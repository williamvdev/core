"""Test the Deluge Sensor Platform."""

from unittest.mock import patch

from homeassistant.components.deluge.const import (
    STATE_DOWNLOADING,
    STATE_SEEDING,
    STATE_UP_DOWN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_IDLE
from homeassistant.core import HomeAssistant

from .const import (
    CONNECTION_STATUS_RESPONSE_DOWNLOADING,
    CONNECTION_STATUS_RESPONSE_IDLE,
    CONNECTION_STATUS_RESPONSE_SEEDING,
)
from .util import setup_integration


async def test_deluge_create_sensors(hass: HomeAssistant) -> None:
    """Test setup & creating deluge sensors."""
    config_entry = await setup_integration(hass)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.deluge_localhost_download_speed").state == "450.0"
    assert hass.states.get("sensor.deluge_localhost_upload_speed").state == "72.0"
    assert hass.states.get("sensor.deluge_localhost_status").state == STATE_UP_DOWN


async def test_deluge_status_seeding(hass: HomeAssistant) -> None:
    """Test for correct status report when seeding."""
    await setup_integration(hass)
    with patch(
        "deluge_client.DelugeRPCClient.call",
        return_value=CONNECTION_STATUS_RESPONSE_SEEDING,
    ):
        await hass.helpers.entity_component.async_update_entity(
            "sensor.deluge_localhost_status"
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.deluge_localhost_status").state == STATE_SEEDING


async def test_deluge_status_downloading(hass: HomeAssistant) -> None:
    """Test for correct status report when downloading."""
    await setup_integration(hass)
    with patch(
        "deluge_client.DelugeRPCClient.call",
        return_value=CONNECTION_STATUS_RESPONSE_DOWNLOADING,
    ):
        await hass.helpers.entity_component.async_update_entity(
            "sensor.deluge_localhost_status"
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.deluge_localhost_status").state == STATE_DOWNLOADING


async def test_deluge_status_idle(hass: HomeAssistant) -> None:
    """Test for correct status report when idle."""
    await setup_integration(hass)
    with patch(
        "deluge_client.DelugeRPCClient.call",
        return_value=CONNECTION_STATUS_RESPONSE_IDLE,
    ):
        await hass.helpers.entity_component.async_update_entity(
            "sensor.deluge_localhost_status"
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.deluge_localhost_status").state == STATE_IDLE
