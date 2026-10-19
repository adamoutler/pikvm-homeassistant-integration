"""Adversarial challenger tests for Milestone 3 (Coordinator & Exception Translations)."""

from __future__ import annotations

import json
import logging
import ssl
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMDeviceInfo,
    PiKVMError,
    PiKVMTimeoutError,
    parse_host_port,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.const import DOMAIN
from custom_components.pikvm.coordinator import PiKVMDataUpdateCoordinator


# -----------------------------------------------------------------------------
# Challenge 1: Exception Translation Parameters Verification
# -----------------------------------------------------------------------------
def load_strings_exceptions() -> dict[str, dict[str, str]]:
    """Load exception definitions from strings.json and translations/en.json."""
    strings_path = Path(__file__).parent.parent / "custom_components" / "pikvm" / "strings.json"
    en_path = Path(__file__).parent.parent / "custom_components" / "pikvm" / "translations" / "en.json"

    with strings_path.open() as f:
        strings_data = json.load(f)
    with en_path.open() as f:
        en_data = json.load(f)

    assert "exceptions" in strings_data, "strings.json missing 'exceptions' key"
    assert "exceptions" in en_data, "translations/en.json missing 'exceptions' key"

    # Verify synchronization between strings.json and en.json for exceptions
    assert strings_data["exceptions"] == en_data["exceptions"], (
        "strings.json and translations/en.json exceptions are out of sync"
    )

    return strings_data["exceptions"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised_exception,expected_exc_type,expected_key",
    [
        (PiKVMAuthenticationError("401 Unauthorized"), ConfigEntryAuthFailed, "authentication_error"),
        (TimeoutError("Asyncio timeout"), UpdateFailed, "timeout"),
        (PiKVMTimeoutError("PiKVM timeout"), UpdateFailed, "timeout"),
        (ssl.SSLError("CERTIFICATE_VERIFY_FAILED"), UpdateFailed, "ssl_certificate_error"),
        (PiKVMConnectionError("Connection refused"), UpdateFailed, "cannot_connect"),
        (aiohttp.ClientError("Client connection reset"), UpdateFailed, "cannot_connect"),
        (OSError("Host unreachable [Errno 113]"), UpdateFailed, "cannot_connect"),
        (PiKVMDeviceError("KVMD internal 500 error"), UpdateFailed, "communication_error"),
        (PiKVMError("General unhandled PiKVM error"), UpdateFailed, "communication_error"),
    ],
)
async def test_coordinator_exception_translations_rigorous(
    hass,
    raised_exception: Exception,
    expected_exc_type: type[Exception],
    expected_key: str,
):
    """Trigger all failure modes in _async_update_data and verify translation parameters."""
    defined_exceptions = load_strings_exceptions()
    assert expected_key in defined_exceptions, f"Key {expected_key} not in strings.json['exceptions']"

    raw_message_template = defined_exceptions[expected_key]["message"]

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm-test.local:8443",
        username="admin",
        password="secret_password",
        totp="JBSWY3DPEHPK3PXP",  # valid base32 TOTP secret
        cert="",
    )
    coordinator.client.get_info = AsyncMock(side_effect=raised_exception)

    with pytest.raises(expected_exc_type) as exc_info:
        await coordinator._async_update_data()

    exc = exc_info.value

    # 1. Assert translation_domain
    assert getattr(exc, "translation_domain", None) == DOMAIN, (
        f"Expected translation_domain '{DOMAIN}', got '{getattr(exc, 'translation_domain', None)}'"
    )

    # 2. Assert translation_key
    assert getattr(exc, "translation_key", None) == expected_key, (
        f"Expected translation_key '{expected_key}', got '{getattr(exc, 'translation_key', None)}'"
    )

    # 3. Assert translation_placeholders
    placeholders = getattr(exc, "translation_placeholders", None)
    assert isinstance(placeholders, dict), f"translation_placeholders is not a dict: {placeholders}"

    # Verify placeholder formatting works without error
    try:
        formatted_message = raw_message_template.format(**placeholders)
        assert len(formatted_message) > 0
    except KeyError as k_err:
        pytest.fail(f"Missing required placeholder key '{k_err}' for template '{raw_message_template}'")
    except ValueError as fmt_err:
        pytest.fail(f"Failed to format exception template '{raw_message_template}' with {placeholders}: {fmt_err}")

    # Verify placeholders are valid strings and not empty
    for k, v in placeholders.items():
        assert isinstance(v, str), f"Placeholder {k} is not a string: {v!r}"
        assert len(v.strip()) > 0, f"Placeholder {k} is blank: {v!r}"

    # Verify clean_host is passed as host
    assert placeholders.get("host") == coordinator.clean_host
    if expected_key == "communication_error":
        assert placeholders.get("error") == str(raised_exception)


# -----------------------------------------------------------------------------
# Challenge 2: Logging Behavior Under log-when-unavailable
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: PiKVMAuthenticationError("401 Bad Credentials"),
        lambda: PiKVMConnectionError("Host is unreachable"),
        lambda: PiKVMTimeoutError("Poll timeout"),
        lambda: ssl.SSLError("Untrusted self-signed certificate"),
        lambda: PiKVMDeviceError("Internal server error 500"),
    ],
)
async def test_coordinator_log_when_unavailable_consecutive_suppression(
    hass, caplog, error_factory
):
    """Assert initial poll logs ERROR, consecutive polls emit NO duplicate ERRORs, and recovery emits 0 ERRORs."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )

    # Mock failure
    coordinator.client.get_info = AsyncMock(side_effect=error_factory())

    # --- Poll 1: Initial failure ---
    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    error_records_p1 = [r for r in caplog.records if r.levelname == "ERROR"]
    # The integration's coordinator module itself must NOT emit direct ERROR logs from coordinator.py
    # (only HA core DataUpdateCoordinator logs the single error from update_coordinator.py)
    coordinator_py_errors = [
        r for r in error_records_p1 if Path(r.pathname).name == "coordinator.py"
    ]
    assert len(coordinator_py_errors) == 0, (
        f"coordinator.py directly emitted ERROR logs: {coordinator_py_errors}"
    )
    # Total error logs should be exactly 1 (from homeassistant's update_coordinator)
    assert len(error_records_p1) == 1, (
        f"Expected exactly 1 ERROR log on initial failure, got {len(error_records_p1)}: {error_records_p1}"
    )

    # --- Poll 2: Consecutive failure ---
    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    error_records_p2 = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records_p2) == 0, (
        f"Consecutive poll 2 emitted unexpected ERROR logs: {error_records_p2}"
    )

    # --- Poll 3: Consecutive failure (still unavailable) ---
    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    error_records_p3 = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records_p3) == 0, (
        f"Consecutive poll 3 emitted unexpected ERROR logs: {error_records_p3}"
    )

    # --- Poll 4: Recovery back to healthy state ---
    mock_healthy_info = MagicMock(spec=PiKVMDeviceInfo)
    mock_healthy_info.raw = {}
    coordinator.client.get_info = AsyncMock(return_value=mock_healthy_info)

    caplog.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    error_records_p4 = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records_p4) == 0, (
        f"Recovery poll emitted unexpected ERROR logs: {error_records_p4}"
    )


# -----------------------------------------------------------------------------
# Challenge 3: Stress Testing Device Name Resolution
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_coordinator_device_name_stress_matrix(hass):
    """Stress test device_name property across diverse adversarial inputs."""
    dev_reg = dr.async_get(hass)

    # Case A: URLs and clean_host parsing
    bizarre_urls = [
        "https://10.0.0.1:8080/api/info",
        "http://pikvm-rack.domain.internal/",
        "https://user:pass@192.168.1.55:443/kvm",
        "https://pikvm.local",
    ]

    for test_url in bizarre_urls:
        coord = PiKVMDataUpdateCoordinator(
            hass=hass,
            url=test_url,
            username="admin",
            password="pwd",
            totp="",
            cert="",
        )
        expected_host = parse_host_port(coord.url)[0]
        assert coord.clean_host == expected_host
        assert coord.device_name == "PiKVM"

    # Case B: Suffix stripping edge cases
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://192.168.1.200",
        username="admin",
        password="pwd",
        totp="",
        cert="",
    )
    assert coordinator.clean_host == "192.168.1.200"

    # B1: Standard suffix match
    coordinator.device_info = DeviceInfo(identifiers={(DOMAIN, "s1")}, name="PiKVM V4 (192.168.1.200)")
    assert coordinator.device_name == "PiKVM V4"

    # B2: Name is ONLY the suffix " (192.168.1.200)" -> cleaned is empty, falls through to raw_name
    coordinator.device_info = DeviceInfo(identifiers={(DOMAIN, "s2")}, name=" (192.168.1.200)")
    assert coordinator.device_name == " (192.168.1.200)"

    # B3: Suffix at beginning or middle, not at end
    coordinator.device_info = DeviceInfo(identifiers={(DOMAIN, "s3")}, name="(192.168.1.200) PiKVM")
    assert coordinator.device_name == "(192.168.1.200) PiKVM"

    # B4: clean_host is empty
    coordinator.clean_host = ""
    coordinator.device_info = DeviceInfo(identifiers={(DOMAIN, "s4")}, name="PiKVM ()")
    # When clean_host is empty, clean_host is falsy so it returns raw_name untouched
    assert coordinator.device_name == "PiKVM ()"

    # Case C: Device info & Data name adversarial types
    coord_c = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://192.168.1.201",
        username="admin",
        password="pwd",
        totp="",
        cert="",
    )

    # Empty dictionary
    coord_c.device_info = DeviceInfo(identifiers={(DOMAIN, "c1")})
    assert coord_c.device_name == "PiKVM"

    # None name in device_info
    coord_c.device_info = {"name": None}  # type: ignore[assignment]
    assert coord_c.device_name == "PiKVM"

    # Empty string name in device_info
    coord_c.device_info = {"name": ""}  # type: ignore[assignment]
    assert coord_c.device_name == "PiKVM"

    # Data is not an object or has None name
    coord_c.device_info = None
    coord_c.data = "plain string data"  # type: ignore[assignment]
    assert coord_c.device_name == "PiKVM"

    mock_data = MagicMock()
    mock_data.name = None
    coord_c.data = mock_data
    assert coord_c.device_name == "PiKVM"

    # Data name is localhost.localdomain
    mock_data.name = "localhost.localdomain"
    coord_c.data = mock_data
    assert coord_c.device_name == "PiKVM"

    # Data name is numeric (e.g. 42)
    mock_data.name = 42
    coord_c.data = mock_data
    assert coord_c.device_name == "42"

    # Case D: Device registry cascading priority with multiple devices
    entry = MockConfigEntry(domain=DOMAIN, entry_id="dev_stress_entry", title="")
    entry.add_to_hass(hass)
    coord_d = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://192.168.1.202",
        username="admin",
        password="pwd",
        totp="",
        cert="",
        entry=entry,
    )

    # Initial: no devices in registry and empty title -> fallback PiKVM
    assert coord_d.device_name == "PiKVM"

    # Add Device 1 with None name
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "dev_reg_1")},
        name=None,
    )
    # dev1 has no name, entry has empty title -> falls back to PiKVM
    assert coord_d.device_name == "PiKVM"

    # Add Device 2 with a name
    dev2 = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "dev_reg_2")},
        name="Device Two Official",
    )
    # dev2 provides raw_name
    assert coord_d.device_name == "Device Two Official"

    # If dev2 (evaluated first) has name_by_user, it takes precedence immediately
    dev_reg.async_update_device(dev2.id, name_by_user="User Overridden Device Two")
    assert coord_d.device_name == "User Overridden Device Two"


# -----------------------------------------------------------------------------
# Challenge 4: Zero Warnings/Errors from coordinator logger on all failures
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_exception",
    [
        PiKVMAuthenticationError("401 Auth"),
        TimeoutError("Timeout"),
        PiKVMTimeoutError("PiKVM Timeout"),
        ssl.SSLError("SSL Bad"),
        PiKVMConnectionError("Conn error"),
        aiohttp.ClientError("Client error"),
        OSError("OS error"),
        PiKVMDeviceError("Device error"),
        PiKVMError("General error"),
    ],
)
async def test_coordinator_internal_logger_emits_no_warnings_or_errors(hass, caplog, failure_exception):
    """Verify that custom_components.pikvm.coordinator never emits WARNING or ERROR directly on failures."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(side_effect=failure_exception)

    caplog.clear()
    with pytest.raises((ConfigEntryAuthFailed, UpdateFailed)):
        await coordinator._async_update_data()

    coordinator_warnings_and_errors = [
        r
        for r in caplog.records
        if r.name == "custom_components.pikvm.coordinator" and r.levelno >= logging.WARNING
    ]
    assert len(coordinator_warnings_and_errors) == 0, (
        f"coordinator emitted unexpected warning/error: {coordinator_warnings_and_errors}"
    )


# -----------------------------------------------------------------------------
# Challenge 5: Hardware Health Defensive Stress Matrix
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adversarial_payload",
    [
        None,
        {},
        {"hw": None},
        {"hw": "not-a-dict"},
        {"hw": {"health": None}},
        {"hw": {"health": 123}},
        {"hw": {"health": {"throttling": None}}},
        {"hw": {"health": {"throttling": "invalid"}}},
        {"hw": {"health": {"throttling": {"raw_flags": "not_an_int"}}}},
        {"hw": {"health": {"throttling": {"raw_flags": None}}}},
        {"hw": {"health": {"throttling": {"text_flags": None}}}},
        {"hw": {"health": {"throttling": {"text_flags": 12345}}}},
        {"hw": {"health": {"throttling": {"voltage": None}}}},
        {"hw": {"health": {"throttling": {"voltage": {"core": None}}}}},
        {"hw": {"health": {"throttling": {"voltage": {"core": "bad"}}}}},
        {"hw": {"health": {"throttling": {"voltage": {"core": {"now": None, "past": None}}}}}},
    ],
)
async def test_coordinator_hardware_health_adversarial_payloads(hass, adversarial_payload):
    """Verify _async_check_hardware_health does not raise exceptions on malformed health payloads."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_malformed_health_entry", title="PiKVM")
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

    # Should run cleanly with no exceptions
    coordinator._async_check_hardware_health(adversarial_payload)

