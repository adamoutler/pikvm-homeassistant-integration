"""Tests for the PiKVM config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pikvm_ha.cert_handler import PiKVMResponse
from custom_components.pikvm_ha.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_config_flow_user_success(hass):
    """Test a full successful user initiated config flow."""
    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }

    response = PiKVMResponse(True, "v3", "pikvm-1234", "My PiKVM", None)

    with patch(
        "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="dummy-cert"),
    ) as mock_fetch, patch(
        "custom_components.pikvm_ha.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=response),
    ) as mock_is_pikvm:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=user_input,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "My PiKVM"
    assert result["data"][CONF_CERTIFICATE] == "dummy-cert"
    assert result["data"][CONF_SERIAL] == "pikvm-1234"
    assert result["data"][CONF_MODEL] == "v3"
    mock_fetch.assert_awaited_once()
    mock_is_pikvm.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_flow_user_cannot_connect(hass):
    """Test the user step when the device cannot be reached."""
    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }

    failure = PiKVMResponse(False, None, None, None, "cannot_connect")

    with patch(
        "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="dummy-cert"),
    ), patch(
        "custom_components.pikvm_ha.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=failure),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=user_input,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"