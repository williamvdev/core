"""Shared Utils for Deluge tests."""

from unittest.mock import patch

from homeassistant.components.deluge.const import DOMAIN
from homeassistant.core import HomeAssistant

from .const import CONFIG, CONNECTION_STATUS_RESPONSE_UPDOWN

from tests.common import MockConfigEntry


async def setup_integration(hass: HomeAssistant) -> MockConfigEntry:
    """Set up integration for testing."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="deluge_unique_id",
        data=CONFIG,
    )

    entry.add_to_hass(hass)

    with patch("deluge_client.DelugeRPCClient.connect", return_value=True), patch(
        "deluge_client.DelugeRPCClient.call",
        return_value=CONNECTION_STATUS_RESPONSE_UPDOWN,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry
