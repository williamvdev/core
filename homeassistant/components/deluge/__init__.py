"""The Deluge integration."""
from __future__ import annotations

import logging

import deluge_client

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    "switch",
    "sensor",
]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Config entry support."""
    hass.data.setdefault(DOMAIN, {})
    deluge_api = deluge_client.DelugeRPCClient(
        config_entry.data[CONF_HOST],
        config_entry.data[CONF_PORT],
        config_entry.data[CONF_USERNAME],
        config_entry.data[CONF_PASSWORD],
        True,
    )
    try:
        deluge_api.connect()
    except ConnectionRefusedError as err:
        _LOGGER.error("Connection to Deluge Daemon failed")
        raise ConfigEntryNotReady from err

    hass.data[DOMAIN][config_entry.entry_id] = deluge_api
    hass.config_entries.async_setup_platforms(config_entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
