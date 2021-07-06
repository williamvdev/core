"""Test the Coinbase integration."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.coinbase.const import (
    CONF_CURRENCIES,
    CONF_EXCHANGE_RATES,
    CONF_YAML_API_TOKEN,
    DOMAIN,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.setup import async_setup_component

from .common import (
    init_mock_coinbase,
    mock_get_current_user,
    mock_get_exchange_rates,
    mocked_get_accounts,
)
from .const import (
    GOOD_CURRENCY,
    GOOD_CURRENCY_2,
    GOOD_EXCHNAGE_RATE,
    GOOD_EXCHNAGE_RATE_2,
)


async def test_setup(hass):
    """Test setting up from configuration.yaml."""
    conf = {
        DOMAIN: {
            CONF_API_KEY: "123456",
            CONF_YAML_API_TOKEN: "AbCDeF",
            CONF_CURRENCIES: [GOOD_CURRENCY, GOOD_CURRENCY_2],
            CONF_EXCHANGE_RATES: [GOOD_EXCHNAGE_RATE, GOOD_EXCHNAGE_RATE_2],
        }
    }
    with patch(
        "coinbase.wallet.client.Client.get_current_user",
        return_value=mock_get_current_user(),
    ), patch(
        "coinbase.wallet.client.Client.get_accounts",
        new=mocked_get_accounts,
    ), patch(
        "coinbase.wallet.client.Client.get_exchange_rates",
        return_value=mock_get_exchange_rates(),
    ):
        assert await async_setup_component(hass, DOMAIN, conf)
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].title == "Test User"
        assert entries[0].source == config_entries.SOURCE_IMPORT
        assert entries[0].options == {
            CONF_CURRENCIES: [GOOD_CURRENCY, GOOD_CURRENCY_2],
            CONF_EXCHANGE_RATES: [GOOD_EXCHNAGE_RATE, GOOD_EXCHNAGE_RATE_2],
        }


async def test_unload_entry(hass):
    """Test successful unload of entry."""
    with patch(
        "coinbase.wallet.client.Client.get_current_user",
        return_value=mock_get_current_user(),
    ), patch(
        "coinbase.wallet.client.Client.get_accounts",
        new=mocked_get_accounts,
    ), patch(
        "coinbase.wallet.client.Client.get_exchange_rates",
        return_value=mock_get_exchange_rates(),
    ):
        entry = await init_mock_coinbase(hass)

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.state == config_entries.ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == config_entries.ConfigEntryState.NOT_LOADED
    assert not hass.data.get(DOMAIN)
