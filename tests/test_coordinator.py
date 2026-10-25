"""Tests for the PiKVM DataUpdateCoordinator."""

import logging
import ssl
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMDeviceInfo,
    PiKVMError,
    PiKVMTimeoutError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.const import DOMAIN
from custom_components.pikvm.coordinator import PiKVMDataUpdateCoordinator


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
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "authentication_error"
    assert exc_info.value.translation_placeholders == {"host": "pikvm.local"}

    # Calling refresh should record failure
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_class,error_message,expected_fragment,expected_key,expected_placeholders",
    [
        (
            PiKVMConnectionError,
            "Connection refused",
            "Cannot connect to pikvm.local",
            "cannot_connect",
            {"host": "pikvm.local"},
        ),
        (
            PiKVMTimeoutError,
            "Request timed out",
            "Connection timed out reaching pikvm.local",
            "timeout",
            {"host": "pikvm.local"},
        ),
        (
            TimeoutError,
            "Builtin timeout",
            "Connection timed out reaching pikvm.local",
            "timeout",
            {"host": "pikvm.local"},
        ),
        (
            PiKVMDeviceError,
            "Internal error in KVMD",
            "Error communicating with PiKVM at pikvm.local",
            "communication_error",
            {"host": "pikvm.local", "error": "Internal error in KVMD"},
        ),
        (
            PiKVMError,
            "General error",
            "Error communicating with PiKVM at pikvm.local",
            "communication_error",
            {"host": "pikvm.local", "error": "General error"},
        ),
    ],
)
async def test_coordinator_communication_errors(
    hass,
    error_class,
    error_message,
    expected_fragment,
    expected_key,
    expected_placeholders,
):
    """Test communication and device errors raise sanitized UpdateFailed with translations."""
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
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == expected_key
    assert exc_info.value.translation_placeholders == expected_placeholders


@pytest.mark.asyncio
async def test_coordinator_parse_host_port_exception(hass):
    """Test clean_host fallback when parse_host_port raises an Exception (covers lines 65-66)."""
    with patch(
        "custom_components.pikvm.coordinator.parse_host_port",
        side_effect=Exception("Failed parsing host"),
    ):
        coordinator = PiKVMDataUpdateCoordinator(
            hass=hass,
            url="https://pikvm-custom.local:8443/api",
            username="admin",
            password="password",
            totp="",
            cert="",
        )
        assert coordinator.clean_host == "pikvm-custom.local:8443"


@pytest.mark.asyncio
async def test_coordinator_init_scan_interval_from_entry_options(hass):
    """Test coordinator uses scan interval from entry options and populates ssl_cert."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={CONF_SCAN_INTERVAL: 15},
        data={CONF_SCAN_INTERVAL: 60},
    )
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="dummy_cert_pem",
        entry=entry,
    )
    assert coordinator.update_interval == timedelta(seconds=15)
    assert coordinator.config_entry == entry
    assert coordinator.client.ssl_cert == "dummy_cert_pem"


@pytest.mark.asyncio
async def test_coordinator_init_scan_interval_from_entry_data(hass):
    """Test coordinator uses scan interval from entry data when options is empty."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={},
        data={CONF_SCAN_INTERVAL: 45},
    )
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )
    assert coordinator.update_interval == timedelta(seconds=45)


@pytest.mark.asyncio
async def test_coordinator_init_scan_interval_default(hass):
    """Test coordinator uses default scan interval when not in entry options or data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={},
        data={},
    )
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )
    assert coordinator.update_interval == timedelta(seconds=30)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "throttling_data",
    [
        {"voltage": {"core": {"now": True}}},
        {"raw_flags": 0x1},
        {"text_flags": ["under-voltage"]},
    ],
)
async def test_coordinator_hardware_health_undervoltage_critical(hass, throttling_data):
    """Test undervoltage issue created with CRITICAL severity when active now."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_uv_now", title="PiKVM")
    entry.add_to_hass(hass)
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )

    data = {
        "hw": {
            "health": {
                "throttling": throttling_data,
            }
        }
    }

    coordinator._async_check_hardware_health(data)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, f"undervoltage_{entry.entry_id}")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.CRITICAL
    assert issue.translation_key == "undervoltage"
    assert issue.translation_placeholders == {"device_name": "PiKVM"}
    assert issue.learn_more_url == "https://docs.pikvm.org/power/"
    assert issue.is_fixable is False
    assert issue.is_persistent is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "throttling_data",
    [
        {"voltage": {"core": {"now": False, "past": True}}},
        {"raw_flags": 0x10000},
    ],
)
async def test_coordinator_hardware_health_undervoltage_warning_past(hass, throttling_data):
    """Test undervoltage issue created with WARNING severity when occurred in the past."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_uv_past", title="PiKVM")
    entry.add_to_hass(hass)
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )

    data = {
        "hw": {
            "health": {
                "throttling": throttling_data,
            }
        }
    }

    coordinator._async_check_hardware_health(data)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, f"undervoltage_{entry.entry_id}")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == "undervoltage"
    assert issue.translation_placeholders == {"device_name": "PiKVM"}
    assert issue.learn_more_url == "https://docs.pikvm.org/power/"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "throttling_data",
    [
        {"raw_flags": 0x2},
        {"raw_flags": 0x4},
        {"text_flags": ["throttled"]},
        {"text_flags": ["arm-frequency-capped"]},
        {"raw_flags": 0x20000},
        {"raw_flags": 0x40000},
    ],
)
async def test_coordinator_hardware_health_throttling_issue_creation(hass, throttling_data):
    """Test throttling issue created with WARNING severity for active or past throttling."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_throttle", title="PiKVM")
    entry.add_to_hass(hass)
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )

    data = {
        "hw": {
            "health": {
                "throttling": throttling_data,
            }
        }
    }

    coordinator._async_check_hardware_health(data)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, f"throttling_{entry.entry_id}")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == "throttling"
    assert issue.translation_placeholders == {"device_name": "PiKVM"}
    assert issue.learn_more_url == "https://docs.pikvm.org/"
    assert issue.is_fixable is False
    assert issue.is_persistent is False


@pytest.mark.asyncio
async def test_coordinator_hardware_health_issue_deletion(hass):
    """Test existing undervoltage and throttling issues are removed when health recovers."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_recovery")
    entry.add_to_hass(hass)
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )

    # 1. Trigger issues
    unhealthy_data = {
        "hw": {
            "health": {
                "throttling": {
                    "voltage": {"core": {"now": True}},
                    "text_flags": ["throttled"],
                }
            }
        }
    }
    coordinator._async_check_hardware_health(unhealthy_data)

    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, f"undervoltage_{entry.entry_id}") is not None
    assert issue_registry.async_get_issue(DOMAIN, f"throttling_{entry.entry_id}") is not None

    # 2. Recover: clear flags and voltages
    healthy_data = {
        "hw": {
            "health": {
                "throttling": {
                    "raw_flags": 0,
                    "text_flags": [],
                    "voltage": {"core": {"now": False, "past": False}},
                }
            }
        }
    }
    coordinator._async_check_hardware_health(healthy_data)

    # 3. Assert deleted
    assert issue_registry.async_get_issue(DOMAIN, f"undervoltage_{entry.entry_id}") is None
    assert issue_registry.async_get_issue(DOMAIN, f"throttling_{entry.entry_id}") is None


@pytest.mark.asyncio
async def test_coordinator_hardware_health_empty_entry_id(hass):
    """Test _async_check_hardware_health returns early when entry_id is empty."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=None,
    )
    coordinator.clean_host = ""

    unhealthy_data = {
        "hw": {
            "health": {
                "throttling": {
                    "voltage": {"core": {"now": True}},
                    "text_flags": ["throttled"],
                }
            }
        }
    }

    with patch("custom_components.pikvm.coordinator.async_create_issue") as mock_create_issue, patch(
        "custom_components.pikvm.coordinator.async_delete_issue"
    ) as mock_delete_issue:
        coordinator._async_check_hardware_health(unhealthy_data)
        mock_create_issue.assert_not_called()
        mock_delete_issue.assert_not_called()


@pytest.mark.asyncio
async def test_coordinator_hardware_health_no_config_entry_uses_clean_host(hass):
    """Test _async_check_hardware_health uses clean_host when config_entry is None."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=None,
    )

    unhealthy_data = {
        "hw": {
            "health": {
                "throttling": {
                    "voltage": {"core": {"now": True}},
                }
            }
        }
    }
    coordinator._async_check_hardware_health(unhealthy_data)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "undervoltage_pikvm.local")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.CRITICAL


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_data", [None, "invalid_string", 12345])
async def test_coordinator_hardware_health_non_dict_fallback(hass, invalid_data):
    """Test _async_check_hardware_health gracefully handles non-dict data without .raw attribute."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=None,
    )

    coordinator._async_check_hardware_health(invalid_data)

    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, "undervoltage_pikvm.local") is None
    assert issue_registry.async_get_issue(DOMAIN, "throttling_pikvm.local") is None


@pytest.mark.asyncio
async def test_coordinator_update_data_triggers_hardware_health(hass):
    """Test _async_update_data invokes _async_check_hardware_health during polling."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_update_health")
    entry.add_to_hass(hass)
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry,
    )

    unhealthy_info = PiKVMDeviceInfo.from_dict({
        "hw": {
            "platform": {"type": "v3", "serial": "sn123"},
            "health": {
                "throttling": {
                    "text_flags": ["under-voltage", "throttled"],
                }
            },
        },
        "system": {"kvmd": {"version": "3.1"}},
        "meta": {"server": {"name": "PiKVM", "host": "pikvm.local"}},
    })

    coordinator.client.get_info = AsyncMock(return_value=unhealthy_info)

    data = await coordinator._async_update_data()
    assert data == unhealthy_info

    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, f"undervoltage_{entry.entry_id}") is not None
    assert issue_registry.async_get_issue(DOMAIN, f"throttling_{entry.entry_id}") is not None


@pytest.mark.asyncio
async def test_coordinator_ssl_and_malformed_health_data(hass):
    """Test ssl.SSLError handling and non-dict throttling/text_flags/voltage_core in coordinator."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )

    coordinator.client.get_info = AsyncMock(side_effect=ssl.SSLError("bad cert"))
    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "SSL certificate validation failed" in str(exc_info.value)
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "ssl_certificate_error"
    assert exc_info.value.translation_placeholders == {"host": "pikvm.local"}

    coordinator._async_check_hardware_health({"hw": {"health": {"throttling": "invalid"}}})
    coordinator._async_check_hardware_health(
        {
            "hw": {
                "health": {
                    "throttling": {
                        "raw_flags": 0,
                        "text_flags": "not-a-list",
                        "voltage": {"core": "not-a-dict"},
                    }
                }
            }
        }
    )
    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, "undervoltage_pikvm.local") is None


@pytest.mark.asyncio
async def test_coordinator_device_name_resolution(hass):
    """Test coordinator.device_name resolution under various scenarios."""
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.device_registry import DeviceInfo

    dev_reg = dr.async_get(hass)

    # 1. No config entry, device_info, or data -> fallback "PiKVM"
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://192.168.1.50",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    assert coordinator.device_name == "PiKVM"

    # 2. With data.name (and not localhost)
    mock_data = MagicMock()
    mock_data.name = "My Discovered KVM"
    coordinator.data = mock_data
    assert coordinator.device_name == "My Discovered KVM"

    # 3. With generic data.name ("localhost") -> falls through
    mock_data.name = "localhost"
    assert coordinator.device_name == "PiKVM"

    # 4. With device_info
    coordinator.device_info = DeviceInfo(identifiers={(DOMAIN, "sn1")}, name="PiKVM V4 Plus")
    assert coordinator.device_name == "PiKVM V4 Plus"

    # 5. With config entry title
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_name", title="Custom Title")
    entry.add_to_hass(hass)
    coordinator.config_entry = entry
    assert coordinator.device_name == "Custom Title"

    # 6. With device registry entry (dev.name)
    dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_dev")},
        name="Device Registry Name",
    )
    assert coordinator.device_name == "Device Registry Name"

    # 7. With user-customized device name (dev.name_by_user)
    dev_reg.async_update_device(dev.id, name_by_user="User Custom Name")
    assert coordinator.device_name == "User Custom Name"

    # 8. Strips legacy clean_host suffix (e.g. "PiKVM (192.168.1.50)" -> "PiKVM")
    dev_reg.async_update_device(dev.id, name_by_user=None, name="PiKVM (192.168.1.50)")
    assert coordinator.device_name == "PiKVM"

    # 9. Device entry with dev.name is None (exercises branch 122->119)
    entry_noname = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_noname", title="")
    entry_noname.add_to_hass(hass)
    coordinator_noname = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://192.168.1.50",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=entry_noname,
    )
    dev_reg.async_get_or_create(
        config_entry_id=entry_noname.entry_id,
        identifiers={(DOMAIN, "sn_noname1")},
        name=None,
    )
    dev_reg.async_get_or_create(
        config_entry_id=entry_noname.entry_id,
        identifiers={(DOMAIN, "sn_noname2")},
        name="Second Device",
    )
    assert coordinator_noname.device_name == "Second Device"

    # 10. Device entry matching only suffix " (192.168.1.50)" resulting in cleaned == "" (exercises branch 143->146)
    dev_reg.async_update_device(dev.id, name_by_user=None, name=" (192.168.1.50)")
    assert coordinator.device_name == " (192.168.1.50)"


@pytest.mark.asyncio
async def test_coordinator_log_when_unavailable_auth_failure(hass, caplog):
    """Verify log-when-unavailable compliance for authentication failure."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="bad_password",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMAuthenticationError("401 Unauthorized")
    )

    # First refresh: Home Assistant DataUpdateCoordinator logs 1 ERROR
    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    error_logs = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(error_logs) == 1

    # Second refresh: coordinator.py demoted to debug, DataUpdateCoordinator suppresses duplicate log -> 0 ERROR logs
    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    error_logs = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(error_logs) == 0

    # Third refresh (recovery): logs 0 ERROR logs
    mock_data = MagicMock(spec=PiKVMDeviceInfo)
    mock_data.raw = {}
    coordinator.client.get_info = AsyncMock(return_value=mock_data)
    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    error_logs = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(error_logs) == 0


@pytest.mark.asyncio
async def test_coordinator_debug_logging_emits_diagnostics(hass, caplog):
    """Verify debug logging captures diagnostic info when log level is DEBUG."""
    caplog.set_level(logging.DEBUG)
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="bad_password",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMAuthenticationError("401 Unauthorized")
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    debug_logs = [
        record.message
        for record in caplog.records
        if record.levelname == "DEBUG"
        and "Authentication failed for PiKVM at https://pikvm.local" in record.message
    ]
    assert len(debug_logs) == 1




