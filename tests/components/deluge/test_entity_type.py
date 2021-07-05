"""Test the Deluge EntityTypeConfiguration class."""
from homeassistant.components.deluge.entity_type import EntityTypeConfiguration


def test_entity_type() -> None:
    """Test the class initializer."""
    fixture = EntityTypeConfiguration("test_id", "Test Name", "kbps", "mdi:flash")
    assert fixture.id == "test_id"
    assert fixture.name == "Test Name"
    assert fixture.unit_of_measurement == "kbps"
    assert fixture.icon == "mdi:flash"
