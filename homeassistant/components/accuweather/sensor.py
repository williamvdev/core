"""Support for the AccuWeather service."""
from __future__ import annotations

from typing import Any, cast

from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    CONF_NAME,
    DEVICE_CLASS_TEMPERATURE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AccuWeatherDataUpdateCoordinator
from .const import (
    API_IMPERIAL,
    API_METRIC,
    ATTR_ENABLED,
    ATTR_FORECAST,
    ATTR_LABEL,
    ATTR_UNIT_IMPERIAL,
    ATTR_UNIT_METRIC,
    ATTRIBUTION,
    DOMAIN,
    FORECAST_SENSOR_TYPES,
    MANUFACTURER,
    MAX_FORECAST_DAYS,
    NAME,
    SENSOR_TYPES,
)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add AccuWeather entities from a config_entry."""
    name: str = entry.data[CONF_NAME]

    coordinator: AccuWeatherDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[AccuWeatherSensor] = []
    for sensor in SENSOR_TYPES:
        sensors.append(AccuWeatherSensor(name, sensor, coordinator))

    if coordinator.forecast:
        for sensor in FORECAST_SENSOR_TYPES:
            for day in range(MAX_FORECAST_DAYS + 1):
                # Some air quality/allergy sensors are only available for certain
                # locations.
                if sensor in coordinator.data[ATTR_FORECAST][0]:
                    sensors.append(
                        AccuWeatherSensor(name, sensor, coordinator, forecast_day=day)
                    )

    async_add_entities(sensors)


class AccuWeatherSensor(CoordinatorEntity, SensorEntity):
    """Define an AccuWeather entity."""

    coordinator: AccuWeatherDataUpdateCoordinator

    def __init__(
        self,
        name: str,
        kind: str,
        coordinator: AccuWeatherDataUpdateCoordinator,
        forecast_day: int | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._sensor_data = _get_sensor_data(coordinator.data, forecast_day, kind)
        if forecast_day is None:
            self._description = SENSOR_TYPES[kind]
        else:
            self._description = FORECAST_SENSOR_TYPES[kind]
        self._unit_system = API_METRIC if coordinator.is_metric else API_IMPERIAL
        self.kind = kind
        self._attrs = {ATTR_ATTRIBUTION: ATTRIBUTION}
        self.forecast_day = forecast_day
        self._attr_state_class = self._description.get(ATTR_STATE_CLASS)
        self._attr_icon = self._description[ATTR_ICON]
        self._attr_device_class = self._description[ATTR_DEVICE_CLASS]
        self._attr_entity_registry_enabled_default = self._description[ATTR_ENABLED]
        if self.forecast_day is not None:
            self._attr_name = f"{name} {self._description[ATTR_LABEL]} {forecast_day}d"
            self._attr_unique_id = (
                f"{coordinator.location_key}-{kind}-{forecast_day}".lower()
            )
        else:
            self._attr_name = f"{name} {self._description[ATTR_LABEL]}"
            self._attr_unique_id = f"{coordinator.location_key}-{kind}".lower()
        if coordinator.is_metric:
            self._attr_unit_of_measurement = self._description[ATTR_UNIT_METRIC]
        else:
            self._attr_unit_of_measurement = self._description[ATTR_UNIT_IMPERIAL]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.location_key)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "entry_type": "service",
        }

    @property
    def state(self) -> StateType:
        """Return the state."""
        if self.forecast_day is not None:
            if self._description["device_class"] == DEVICE_CLASS_TEMPERATURE:
                return cast(float, self._sensor_data["Value"])
            if self.kind == "UVIndex":
                return cast(int, self._sensor_data["Value"])
        if self.kind in ["Grass", "Mold", "Ragweed", "Tree", "Ozone"]:
            return cast(int, self._sensor_data["Value"])
        if self.kind == "Ceiling":
            return round(self._sensor_data[self._unit_system]["Value"])
        if self.kind == "PressureTendency":
            return cast(str, self._sensor_data["LocalizedText"].lower())
        if self._description["device_class"] == DEVICE_CLASS_TEMPERATURE:
            return cast(float, self._sensor_data[self._unit_system]["Value"])
        if self.kind == "Precipitation":
            return cast(float, self._sensor_data[self._unit_system]["Value"])
        if self.kind in ["Wind", "WindGust"]:
            return cast(float, self._sensor_data["Speed"][self._unit_system]["Value"])
        if self.kind in ["WindDay", "WindNight", "WindGustDay", "WindGustNight"]:
            return cast(StateType, self._sensor_data["Speed"]["Value"])
        return cast(StateType, self._sensor_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.forecast_day is not None:
            if self.kind in ["WindDay", "WindNight", "WindGustDay", "WindGustNight"]:
                self._attrs["direction"] = self._sensor_data["Direction"]["English"]
            elif self.kind in ["Grass", "Mold", "Ragweed", "Tree", "UVIndex", "Ozone"]:
                self._attrs["level"] = self._sensor_data["Category"]
            return self._attrs
        if self.kind == "UVIndex":
            self._attrs["level"] = self.coordinator.data["UVIndexText"]
        elif self.kind == "Precipitation":
            self._attrs["type"] = self.coordinator.data["PrecipitationType"]
        return self._attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        self._sensor_data = _get_sensor_data(
            self.coordinator.data, self.forecast_day, self.kind
        )
        self.async_write_ha_state()


def _get_sensor_data(
    sensors: dict[str, Any], forecast_day: int | None, kind: str
) -> Any:
    """Get sensor data."""
    if forecast_day is not None:
        return sensors[ATTR_FORECAST][forecast_day][kind]

    if kind == "Precipitation":
        return sensors["PrecipitationSummary"][kind]

    return sensors[kind]
