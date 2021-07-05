"""Deluge Entity Type Configuration."""

from __future__ import annotations


class EntityTypeConfiguration:
    """Base class for Deluge Entity Type configuration."""

    def __init__(self, entity_id, name, unit_of_measurement, icon=None) -> None:
        """Initialize the entity type configuration."""
        self._id = entity_id
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._icon = icon

    @property
    def id(self) -> str:
        """Return unique id."""
        return self._id

    @property
    def name(self) -> str:
        """Return  name."""
        return self._name

    @property
    def unit_of_measurement(self) -> str:
        """Return unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self) -> str | None:
        """Return icon."""
        return self._icon or None
