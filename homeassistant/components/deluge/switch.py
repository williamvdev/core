"""Support for setting the Deluge BitTorrent client in Pause."""
import logging

from deluge_client import FailedToReconnectException

from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON
from homeassistant.helpers.entity import ToggleEntity

from .const import (
    CORE_GET_SESSION_STATE,
    CORE_GET_TORRENTS_STATUS,
    CORE_PAUSE_TORRENT,
    CORE_RESUME_TORRENT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Deluge Switch"


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Config entry support."""
    deluge_api = hass.data[DOMAIN][config_entry.entry_id]
    async_add_devices(
        [DelugeSwitch(deluge_api, DEFAULT_NAME, config_entry.data[CONF_HOST])]
    )


class DelugeSwitch(ToggleEntity):
    """Representation of a Deluge switch."""

    def __init__(self, deluge_client, name, host):
        """Initialize the Deluge switch."""
        self._name = name
        self._host = host
        self.deluge_client = deluge_client
        self._state = STATE_OFF
        self._available = False
        self._type = "switch"

    @property
    def unique_id(self):
        """Return the unique id based on deluge host name and entity type."""
        return f"{self._host}-{self._type}"

    @property
    def name(self):
        """Return the name of the switch."""
        return f"Deluge({self._host}) - Download"

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def available(self):
        """Return true if device is available."""
        return self._available

    def turn_on(self, **kwargs):
        """Turn the device on."""
        torrent_ids = self.deluge_client.call(CORE_GET_SESSION_STATE)
        self.deluge_client.call(CORE_RESUME_TORRENT, torrent_ids)

    def turn_off(self, **kwargs):
        """Turn the device off."""
        torrent_ids = self.deluge_client.call(CORE_GET_SESSION_STATE)
        self.deluge_client.call(CORE_PAUSE_TORRENT, torrent_ids)

    def update(self):
        """Get the latest data from deluge and updates the state."""
        try:
            torrent_list = self.deluge_client.call(
                CORE_GET_TORRENTS_STATUS, {}, ["paused"]
            )
            self._available = True
        except FailedToReconnectException:
            _LOGGER.error("Connection to Deluge Daemon Lost")
            self._available = False
            return
        for torrent in torrent_list.values():
            item = torrent.popitem()
            if not item[1]:
                self._state = STATE_ON
                return

        self._state = STATE_OFF
