"""Tests for PiKVM certificate and device verification helpers."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMTimeoutError,
)

from custom_components.pikvm_ha.cert_handler import (
    PiKVMResponse,
    fetch_serialized_cert,
    is_pikvm_device,
)


@pytest.mark.asyncio
async def test_fetch_serialized_cert_success(hass, pikvm_cert):
    """Test successfully fetching and serializing certificate."""
    with patch(
        "custom_components.pikvm_ha.cert_handler.fetch_remote_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ) as mock_fetch:
        result = await fetch_serialized_cert(hass, "https://pikvm.local")
        assert result == pikvm_cert
        mock_fetch.assert_awaited_once_with("https://pikvm.local", timeout=5.0)


@pytest.mark.asyncio
async def test_fetch_serialized_cert_network_failure(hass):
    """Test certificate fetch fails gracefully on network timeout or error."""
    with patch(
        "custom_components.pikvm_ha.cert_handler.fetch_remote_cert",
        new=AsyncMock(side_effect=TimeoutError("Timed out")),
    ):
        result = await fetch_serialized_cert(hass, "https://pikvm.local")
        assert result is None


@pytest.mark.asyncio
async def test_is_pikvm_device_success(hass, pikvm_cert):
    """Test verifying a valid PiKVM device."""
    mock_device = MagicMock()
    mock_device.serial = "PIKVM-1234"
    mock_device.model = "PiKVM V3"
    mock_device.name = "My PiKVM"

    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device),
    ):
        resp = await is_pikvm_device(
            hass, "https://pikvm.local", "admin", "secret", pikvm_cert
        )
        assert resp.success is True
        assert resp.model == "PiKVM V3"
        assert resp.serial == "pikvm-1234"
        assert resp.name == "My PiKVM"
        assert resp.error is None


@pytest.mark.asyncio
async def test_is_pikvm_device_fallbacks(hass, pikvm_cert):
    """Test fallbacks for model, serial, and name when properties are empty."""
    mock_device = MagicMock()
    mock_device.serial = None
    mock_device.model = None
    mock_device.name = None
    mock_device.get = MagicMock(return_value={})

    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device),
    ):
        resp = await is_pikvm_device(
            hass, "https://pikvm.local", "admin", "secret", pikvm_cert
        )
        assert resp.success is True
        assert resp.serial == "unknown"
        assert resp.model == "PiKVM"
        assert resp.name == "PiKVM"
        assert resp.error is None


@pytest.mark.asyncio
async def test_is_pikvm_device_hass_none(pikvm_cert):
    """Test is_pikvm_device works when hass is None (e.g. standalone calls)."""
    mock_device = MagicMock()
    mock_device.serial = "PIKVM-99"
    mock_device.model = "PiKVM V4"
    mock_device.name = "Standalone PiKVM"

    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device),
    ):
        resp = await is_pikvm_device(
            None, "https://pikvm.local", "admin", "secret", pikvm_cert
        )
        assert resp.success is True
        assert resp.serial == "pikvm-99"


@pytest.mark.asyncio
async def test_is_pikvm_device_auth_error(hass, pikvm_cert):
    """Test authentication error returning 403 response."""
    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(side_effect=PiKVMAuthenticationError("403 Forbidden")),
    ):
        resp = await is_pikvm_device(
            hass, "https://pikvm.local", "admin", "bad_pass", pikvm_cert
        )
        assert resp == PiKVMResponse(False, None, None, None, "Exception_HTTP403")


@pytest.mark.asyncio
async def test_is_pikvm_device_timeout_error(hass, pikvm_cert):
    """Test timeout error returning timeout response."""
    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(side_effect=PiKVMTimeoutError("Timed out")),
    ):
        resp = await is_pikvm_device(
            hass, "https://pikvm.local", "admin", "pass", pikvm_cert
        )
        assert resp == PiKVMResponse(False, None, None, None, "timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_cls",
    [PiKVMConnectionError, PiKVMDeviceError],
)
async def test_is_pikvm_device_connection_errors(hass, pikvm_cert, exception_cls):
    """Test connection and device errors returning cannot_connect response."""
    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(side_effect=exception_cls("Connection error")),
    ):
        resp = await is_pikvm_device(
            hass, "https://pikvm.local", "admin", "pass", pikvm_cert
        )
        assert resp == PiKVMResponse(False, None, None, None, "cannot_connect")


@pytest.mark.asyncio
async def test_is_pikvm_device_generic_exception(hass, pikvm_cert):
    """Test unexpected exception returning cannot_connect response."""
    with patch(
        "custom_components.pikvm_ha.cert_handler.PiKVMClient.get_info",
        new=AsyncMock(side_effect=RuntimeError("Unexpected error")),
    ):
        resp = await is_pikvm_device(
            hass, "https://pikvm.local", "admin", "pass", pikvm_cert
        )
        assert resp == PiKVMResponse(False, None, None, None, "cannot_connect")
