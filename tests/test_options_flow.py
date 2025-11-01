"""Tests for the PiKVM options flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_options_flow_updates_entry(hass):
    """Ensure that options flow updates credentials and certificate."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "https://old-host",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: DEFAULT_PASSWORD,
            CONF_SERIAL: "old-serial",
            CONF_CERTIFICATE: "old-cert",
        },
    )
    config_entry.add_to_hass(hass)

    init_result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM

    new_user_input = {
        CONF_HOST: "pikvm.local",
        CONF_USERNAME: "new_admin",
        CONF_PASSWORD: "new_secret",
    }

    with patch(
        "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="new-cert"),
    ), patch(
        "custom_components.pikvm_ha.options_flow.is_pikvm_device",
        new=AsyncMock(return_value=(True, "pikvm-9999", "My PiKVM")),
    ):
        result = await hass.config_entries.options.async_configure(
            init_result["flow_id"],
            user_input=new_user_input,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert config_entry.data[CONF_HOST] == "pikvm.local"
    assert config_entry.data[CONF_USERNAME] == "new_admin"
    assert config_entry.data[CONF_PASSWORD] == "new_secret"
    assert config_entry.data[CONF_SERIAL] == "pikvm-9999"
    assert config_entry.data[CONF_CERTIFICATE] == "new-cert"
