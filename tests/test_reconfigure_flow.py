"""Tests for PiKVM config flow reconfiguration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.cert_handler import PiKVMResponse
from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
)


@pytest.fixture
def mock_entry(hass):
    """Create a configured mock entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="reconfig_entry_1",
        unique_id="pikvm_sn_original",
        data={
            CONF_HOST: "https://192.168.1.10",
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD,
            CONF_TOTP: "",
            CONF_SERIAL: "pikvm_sn_original",
            CONF_CERTIFICATE: "cert_original",
            CONF_MODEL: "v3",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_reconfigure_flow_init(hass, mock_entry):
    """Test reconfigure flow initialization displays form with default host."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_confirm"
    assert result["description_placeholders"]["host"] == "192.168.1.10"


@pytest.mark.asyncio
async def test_reconfigure_flow_success(hass, mock_entry):
    """Test successful reconfiguration of host and credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="new_cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="v4_plus",
                serial="pikvm_sn_original",
                name="PiKVM Lab",
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.50",
                CONF_PORT: 443,
                CONF_USERNAME: "new_admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )

        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"
        assert mock_entry.data[CONF_HOST] == "https://192.168.1.50:443"
        assert mock_entry.data[CONF_USERNAME] == "new_admin"
        assert mock_entry.data[CONF_PASSWORD] == "new_password"
        assert mock_entry.data[CONF_CERTIFICATE] == "new_cert"
        assert mock_entry.data[CONF_MODEL] == "v4_plus"


@pytest.mark.asyncio
async def test_reconfigure_flow_with_totp_success(hass, mock_entry):
    """Test successful reconfiguration with valid base32 TOTP secret."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="new_cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model=None,
                serial="pikvm_sn_original",
                name=None,
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.50:443",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "JBSWY3DPEHPK3PXP",
            },
        )

        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"
        assert mock_entry.data[CONF_TOTP] == "JBSWY3DPEHPK3PXP"


@pytest.mark.asyncio
async def test_reconfigure_flow_invalid_totp(hass, mock_entry):
    """Test reconfigure flow rejects invalid TOTP secret."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "https://192.168.1.50",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_TOTP: "invalid_not_base32!",
        },
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_totp"


@pytest.mark.asyncio
async def test_reconfigure_flow_cannot_fetch_cert(hass, mock_entry):
    """Test reconfigure flow error when cert fetch fails."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=""),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.50",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"]["base"] == "cannot_fetch_cert"


@pytest.mark.asyncio
async def test_reconfigure_flow_cannot_connect(hass, mock_entry):
    """Test reconfigure flow error when device connection fails."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="new_cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=False,
                model=None,
                serial=None,
                name=None,
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.50",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_reconfigure_flow_response_error(hass, mock_entry):
    """Test reconfigure flow error when device returns explicit error code."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="new_cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=False,
                model=None,
                serial=None,
                name=None,
                error="Exception_HTTP403",
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.50",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong_password",
                CONF_TOTP: "",
            },
        )

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"]["base"] == "Exception_HTTP403"


@pytest.mark.asyncio
async def test_reconfigure_flow_unique_id_mismatch(hass, mock_entry):
    """Test reconfigure flow aborts if reconfigured host points to a different physical device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="new_cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="v3",
                serial="different_device_serial",
                name="Other PiKVM",
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.99",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )

        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] in ("unique_id_mismatched", "cannot_connect")


@pytest.mark.asyncio
async def test_reconfigure_flow_port_already_in_host(hass, mock_entry):
    """Test reconfigure flow when port is already included in host (line 414 branch)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
    )

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="valid_cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="v3",
                serial=mock_entry.data[CONF_SERIAL],
                name="PiKVM",
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.100:443",
                CONF_PORT: 443,
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )
        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"


@pytest.mark.asyncio
async def test_reconfigure_confirm_no_reconfigure_entry(hass):
    """Test async_step_reconfigure_confirm when _get_reconfigure_entry is None (line 463 branch)."""
    from custom_components.pikvm.config_flow import PiKVMConfigFlow

    flow = PiKVMConfigFlow()
    flow.hass = hass

    with patch.object(flow, "_get_reconfigure_entry", return_value=None):
        result = await flow.async_step_reconfigure_confirm()
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure_confirm"

