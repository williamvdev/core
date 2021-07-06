"""Support for esphome devices."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import functools
import logging
import math
from typing import Generic, TypeVar

from aioesphomeapi import (
    APIClient,
    APIConnectionError,
    APIVersion,
    DeviceInfo as EsphomeDeviceInfo,
    EntityInfo,
    EntityState,
    HomeassistantServiceCall,
    UserService,
    UserServiceArgType,
)
import voluptuous as vol
from zeroconf import DNSPointer, DNSRecord, RecordUpdateListener, Zeroconf

from homeassistant import const
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_MODE,
    CONF_PASSWORD,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import template
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template

# Import config flow so that it's added to the registry
from .entry_data import RuntimeEntryData

DOMAIN = "esphome"
_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")

STORAGE_VERSION = 1


@dataclass
class DomainData:
    """Define a class that stores global esphome data in hass.data[DOMAIN]."""

    _entry_datas: dict[str, RuntimeEntryData] = field(default_factory=dict)
    _stores: dict[str, Store] = field(default_factory=dict)

    def get_entry_data(self, entry: ConfigEntry) -> RuntimeEntryData:
        """Return the runtime entry data associated with this config entry.

        Raises KeyError if the entry isn't loaded yet.
        """
        return self._entry_datas[entry.entry_id]

    def set_entry_data(self, entry: ConfigEntry, entry_data: RuntimeEntryData) -> None:
        """Set the runtime entry data associated with this config entry."""
        if entry.entry_id in self._entry_datas:
            raise ValueError("Entry data for this entry is already set")
        self._entry_datas[entry.entry_id] = entry_data

    def pop_entry_data(self, entry: ConfigEntry) -> RuntimeEntryData:
        """Pop the runtime entry data instance associated with this config entry."""
        return self._entry_datas.pop(entry.entry_id)

    def is_entry_loaded(self, entry: ConfigEntry) -> bool:
        """Check whether the given entry is loaded."""
        return entry.entry_id in self._entry_datas

    def get_or_create_store(self, hass: HomeAssistant, entry: ConfigEntry) -> Store:
        """Get or create a Store instance for the given config entry."""
        return self._stores.setdefault(
            entry.entry_id,
            Store(
                hass, STORAGE_VERSION, f"esphome.{entry.entry_id}", encoder=JSONEncoder
            ),
        )

    @classmethod
    def get(cls: type[_T], hass: HomeAssistant) -> _T:
        """Get the global DomainData instance stored in hass.data."""
        # Don't use setdefault - this is a hot code path
        if DOMAIN in hass.data:
            return hass.data[DOMAIN]
        ret = hass.data[DOMAIN] = cls()
        return ret


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the esphome component."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    password = entry.data[CONF_PASSWORD]
    device_id = None

    zeroconf_instance = await zeroconf.async_get_instance(hass)

    cli = APIClient(
        hass.loop,
        host,
        port,
        password,
        client_info=f"Home Assistant {const.__version__}",
        zeroconf_instance=zeroconf_instance,
    )

    domain_data = DomainData.get(hass)
    entry_data = RuntimeEntryData(
        client=cli,
        entry_id=entry.entry_id,
        store=domain_data.get_or_create_store(hass, entry),
    )
    domain_data.set_entry_data(entry, entry_data)

    async def on_stop(event: Event) -> None:
        """Cleanup the socket client on HA stop."""
        await _cleanup_instance(hass, entry)

    # Use async_listen instead of async_listen_once so that we don't deregister
    # the callback twice when shutting down Home Assistant.
    # "Unable to remove unknown listener <function EventBus.async_listen_once.<locals>.onetime_listener>"
    entry_data.cleanup_callbacks.append(
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, on_stop)
    )

    @callback
    def async_on_state(state: EntityState) -> None:
        """Send dispatcher updates when a new state is received."""
        entry_data.async_update_state(hass, state)

    @callback
    def async_on_service_call(service: HomeassistantServiceCall) -> None:
        """Call service when user automation in ESPHome config is triggered."""
        domain, service_name = service.service.split(".", 1)
        service_data = service.data

        if service.data_template:
            try:
                data_template = {
                    key: Template(value) for key, value in service.data_template.items()
                }
                template.attach(hass, data_template)
                service_data.update(
                    template.render_complex(data_template, service.variables)
                )
            except TemplateError as ex:
                _LOGGER.error("Error rendering data template for %s: %s", host, ex)
                return

        if service.is_event:
            # ESPHome uses servicecall packet for both events and service calls
            # Ensure the user can only send events of form 'esphome.xyz'
            if domain != "esphome":
                _LOGGER.error(
                    "Can only generate events under esphome domain! (%s)", host
                )
                return

            # Call native tag scan
            if service_name == "tag_scanned":
                tag_id = service_data["tag_id"]
                hass.async_create_task(
                    hass.components.tag.async_scan_tag(tag_id, device_id)
                )
                return

            hass.bus.async_fire(service.service, service_data)
        else:
            hass.async_create_task(
                hass.services.async_call(
                    domain, service_name, service_data, blocking=True
                )
            )

    async def _send_home_assistant_state(
        entity_id: str, attribute: str | None, state: State | None
    ) -> None:
        """Forward Home Assistant states to ESPHome."""
        if state is None or (attribute and attribute not in state.attributes):
            return

        send_state = state.state
        if attribute:
            send_state = state.attributes[attribute]
            # ESPHome only handles "on"/"off" for boolean values
            if isinstance(send_state, bool):
                send_state = "on" if send_state else "off"

        await cli.send_home_assistant_state(entity_id, attribute, str(send_state))

    @callback
    def async_on_state_subscription(
        entity_id: str, attribute: str | None = None
    ) -> None:
        """Subscribe and forward states for requested entities."""

        async def send_home_assistant_state_event(event: Event) -> None:
            """Forward Home Assistant states updates to ESPHome."""

            # Only communicate changes to the state or attribute tracked
            if (
                "old_state" in event.data
                and "new_state" in event.data
                and (
                    (
                        not attribute
                        and event.data["old_state"].state
                        == event.data["new_state"].state
                    )
                    or (
                        attribute
                        and attribute in event.data["old_state"].attributes
                        and attribute in event.data["new_state"].attributes
                        and event.data["old_state"].attributes[attribute]
                        == event.data["new_state"].attributes[attribute]
                    )
                )
            ):
                return

            await _send_home_assistant_state(
                event.data["entity_id"], attribute, event.data.get("new_state")
            )

        unsub = async_track_state_change_event(
            hass, [entity_id], send_home_assistant_state_event
        )
        entry_data.disconnect_callbacks.append(unsub)

        # Send initial state
        hass.async_create_task(
            _send_home_assistant_state(entity_id, attribute, hass.states.get(entity_id))
        )

    async def on_login() -> None:
        """Subscribe to states and list entities on successful API login."""
        nonlocal device_id
        try:
            entry_data.device_info = await cli.device_info()
            entry_data.api_version = cli.api_version
            entry_data.available = True
            device_id = await _async_setup_device_registry(
                hass, entry, entry_data.device_info
            )
            entry_data.async_update_device_state(hass)

            entity_infos, services = await cli.list_entities_services()
            await entry_data.async_update_static_infos(hass, entry, entity_infos)
            await _setup_services(hass, entry_data, services)
            await cli.subscribe_states(async_on_state)
            await cli.subscribe_service_calls(async_on_service_call)
            await cli.subscribe_home_assistant_states(async_on_state_subscription)

            hass.async_create_task(entry_data.async_save_to_store())
        except APIConnectionError as err:
            _LOGGER.warning("Error getting initial data for %s: %s", host, err)
            # Re-connection logic will trigger after this
            await cli.disconnect()

    reconnect_logic = ReconnectLogic(
        hass, cli, entry, host, on_login, zeroconf_instance
    )

    async def complete_setup() -> None:
        """Complete the config entry setup."""
        infos, services = await entry_data.async_load_from_store()
        await entry_data.async_update_static_infos(hass, entry, infos)
        await _setup_services(hass, entry_data, services)

        await reconnect_logic.start()
        entry_data.cleanup_callbacks.append(reconnect_logic.stop_callback)

    hass.async_create_task(complete_setup())
    return True


class ReconnectLogic(RecordUpdateListener):
    """Reconnectiong logic handler for ESPHome config entries.

    Contains two reconnect strategies:
     - Connect with increasing time between connection attempts.
     - Listen to zeroconf mDNS records, if any records are found for this device, try reconnecting immediately.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        cli: APIClient,
        entry: ConfigEntry,
        host: str,
        on_login,
        zc: Zeroconf,
    ):
        """Initialize ReconnectingLogic."""
        self._hass = hass
        self._cli = cli
        self._entry = entry
        self._host = host
        self._on_login = on_login
        self._zc = zc
        # Flag to check if the device is connected
        self._connected = True
        self._connected_lock = asyncio.Lock()
        self._zc_lock = asyncio.Lock()
        self._zc_listening = False
        # Event the different strategies use for issuing a reconnect attempt.
        self._reconnect_event = asyncio.Event()
        # The task containing the infinite reconnect loop while running
        self._loop_task: asyncio.Task | None = None
        # How many reconnect attempts have there been already, used for exponential wait time
        self._tries = 0
        self._tries_lock = asyncio.Lock()
        # Track the wait task to cancel it on HA shutdown
        self._wait_task: asyncio.Task | None = None
        self._wait_task_lock = asyncio.Lock()

    @property
    def _entry_data(self) -> RuntimeEntryData | None:
        domain_data = DomainData.get(self._hass)
        try:
            return domain_data.get_entry_data(self._entry)
        except KeyError:
            return None

    async def _on_disconnect(self):
        """Log and issue callbacks when disconnecting."""
        if self._entry_data is None:
            return
        # This can happen often depending on WiFi signal strength.
        # So therefore all these connection warnings are logged
        # as infos. The "unavailable" logic will still trigger so the
        # user knows if the device is not connected.
        _LOGGER.info("Disconnected from ESPHome API for %s", self._host)

        # Run disconnect hooks
        for disconnect_cb in self._entry_data.disconnect_callbacks:
            disconnect_cb()
        self._entry_data.disconnect_callbacks = []
        self._entry_data.available = False
        self._entry_data.async_update_device_state(self._hass)
        await self._start_zc_listen()

        # Reset tries
        async with self._tries_lock:
            self._tries = 0
        # Connected needs to be reset before the reconnect event (opposite order of check)
        async with self._connected_lock:
            self._connected = False
        self._reconnect_event.set()

    async def _wait_and_start_reconnect(self):
        """Wait for exponentially increasing time to issue next reconnect event."""
        async with self._tries_lock:
            tries = self._tries
        # If not first re-try, wait and print message
        # Cap wait time at 1 minute. This is because while working on the
        # device (e.g. soldering stuff), users don't want to have to wait
        # a long time for their device to show up in HA again (this was
        # mentioned a lot in early feedback)
        tries = min(tries, 10)  # prevent OverflowError
        wait_time = int(round(min(1.8 ** tries, 60.0)))
        if tries == 1:
            _LOGGER.info("Trying to reconnect to %s in the background", self._host)
        _LOGGER.debug("Retrying %s in %d seconds", self._host, wait_time)
        await asyncio.sleep(wait_time)
        async with self._wait_task_lock:
            self._wait_task = None
        self._reconnect_event.set()

    async def _try_connect(self):
        """Try connecting to the API client."""
        async with self._tries_lock:
            tries = self._tries
            self._tries += 1

        try:
            await self._cli.connect(on_stop=self._on_disconnect, login=True)
        except APIConnectionError as error:
            level = logging.WARNING if tries == 0 else logging.DEBUG
            _LOGGER.log(
                level,
                "Can't connect to ESPHome API for %s (%s): %s",
                self._entry.unique_id,
                self._host,
                error,
            )
            await self._start_zc_listen()
            # Schedule re-connect in event loop in order not to delay HA
            # startup. First connect is scheduled in tracked tasks.
            async with self._wait_task_lock:
                # Allow only one wait task at a time
                # can happen if mDNS record received while waiting, then use existing wait task
                if self._wait_task is not None:
                    return

                self._wait_task = self._hass.loop.create_task(
                    self._wait_and_start_reconnect()
                )
        else:
            _LOGGER.info("Successfully connected to %s", self._host)
            async with self._tries_lock:
                self._tries = 0
            async with self._connected_lock:
                self._connected = True
            await self._stop_zc_listen()
            self._hass.async_create_task(self._on_login())

    async def _reconnect_once(self):
        # Wait and clear reconnection event
        await self._reconnect_event.wait()
        self._reconnect_event.clear()

        # If in connected state, do not try to connect again.
        async with self._connected_lock:
            if self._connected:
                return False

        # Check if the entry got removed or disabled, in which case we shouldn't reconnect
        if not DomainData.get(self._hass).is_entry_loaded(self._entry):
            # When removing/disconnecting manually
            return

        device_registry = self._hass.helpers.device_registry.async_get(self._hass)
        devices = dr.async_entries_for_config_entry(
            device_registry, self._entry.entry_id
        )
        for device in devices:
            # There is only one device in ESPHome
            if device.disabled:
                # Don't attempt to connect if it's disabled
                return

        await self._try_connect()

    async def _reconnect_loop(self):
        while True:
            try:
                await self._reconnect_once()
            except asyncio.CancelledError:  # pylint: disable=try-except-raise
                raise
            except Exception:  # pylint: disable=broad-except
                _LOGGER.error("Caught exception while reconnecting", exc_info=True)

    async def start(self):
        """Start the reconnecting logic background task."""
        # Create reconnection loop outside of HA's tracked tasks in order
        # not to delay startup.
        self._loop_task = self._hass.loop.create_task(self._reconnect_loop())

        async with self._connected_lock:
            self._connected = False
        self._reconnect_event.set()

    async def stop(self):
        """Stop the reconnecting logic background task. Does not disconnect the client."""
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None
        async with self._wait_task_lock:
            if self._wait_task is not None:
                self._wait_task.cancel()
            self._wait_task = None
        await self._stop_zc_listen()

    async def _start_zc_listen(self):
        """Listen for mDNS records.

        This listener allows us to schedule a reconnect as soon as a
        received mDNS record indicates the node is up again.
        """
        async with self._zc_lock:
            if not self._zc_listening:
                await self._hass.async_add_executor_job(
                    self._zc.add_listener, self, None
                )
                self._zc_listening = True

    async def _stop_zc_listen(self):
        """Stop listening for zeroconf updates."""
        async with self._zc_lock:
            if self._zc_listening:
                await self._hass.async_add_executor_job(self._zc.remove_listener, self)
                self._zc_listening = False

    @callback
    def stop_callback(self):
        """Stop as an async callback function."""
        self._hass.async_create_task(self.stop())

    @callback
    def _set_reconnect(self):
        self._reconnect_event.set()

    def update_record(self, zc: Zeroconf, now: float, record: DNSRecord) -> None:
        """Listen to zeroconf updated mDNS records."""
        if not isinstance(record, DNSPointer):
            # We only consider PTR records and match using the alias name
            return
        if self._entry_data is None or self._entry_data.device_info is None:
            # Either the entry was already teared down or we haven't received device info yet
            return
        filter_alias = f"{self._entry_data.device_info.name}._esphomelib._tcp.local."
        if record.alias != filter_alias:
            return

        # This is a mDNS record from the device and could mean it just woke up
        # Check if already connected, no lock needed for this access
        if self._connected:
            return

        # Tell reconnection logic to retry connection attempt now (even before reconnect timer finishes)
        _LOGGER.debug(
            "%s: Triggering reconnect because of received mDNS record %s",
            self._host,
            record,
        )
        self._hass.add_job(self._set_reconnect)


async def _async_setup_device_registry(
    hass: HomeAssistant, entry: ConfigEntry, device_info: EsphomeDeviceInfo
):
    """Set up device registry feature for a particular config entry."""
    sw_version = device_info.esphome_version
    if device_info.compilation_time:
        sw_version += f" ({device_info.compilation_time})"
    device_registry = await dr.async_get_registry(hass)
    entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, device_info.mac_address)},
        name=device_info.name,
        manufacturer="espressif",
        model=device_info.model,
        sw_version=sw_version,
    )
    return entry.id


async def _register_service(
    hass: HomeAssistant, entry_data: RuntimeEntryData, service: UserService
):
    service_name = f"{entry_data.device_info.name.replace('-', '_')}_{service.name}"
    schema = {}
    fields = {}

    for arg in service.args:
        metadata = {
            UserServiceArgType.BOOL: {
                "validator": cv.boolean,
                "example": "False",
                "selector": {"boolean": None},
            },
            UserServiceArgType.INT: {
                "validator": vol.Coerce(int),
                "example": "42",
                "selector": {"number": {CONF_MODE: "box"}},
            },
            UserServiceArgType.FLOAT: {
                "validator": vol.Coerce(float),
                "example": "12.3",
                "selector": {"number": {CONF_MODE: "box", "step": 1e-3}},
            },
            UserServiceArgType.STRING: {
                "validator": cv.string,
                "example": "Example text",
                "selector": {"text": None},
            },
            UserServiceArgType.BOOL_ARRAY: {
                "validator": [cv.boolean],
                "description": "A list of boolean values.",
                "example": "[True, False]",
                "selector": {"object": {}},
            },
            UserServiceArgType.INT_ARRAY: {
                "validator": [vol.Coerce(int)],
                "description": "A list of integer values.",
                "example": "[42, 34]",
                "selector": {"object": {}},
            },
            UserServiceArgType.FLOAT_ARRAY: {
                "validator": [vol.Coerce(float)],
                "description": "A list of floating point numbers.",
                "example": "[ 12.3, 34.5 ]",
                "selector": {"object": {}},
            },
            UserServiceArgType.STRING_ARRAY: {
                "validator": [cv.string],
                "description": "A list of strings.",
                "example": "['Example text', 'Another example']",
                "selector": {"object": {}},
            },
        }[arg.type]
        schema[vol.Required(arg.name)] = metadata["validator"]
        fields[arg.name] = {
            "name": arg.name,
            "required": True,
            "description": metadata.get("description"),
            "example": metadata["example"],
            "selector": metadata["selector"],
        }

    async def execute_service(call):
        await entry_data.client.execute_service(service, call.data)

    hass.services.async_register(
        DOMAIN, service_name, execute_service, vol.Schema(schema)
    )

    service_desc = {
        "description": f"Calls the service {service.name} of the node {entry_data.device_info.name}",
        "fields": fields,
    }

    async_set_service_schema(hass, DOMAIN, service_name, service_desc)


async def _setup_services(
    hass: HomeAssistant, entry_data: RuntimeEntryData, services: list[UserService]
):
    old_services = entry_data.services.copy()
    to_unregister = []
    to_register = []
    for service in services:
        if service.key in old_services:
            # Already exists
            matching = old_services.pop(service.key)
            if matching != service:
                # Need to re-register
                to_unregister.append(matching)
                to_register.append(service)
        else:
            # New service
            to_register.append(service)

    for service in old_services.values():
        to_unregister.append(service)

    entry_data.services = {serv.key: serv for serv in services}

    for service in to_unregister:
        service_name = f"{entry_data.device_info.name}_{service.name}"
        hass.services.async_remove(DOMAIN, service_name)

    for service in to_register:
        await _register_service(hass, entry_data, service)


async def _cleanup_instance(
    hass: HomeAssistant, entry: ConfigEntry
) -> RuntimeEntryData:
    """Cleanup the esphome client if it exists."""
    domain_data = DomainData.get(hass)
    data = domain_data.pop_entry_data(entry)
    for disconnect_cb in data.disconnect_callbacks:
        disconnect_cb()
    for cleanup_callback in data.cleanup_callbacks:
        cleanup_callback()
    await data.client.disconnect()
    return data


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an esphome config entry."""
    entry_data = await _cleanup_instance(hass, entry)
    return await hass.config_entries.async_unload_platforms(
        entry, entry_data.loaded_platforms
    )


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove an esphome config entry."""
    await DomainData.get(hass).get_or_create_store(hass, entry).async_remove()


async def platform_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
    *,
    component_key: str,
    info_type,
    entity_type,
    state_type,
) -> None:
    """Set up an esphome platform.

    This method is in charge of receiving, distributing and storing
    info and state updates.
    """
    entry_data: RuntimeEntryData = DomainData.get(hass).get_entry_data(entry)
    entry_data.info[component_key] = {}
    entry_data.old_info[component_key] = {}
    entry_data.state[component_key] = {}

    @callback
    def async_list_entities(infos: list[EntityInfo]):
        """Update entities of this platform when entities are listed."""
        old_infos = entry_data.info[component_key]
        new_infos = {}
        add_entities = []
        for info in infos:
            if not isinstance(info, info_type):
                # Filter out infos that don't belong to this platform.
                continue

            if info.key in old_infos:
                # Update existing entity
                old_infos.pop(info.key)
            else:
                # Create new entity
                entity = entity_type(entry_data, component_key, info.key)
                add_entities.append(entity)
            new_infos[info.key] = info

        # Remove old entities
        for info in old_infos.values():
            entry_data.async_remove_entity(hass, component_key, info.key)

        # First copy the now-old info into the backup object
        entry_data.old_info[component_key] = entry_data.info[component_key]
        # Then update the actual info
        entry_data.info[component_key] = new_infos

        # Add entities to Home Assistant
        async_add_entities(add_entities)

    signal = f"esphome_{entry.entry_id}_on_list"
    entry_data.cleanup_callbacks.append(
        async_dispatcher_connect(hass, signal, async_list_entities)
    )

    @callback
    def async_entity_state(state: EntityState):
        """Notify the appropriate entity of an updated state."""
        if not isinstance(state, state_type):
            return
        entry_data.state[component_key][state.key] = state
        entry_data.async_update_entity(hass, component_key, state.key)

    signal = f"esphome_{entry.entry_id}_on_state"
    entry_data.cleanup_callbacks.append(
        async_dispatcher_connect(hass, signal, async_entity_state)
    )


def esphome_state_property(func):
    """Wrap a state property of an esphome entity.

    This checks if the state object in the entity is set, and
    prevents writing NAN values to the Home Assistant state machine.
    """

    @property
    def _wrapper(self):
        if self._state is None:
            return None
        val = func(self)
        if isinstance(val, float) and math.isnan(val):
            # Home Assistant doesn't use NAN values in state machine
            # (not JSON serializable)
            return None
        return val

    return _wrapper


class EsphomeEnumMapper(Generic[_T]):
    """Helper class to convert between hass and esphome enum values."""

    def __init__(self, mapping: dict[_T, str]) -> None:
        """Construct a EsphomeEnumMapper."""
        # Add none mapping
        mapping = {None: None, **mapping}
        self._mapping = mapping
        self._inverse: dict[str, _T] = {v: k for k, v in mapping.items()}

    def from_esphome(self, value: _T | None) -> str | None:
        """Convert from an esphome int representation to a hass string."""
        return self._mapping[value]

    def from_hass(self, value: str) -> _T:
        """Convert from a hass string to a esphome int representation."""
        return self._inverse[value]


class EsphomeBaseEntity(Entity):
    """Define a base esphome entity."""

    def __init__(
        self, entry_data: RuntimeEntryData, component_key: str, key: int
    ) -> None:
        """Initialize."""
        self._entry_data = entry_data
        self._component_key = component_key
        self._key = key

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                (
                    f"esphome_{self._entry_id}_remove_"
                    f"{self._component_key}_{self._key}"
                ),
                functools.partial(self.async_remove, force_remove=True),
            )
        )

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"esphome_{self._entry_id}_on_device_update",
                self._on_device_update,
            )
        )

    @callback
    def _on_device_update(self) -> None:
        """Update the entity state when device info has changed."""
        if self._entry_data.available:
            # Don't update the HA state yet when the device comes online.
            # Only update the HA state when the full state arrives
            # through the next entity state packet.
            return
        self.async_write_ha_state()

    @property
    def _entry_id(self) -> str:
        return self._entry_data.entry_id

    @property
    def _api_version(self) -> APIVersion:
        return self._entry_data.api_version

    @property
    def _static_info(self) -> EntityInfo:
        # Check if value is in info database. Use a single lookup.
        info = self._entry_data.info[self._component_key].get(self._key)
        if info is not None:
            return info
        # This entity is in the removal project and has been removed from .info
        # already, look in old_info
        return self._entry_data.old_info[self._component_key].get(self._key)

    @property
    def _device_info(self) -> EsphomeDeviceInfo:
        return self._entry_data.device_info

    @property
    def _client(self) -> APIClient:
        return self._entry_data.client

    @property
    def _state(self) -> EntityState | None:
        try:
            return self._entry_data.state[self._component_key][self._key]
        except KeyError:
            return None

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        device = self._device_info

        if device.has_deep_sleep:
            # During deep sleep the ESP will not be connectable (by design)
            # For these cases, show it as available
            return True

        return self._entry_data.available

    @property
    def unique_id(self) -> str | None:
        """Return a unique id identifying the entity."""
        if not self._static_info.unique_id:
            return None
        return self._static_info.unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return {
            "connections": {(dr.CONNECTION_NETWORK_MAC, self._device_info.mac_address)}
        }

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._static_info.name

    @property
    def should_poll(self) -> bool:
        """Disable polling."""
        return False


class EsphomeEntity(EsphomeBaseEntity):
    """Define a generic esphome entity."""

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""

        await super().async_added_to_hass()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                (
                    f"esphome_{self._entry_id}"
                    f"_update_{self._component_key}_{self._key}"
                ),
                self.async_write_ha_state,
            )
        )
