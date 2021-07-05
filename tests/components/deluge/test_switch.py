"""Test the Deluge Switch Platform."""
from unittest.mock import call, patch

import deluge_client
from deluge_client.client import DelugeRPCClient, FailedToReconnectException

from homeassistant.components.deluge.const import (
    CORE_GET_SESSION_STATE,
    CORE_PAUSE_TORRENT,
    CORE_RESUME_TORRENT,
)
from homeassistant.components.deluge.switch import DEFAULT_NAME, DelugeSwitch
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_component

from .const import (
    CONFIG,
    SESSION_STATE_SINGLE_TORRENT,
    SINGLE_TORRENT_STATUS_ACTIVE,
    SINGLE_TORRENT_STATUS_PAUSED,
)
from .util import setup_integration


async def test_deluge_create_switch(hass: HomeAssistant) -> None:
    """Test setup & creating deluge sensors."""
    config_entry = await setup_integration(hass)
    assert config_entry.state is ConfigEntryState.LOADED
    assert (
        hass.states.get("switch.deluge_localhost_download").state == STATE_UNAVAILABLE
    )


def _setup_test_switch(client):
    """Create a DelugeSwitch instance."""
    switch = DelugeSwitch(client, DEFAULT_NAME, CONFIG["host"])
    return switch


async def test_deluge_switch_update(hass: HomeAssistant) -> None:
    """Test correct switch state calculation based on api response."""
    await setup_integration(hass)

    with patch(
        "deluge_client.DelugeRPCClient.call", return_value=SINGLE_TORRENT_STATUS_PAUSED
    ):
        await entity_component.async_update_entity(
            hass, "switch.deluge_localhost_download"
        )
        await hass.async_block_till_done()

        assert hass.states.get("switch.deluge_localhost_download").state == STATE_OFF

    with patch(
        "deluge_client.DelugeRPCClient.call", return_value=SINGLE_TORRENT_STATUS_ACTIVE
    ):
        await entity_component.async_update_entity(
            hass, "switch.deluge_localhost_download"
        )
        await hass.async_block_till_done()

        assert hass.states.get("switch.deluge_localhost_download").state == STATE_ON


async def test_deluge_switch_error(hass: HomeAssistant) -> None:
    """Test api error handling."""
    await setup_integration(hass)

    with patch(
        "deluge_client.DelugeRPCClient.call", side_effect=FailedToReconnectException()
    ):
        await entity_component.async_update_entity(
            hass, "switch.deluge_localhost_download"
        )
        await hass.async_block_till_done()

        assert (
            hass.states.get("switch.deluge_localhost_download").state
            == STATE_UNAVAILABLE
        )


def test_switch_turn_on(hass: HomeAssistant) -> None:
    """Test for correct api call when turning on the switch."""
    with patch.object(
        deluge_client.DelugeRPCClient,
        "call",
        side_effect=[SESSION_STATE_SINGLE_TORRENT, None],
    ) as mocked_client:
        client = DelugeRPCClient(**CONFIG, decode_utf8=True)
        switch = _setup_test_switch(client)
        switch.turn_on()

        calls = [
            call(CORE_GET_SESSION_STATE),
            call(CORE_RESUME_TORRENT, SESSION_STATE_SINGLE_TORRENT),
        ]

        mocked_client.assert_has_calls(calls, any_order=False)


def test_switch_turn_off(hass: HomeAssistant) -> None:
    """Test for correct api call when turning off the switch."""

    with patch.object(
        deluge_client.DelugeRPCClient,
        "call",
        side_effect=[SESSION_STATE_SINGLE_TORRENT, None],
    ) as mocked_client:
        client = DelugeRPCClient(**CONFIG, decode_utf8=True)
        switch = _setup_test_switch(client)
        switch.turn_off()

        calls = [
            call(CORE_GET_SESSION_STATE),
            call(CORE_PAUSE_TORRENT, SESSION_STATE_SINGLE_TORRENT),
        ]

        mocked_client.assert_has_calls(calls, any_order=False)
