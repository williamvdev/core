"""Support for monitoring the Deluge BitTorrent client API."""
from __future__ import annotations

from datetime import timedelta
import logging

import async_timeout
from deluge_client import FailedToReconnectException

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_HOST, DATA_RATE_KILOBYTES_PER_SECOND, STATE_IDLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CORE_GET_SESSION_STATUS,
    CURRENT_STATUS,
    DHT_DOWNLOAD_RATE,
    DHT_UPLOAD_RATE,
    DOMAIN,
    DOWNLOAD_RATE,
    DOWNLOAD_SPEED,
    SENSORS_COORDINATOR_DATA_NAME,
    STATE_DOWNLOADING,
    STATE_SEEDING,
    STATE_UP_DOWN,
    UPLOAD_RATE,
    UPLOAD_SPEED,
)
from .entity_type import EntityTypeConfiguration

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    EntityTypeConfiguration(CURRENT_STATUS, "Status", None),
    EntityTypeConfiguration(
        DOWNLOAD_SPEED,
        "Download Speed",
        DATA_RATE_KILOBYTES_PER_SECOND,
        "mdi:progress-download",
    ),
    EntityTypeConfiguration(
        UPLOAD_SPEED,
        "Upload Speed",
        DATA_RATE_KILOBYTES_PER_SECOND,
        "mdi:progress-upload",
    ),
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Config Entry support."""
    api = hass.data[DOMAIN][entry.entry_id]

    async def async_update_data():
        try:
            async with async_timeout.timeout(30):
                api_data = await hass.async_add_executor_job(
                    api.call,
                    CORE_GET_SESSION_STATUS,
                    [
                        UPLOAD_RATE,
                        DOWNLOAD_RATE,
                        DHT_UPLOAD_RATE,
                        DHT_DOWNLOAD_RATE,
                    ],
                )
        except FailedToReconnectException as err:
            raise UpdateFailed("Connection to Deluge Daemon Lost") from err

        upload = api_data[UPLOAD_RATE] - api_data[DHT_UPLOAD_RATE]
        download = api_data[DOWNLOAD_RATE] - api_data[DHT_DOWNLOAD_RATE]

        def calculate_current_status(updload, download):
            if upload > 0 and download > 0:
                return STATE_UP_DOWN
            if upload > 0 and download == 0:
                return STATE_SEEDING
            if upload == 0 and download > 0:
                return STATE_DOWNLOADING
            return STATE_IDLE

        def calculate_kbps(bps):
            kbps = float(bps)
            kbps = kbps / 1024
            return round(kbps, 2 if kbps < 0.1 else 1)

        return {
            CURRENT_STATUS: calculate_current_status(upload, download),
            DOWNLOAD_SPEED: calculate_kbps(download),
            UPLOAD_SPEED: calculate_kbps(upload),
        }

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=SENSORS_COORDINATOR_DATA_NAME,
        update_method=async_update_data,
        update_interval=timedelta(seconds=30),
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        DelugeSensor(coordinator, sensor_type, entry.data[CONF_HOST])
        for sensor_type in SENSOR_TYPES
    )


class DelugeSensor(CoordinatorEntity, SensorEntity):
    """DataUpdateCoordinator based sensor entity."""

    def __init__(self, coordinator, sensor_type: EntityTypeConfiguration, host):
        """Init."""
        super().__init__(coordinator)
        self._type = sensor_type
        self._host = host

    @property
    def icon(self) -> str | None:
        """Icon."""
        return self._type.icon or super().icon

    @property
    def unique_id(self):
        """Return a unique id based on the deluge host name and sensor type."""
        return f"{self._host}_{self._type.id}"

    @property
    def name(self):
        """Return entity name based on the deluge host name and sensor type."""
        return f"Deluge({self._host}) - {self._type.name}"

    @property
    def state(self):
        """Return current state."""
        return self.coordinator.data[self._type.id]

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._type.unit_of_measurement
