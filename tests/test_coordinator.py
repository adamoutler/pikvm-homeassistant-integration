"""Tests for the PiKVM DataUpdateCoordinator."""

from unittest.mock import AsyncMock, patch
import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMDeviceInfo,
    PiKVMError,
    PiKVMTimeoutError,
)

from custom_components.pikvm_ha.coordinator import PiKVMDataUpdateCoordinator


@pytest.fixture
def mock_device_info():
    """Create a sample PiKVMDeviceInfo instance."""
    raw_data = {
        "hw": {
            "platform": {"type": "v3", "serial": "pikvm-1234"},
            "health": {"temp": {"cpu": 42.0}},
        },
        "system": {"kvmd": {"version": "3.1"}},
        "meta": {"server": {"name": "Test PiKVM", "host": "pikvm.local"}},
    }
    return PiKVMDeviceInfo.from_dict(raw_data)


@pytest.mark.asyncio
async def test_coordinator_successful_update(hass, mock_device_info):
    """Test successful data update from PiKVM."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    await coordinator.async_setup()

    coordinator.client.get_info = AsyncMock(return_value=mock_device_info)

    data = await coordinator._async_update_data()
    assert data == mock_device_info
    assert data.serial == "pikvm-1234"
    assert data.hw.platform.serial == "pikvm-1234"

    # Also test via async_refresh
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data == mock_device_info


@pytest.mark.asyncio
async def test_coordinator_authentication_error(hass):
    """Test authentication failure raises ConfigEntryAuthFailed."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="bad_password",
        totp="JBSWY3DPEHPK3PXP",
        cert="",
    )

    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMAuthenticationError("401 Unauthorized")
    )

    with pytest.raises(ConfigEntryAuthFailed) as exc_info:
        await coordinator._async_update_data()
    assert "Invalid credentials or 2FA TOTP token required" in str(exc_info.value)

    # Calling refresh should record failure
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_class,error_message,expected_fragment",
    [
        (PiKVMConnectionError, "Connection refused", "Cannot connect to pikvm.local"),
        (PiKVMTimeoutError, "Request timed out", "Connection timed out reaching pikvm.local"),
        (PiKVMDeviceError, "Internal error in KVMD", "Error communicating with PiKVM at pikvm.local"),
        (PiKVMError, "General error", "Error communicating with PiKVM at pikvm.local"),
    ],
)
async def test_coordinator_communication_errors(hass, error_class, error_message, expected_fragment):
    """Test communication and device errors raise sanitized UpdateFailed."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )

    coordinator.client.get_info = AsyncMock(side_effect=error_class(error_message))

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert expected_fragment in str(exc_info.value)
