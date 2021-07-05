"""Tests for the Deluge init."""

from unittest.mock import patch

from homeassistant.components.deluge.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import CONFIG

from tests.common import MockConfigEntry


async def test_setup_connection_refused(hass: HomeAssistant) -> None:
    """Test we handle connection refused from deluge server."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="deluge_unique_id",
        data=CONFIG,
    )

    config_entry.add_to_hass(hass)

    with patch(
        "deluge_client.DelugeRPCClient.connect",
        side_effect=ConnectionRefusedError(),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        assert config_entry.state is ConfigEntryState.SETUP_RETRY

    # await hass.config_entries.async_unload(config_entry.entry_id)
    # await hass.async_block_till_done()
    # assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_success(hass: HomeAssistant) -> None:
    """Test we handle connection refused from deluge server."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="deluge_unique_id",
        data=CONFIG,
    )

    config_entry.add_to_hass(hass)

    with patch("deluge_client.DelugeRPCClient.connect", return_value=True):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        assert config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
