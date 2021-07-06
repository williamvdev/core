"""The Switcher integration."""
from __future__ import annotations

from asyncio import QueueEmpty, TimeoutError as Asyncio_TimeoutError, wait_for
from datetime import datetime, timedelta
import logging

from aioswitcher.bridge import SwitcherV2Bridge
import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import EventType

from .const import (
    CONF_DEVICE_PASSWORD,
    CONF_PHONE_ID,
    DATA_DEVICE,
    DOMAIN,
    SIGNAL_SWITCHER_DEVICE_UPDATE,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_PHONE_ID): cv.string,
                vol.Required(CONF_DEVICE_ID): cv.string,
                vol.Required(CONF_DEVICE_PASSWORD): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the switcher component."""
    phone_id = config[DOMAIN][CONF_PHONE_ID]
    device_id = config[DOMAIN][CONF_DEVICE_ID]
    device_password = config[DOMAIN][CONF_DEVICE_PASSWORD]

    v2bridge = SwitcherV2Bridge(hass.loop, phone_id, device_id, device_password)

    await v2bridge.start()

    async def async_stop_bridge(event: EventType) -> None:
        """On Home Assistant stop, gracefully stop the bridge if running."""
        await v2bridge.stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop_bridge)

    try:
        device_data = await wait_for(v2bridge.queue.get(), timeout=10.0)
    except (Asyncio_TimeoutError, RuntimeError):
        _LOGGER.exception("Failed to get response from device")
        await v2bridge.stop()
        return False
    hass.data[DOMAIN] = {DATA_DEVICE: device_data}

    hass.async_create_task(async_load_platform(hass, "switch", DOMAIN, {}, config))
    hass.async_create_task(async_load_platform(hass, "sensor", DOMAIN, {}, config))

    @callback
    def device_updates(timestamp: datetime | None) -> None:
        """Use for updating the device data from the queue."""
        if v2bridge.running:
            try:
                device_new_data = v2bridge.queue.get_nowait()
                if device_new_data:
                    async_dispatcher_send(
                        hass, SIGNAL_SWITCHER_DEVICE_UPDATE, device_new_data
                    )
            except QueueEmpty:
                pass

    async_track_time_interval(hass, device_updates, timedelta(seconds=4))

    return True
