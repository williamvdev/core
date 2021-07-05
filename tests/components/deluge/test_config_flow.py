"""Test the Deluge config flow."""
from unittest.mock import patch

from homeassistant import config_entries, setup
from homeassistant.components.deluge.const import (
    DOMAIN,
    PASSWORD_ERROR_TEXT,
    USERNAME_ERROR_TEXT,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import RESULT_TYPE_CREATE_ENTRY, RESULT_TYPE_FORM


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == RESULT_TYPE_FORM
    assert result["errors"] == {}

    with patch("deluge_client.DelugeRPCClient.connect", return_value=True,), patch(
        "deluge_client.DelugeRPCClient.disconnect",
        retun_value=True,
    ), patch(
        "homeassistant.components.deluge.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "port": 58846,
                "username": "test-username",
                "password": "test-password",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == RESULT_TYPE_CREATE_ENTRY
    assert result2["title"] == "Deluge Daemon on 1.1.1.1"
    assert result2["data"] == {
        "host": "1.1.1.1",
        "port": 58846,
        "username": "test-username",
        "password": "test-password",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_invalid_user(hass: HomeAssistant) -> None:
    """Test we handle invalid username."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "deluge_client.DelugeRPCClient.connect",
        side_effect=Exception(USERNAME_ERROR_TEXT),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "port": 58846,
                "username": "test-username",
                "password": "test-password",
            },
        )

    assert result2["type"] == RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_invalid_password(hass: HomeAssistant) -> None:
    """Test we handle invalid password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "deluge_client.DelugeRPCClient.connect",
        side_effect=Exception(PASSWORD_ERROR_TEXT),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "port": 58846,
                "username": "test-username",
                "password": "test-password",
            },
        )

    assert result2["type"] == RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "deluge_client.DelugeRPCClient.connect",
        side_effect=ConnectionError(),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "port": 58846,
                "username": "test-username",
                "password": "test-password",
            },
        )

    assert result2["type"] == RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_unknown_error(hass: HomeAssistant) -> None:
    """Test we handle cannot unexpected errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "deluge_client.DelugeRPCClient.connect",
        side_effect=Exception("Unknown Exception"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "1.1.1.1",
                "port": 58846,
                "username": "test-username",
                "password": "test-password",
            },
        )

    assert result2["type"] == RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "unknown"}
