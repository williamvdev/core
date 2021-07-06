"""Component to embed TP-Link smart home devices."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .common import (
    ATTR_CONFIG,
    CONF_DIMMER,
    CONF_DISCOVERY,
    CONF_LIGHT,
    CONF_STRIP,
    CONF_SWITCH,
    SmartDevices,
    async_discover_devices,
    get_static_devices,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "tplink"

PLATFORMS = [CONF_LIGHT, CONF_SWITCH]

TPLINK_HOST_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_LIGHT, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_SWITCH, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_STRIP, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_DIMMER, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_DISCOVERY, default=True): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the TP-Link component."""
    conf = config.get(DOMAIN)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][ATTR_CONFIG] = conf

    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TPLink from a config entry."""
    config_data = hass.data[DOMAIN].get(ATTR_CONFIG)

    device_registry = dr.async_get(hass)
    tplink_devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    device_count = len(tplink_devices)

    # These will contain the initialized devices
    lights = hass.data[DOMAIN][CONF_LIGHT] = []
    switches = hass.data[DOMAIN][CONF_SWITCH] = []

    # Add static devices
    static_devices = SmartDevices()
    if config_data is not None:
        static_devices = get_static_devices(config_data)

        lights.extend(static_devices.lights)
        switches.extend(static_devices.switches)

    # Add discovered devices
    if config_data is None or config_data[CONF_DISCOVERY]:
        discovered_devices = await async_discover_devices(
            hass, static_devices, device_count
        )

        lights.extend(discovered_devices.lights)
        switches.extend(discovered_devices.switches)

    forward_setup = hass.config_entries.async_forward_entry_setup
    if lights:
        _LOGGER.debug(
            "Got %s lights: %s", len(lights), ", ".join(d.host for d in lights)
        )

        hass.async_create_task(forward_setup(entry, "light"))

    if switches:
        _LOGGER.debug(
            "Got %s switches: %s",
            len(switches),
            ", ".join(d.host for d in switches),
        )

        hass.async_create_task(forward_setup(entry, "switch"))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = [platform for platform in PLATFORMS if hass.data[DOMAIN].get(platform)]
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        hass.data[DOMAIN].clear()

    return unload_ok
