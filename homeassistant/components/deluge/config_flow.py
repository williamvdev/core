"""Config flow for Deluge integration."""
from __future__ import annotations

import logging
from typing import Any

from deluge_client import DelugeRPCClient
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import DEFAULT_PORT, DOMAIN, PASSWORD_ERROR_TEXT, USERNAME_ERROR_TEXT

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="seraph"): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            int, vol.Range(min=0)
        ),  # cv.port causes the ui to display a slider which isn't optimal ux in this case.
        vol.Required(CONF_USERNAME, default="homeassistant"): cv.string,
        vol.Required(CONF_PASSWORD, default="MonadGlobalBunBusRuddySeal"): cv.string,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Make a connection to Deluge daemon to check user input values."""
    client = DelugeRPCClient(
        data[CONF_HOST], data[CONF_PORT], data[CONF_USERNAME], data[CONF_PASSWORD]
    )
    await hass.async_add_executor_job(client.connect)
    client.disconnect()
    return {"title": f"Deluge Daemon on {data[CONF_HOST]}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Deluge."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle User step."""
        errors: dict[str, str] = {}
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        await self.async_set_unique_id(f"{user_input[CONF_HOST]}")
        self._abort_if_unique_id_configured()

        try:
            info = await validate_input(self.hass, user_input)
        except ConnectionError:
            errors["base"] = "cannot_connect"
        except Exception as err:  # pylint: disable=broad-except
            if (USERNAME_ERROR_TEXT in str(err)) or (PASSWORD_ERROR_TEXT in str(err)):
                errors["base"] = "invalid_auth"
            else:
                _LOGGER.exception("Unexpected exception: %s", str(err))
                errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
