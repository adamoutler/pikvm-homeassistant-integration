"""Tests for the PiKVM diagnostics platform."""

from unittest.mock import MagicMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.pikvm_ha.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_with_coordinator(hass):
    """Test diagnostics output when coordinator is active and verify sensitive data is redacted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pikvm_123456",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "super_secret_password",
            CONF_TOTP: "JBSWY3DPEHPK3PXP",
            CONF_CERTIFICATE: "-----BEGIN CERTIFICATE-----\nSECRET_CERT\n-----END CERTIFICATE-----",
            CONF_SERIAL: "pikvm_123456",
        },
    )
    entry.add_to_hass(hass)

    mock_coordinator = MagicMock()
    mock_coordinator.last_update_success = True
    mock_coordinator.update_interval = "0:00:30"
    mock_coordinator.data = MagicMock()
    mock_coordinator.data.raw = {
        "hw": {"platform": {"type": "v3", "serial": "pikvm_123456"}},
        "auth": {"password": "nested_secret", "totp": "nested_totp"},
        "system": {"version": "3.1"},
    }

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Ensure config entry fields are redacted
    assert diagnostics["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_TOTP] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_CERTIFICATE] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_HOST] == "https://pikvm.local"
    assert diagnostics["config_entry"]["data"][CONF_USERNAME] == "admin"

    # Ensure coordinator data is redacted
    coordinator_diag = diagnostics["coordinator"]
    assert coordinator_diag["last_update_success"] is True
    assert coordinator_diag["data"]["auth"]["password"] == "**REDACTED**"
    assert coordinator_diag["data"]["auth"]["totp"] == "**REDACTED**"
    assert coordinator_diag["data"]["system"]["version"] == "3.1"


@pytest.mark.asyncio
async def test_diagnostics_without_coordinator(hass):
    """Test diagnostics output when coordinator is not in hass.data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pikvm_999",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
        },
    )
    entry.add_to_hass(hass)

    # Ensure DOMAIN has no coordinator for this entry
    hass.data.setdefault(DOMAIN, {})

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["coordinator"] == {}


@pytest.mark.asyncio
async def test_diagnostics_with_dict_data_and_none_data(hass):
    """Test diagnostics with plain dict data and when coordinator data is None."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pikvm_dict",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
        },
    )
    entry.add_to_hass(hass)

    mock_coordinator = MagicMock()
    mock_coordinator.last_update_success = True
    mock_coordinator.update_interval = "0:00:30"
    mock_coordinator.data = {"hw": {"serial": "123"}}

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["coordinator"]["data"] == {"hw": {"serial": "123"}}

    # Test when coordinator.data is None
    mock_coordinator.data = None
    diagnostics_none = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics_none["coordinator"]["data"] is None
