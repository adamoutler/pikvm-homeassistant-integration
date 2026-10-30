"""Tests for the PiKVM diagnostics platform."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.pikvm.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


def test_diagnostics_redact_set_contains_required_keys():
    """Verify TO_REDACT includes all sensitive credential and session keys."""
    for required in (
        CONF_PASSWORD,
        CONF_TOTP,
        CONF_CERTIFICATE,
        "password",
        "totp",
        "token",
        "secret",
        "api_key",
        "cookie",
        "jwt",
    ):
        assert required in TO_REDACT


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

    entry.runtime_data = mock_coordinator

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
    """Test diagnostics output when coordinator is not set on runtime_data."""
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

    entry.runtime_data = mock_coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["coordinator"]["data"] == {"hw": {"serial": "123"}}

    # Test when coordinator.data is None
    mock_coordinator.data = None
    diagnostics_none = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics_none["coordinator"]["data"] is None


@pytest.mark.asyncio
async def test_diagnostics_with_non_dict_non_raw_data(hass):
    """Test diagnostics when coordinator.data is a non-dict scalar without a raw attribute."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pikvm_scalar",
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
    mock_coordinator.data = "unexpected_scalar"

    entry.runtime_data = mock_coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["coordinator"]["data"] is None


@pytest.mark.asyncio
async def test_device_diagnostics_with_device_registry(hass):
    """Test device diagnostics output and redaction with a registered device and coordinator runtime data."""
    from homeassistant.helpers import device_registry as dr

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
        "auth": {
            "password": "nested_password",
            "totp": "nested_totp",
            "token": "secret_token",
            "api_key": "secret_key",
        },
        "system": {"version": "3.1"},
    }

    entry.runtime_data = mock_coordinator

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "pikvm_123456")},
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        manufacturer="PiKVM",
        model="V3.3",
        sw_version="3.100",
        hw_version="Raspberry Pi 4",
        serial_number="pikvm_123456",
    )
    dev_reg.async_update_device(device.id, name_by_user="Custom PiKVM Name")
    device = dev_reg.async_get(device.id)

    diagnostics = await async_get_device_diagnostics(hass, entry, device)

    # 1. Verify config entry credentials and certificates are redacted
    assert diagnostics["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_TOTP] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_CERTIFICATE] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"][CONF_HOST] == "https://pikvm.local"
    assert diagnostics["config_entry"]["data"][CONF_USERNAME] == "admin"

    # 2. Verify coordinator sensitive keys are redacted
    coord_diag = diagnostics["coordinator"]
    assert coord_diag["last_update_success"] is True
    assert coord_diag["update_interval"] == "0:00:30"
    assert coord_diag["data"]["auth"]["password"] == "**REDACTED**"
    assert coord_diag["data"]["auth"]["totp"] == "**REDACTED**"
    assert coord_diag["data"]["auth"]["token"] == "**REDACTED**"
    assert coord_diag["data"]["auth"]["api_key"] == "**REDACTED**"
    assert coord_diag["data"]["system"]["version"] == "3.1"

    # 3. Verify extracted device attributes via dict_repr
    dev_diag = diagnostics["device"]
    assert dev_diag["id"] == device.id
    assert dev_diag["name"] == device.name
    assert dev_diag["name_by_user"] == "Custom PiKVM Name"
    assert (DOMAIN, "pikvm_123456") in dev_diag["identifiers"]
    assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in dev_diag["connections"]
    assert dev_diag["manufacturer"] == "PiKVM"
    assert dev_diag["model"] == "V3.3"
    assert dev_diag["sw_version"] == "3.100"
    assert dev_diag["hw_version"] == "Raspberry Pi 4"
    assert dev_diag["serial_number"] == "pikvm_123456"
    assert dev_diag["disabled_by"] is None


@pytest.mark.asyncio
async def test_device_diagnostics_disabled_device(hass):
    """Test device diagnostics reports disabled_by status correctly when device is disabled."""
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pikvm_disabled",
        data={CONF_HOST: "https://pikvm.local", CONF_USERNAME: "admin"},
    )
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "pikvm_disabled")},
        name="Disabled PiKVM",
    )
    dev_reg.async_update_device(device.id, disabled_by=dr.DeviceEntryDisabler.USER)
    device = dev_reg.async_get(device.id)

    diagnostics = await async_get_device_diagnostics(hass, entry, device)

    assert diagnostics["device"]["id"] == device.id
    assert diagnostics["device"]["disabled_by"] == dr.DeviceEntryDisabler.USER
