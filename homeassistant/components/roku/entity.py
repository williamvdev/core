"""Base Entity for Roku."""
from __future__ import annotations

from homeassistant.const import (
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SW_VERSION,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RokuDataUpdateCoordinator
from .const import DOMAIN


class RokuEntity(CoordinatorEntity):
    """Defines a base Roku entity."""

    coordinator: RokuDataUpdateCoordinator

    def __init__(
        self, *, device_id: str, coordinator: RokuDataUpdateCoordinator
    ) -> None:
        """Initialize the Roku entity."""
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Roku device."""
        if self._device_id is None:
            return None

        return {
            ATTR_IDENTIFIERS: {(DOMAIN, self._device_id)},
            ATTR_NAME: self.coordinator.data.info.name,
            ATTR_MANUFACTURER: self.coordinator.data.info.brand,
            ATTR_MODEL: self.coordinator.data.info.model_name,
            ATTR_SW_VERSION: self.coordinator.data.info.version,
            "suggested_area": self.coordinator.data.info.device_location,
        }
