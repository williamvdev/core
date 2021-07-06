"""Home Assistant Switcher Component Switch platform."""
from __future__ import annotations

from aioswitcher.api import SwitcherV2Api
from aioswitcher.api.messages import SwitcherV2ControlResponseMSG
from aioswitcher.consts import (
    COMMAND_OFF,
    COMMAND_ON,
    STATE_OFF as SWITCHER_STATE_OFF,
    STATE_ON as SWITCHER_STATE_ON,
)
from aioswitcher.devices import SwitcherV2Device
import voluptuous as vol

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_AUTO_OFF,
    CONF_TIMER_MINUTES,
    DATA_DEVICE,
    DOMAIN,
    SERVICE_SET_AUTO_OFF_NAME,
    SERVICE_TURN_ON_WITH_TIMER_NAME,
    SIGNAL_SWITCHER_DEVICE_UPDATE,
)

SERVICE_SET_AUTO_OFF_SCHEMA = {
    vol.Required(CONF_AUTO_OFF): cv.time_period_str,
}

SERVICE_TURN_ON_WITH_TIMER_SCHEMA = {
    vol.Required(CONF_TIMER_MINUTES): vol.All(
        cv.positive_int, vol.Range(min=1, max=150)
    ),
}


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict,
) -> None:
    """Set up the switcher platform for the switch component."""
    if discovery_info is None:
        return

    async def async_set_auto_off_service(entity, service_call: ServiceCall) -> None:
        """Use for handling setting device auto-off service calls."""
        async with SwitcherV2Api(
            hass.loop,
            device_data.ip_addr,
            device_data.phone_id,
            device_data.device_id,
            device_data.device_password,
        ) as swapi:
            await swapi.set_auto_shutdown(service_call.data[CONF_AUTO_OFF])

    async def async_turn_on_with_timer_service(
        entity, service_call: ServiceCall
    ) -> None:
        """Use for handling turning device on with a timer service calls."""
        async with SwitcherV2Api(
            hass.loop,
            device_data.ip_addr,
            device_data.phone_id,
            device_data.device_id,
            device_data.device_password,
        ) as swapi:
            await swapi.control_device(
                COMMAND_ON, service_call.data[CONF_TIMER_MINUTES]
            )

    device_data = hass.data[DOMAIN][DATA_DEVICE]
    async_add_entities([SwitcherControl(hass.data[DOMAIN][DATA_DEVICE])])

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_AUTO_OFF_NAME,
        SERVICE_SET_AUTO_OFF_SCHEMA,
        async_set_auto_off_service,
    )

    platform.async_register_entity_service(
        SERVICE_TURN_ON_WITH_TIMER_NAME,
        SERVICE_TURN_ON_WITH_TIMER_SCHEMA,
        async_turn_on_with_timer_service,
    )


class SwitcherControl(SwitchEntity):
    """Home Assistant switch entity."""

    def __init__(self, device_data: SwitcherV2Device) -> None:
        """Initialize the entity."""
        self._self_initiated = False
        self._device_data = device_data
        self._state = device_data.state

    @property
    def name(self) -> str:
        """Return the device's name."""
        return self._device_data.name

    @property
    def should_poll(self) -> bool:
        """Return False, entity pushes its state to HA."""
        return False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._device_data.device_id}-{self._device_data.mac_addr}"

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._state == SWITCHER_STATE_ON

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._state in [SWITCHER_STATE_ON, SWITCHER_STATE_OFF]

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_SWITCHER_DEVICE_UPDATE, self.async_update_data
            )
        )

    @callback
    def async_update_data(self, device_data: SwitcherV2Device) -> None:
        """Update the entity data."""
        if self._self_initiated:
            self._self_initiated = False
        else:
            self._device_data = device_data
            self._state = self._device_data.state
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: dict) -> None:
        """Turn the entity on."""
        await self._control_device(True)

    async def async_turn_off(self, **kwargs: dict) -> None:
        """Turn the entity off."""
        await self._control_device(False)

    async def _control_device(self, send_on: bool) -> None:
        """Turn the entity on or off."""
        response: SwitcherV2ControlResponseMSG = None
        async with SwitcherV2Api(
            self.hass.loop,
            self._device_data.ip_addr,
            self._device_data.phone_id,
            self._device_data.device_id,
            self._device_data.device_password,
        ) as swapi:
            response = await swapi.control_device(
                COMMAND_ON if send_on else COMMAND_OFF
            )

        if response and response.successful:
            self._self_initiated = True
            self._state = SWITCHER_STATE_ON if send_on else SWITCHER_STATE_OFF
            self.async_write_ha_state()
