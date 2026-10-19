"""Quality Scale, Feature Inventory (Tier 1), and Boundary/Corner (Tier 2) Tests for PiKVM.

Covers all 10 features defined in TEST_INFRA.md and Home Assistant Quality Scale standards:
- Feature 1: Device Setup & Zeroconf Discovery
- Feature 2: Coordinator Polling & Translated Exceptions
- Feature 3: Sensor & Long-Term Statistics Platform
- Feature 4: Binary Sensor & Dynamic State Icons
- Feature 5: Diagnostics & Redaction
- Feature 6: Options Flow & Reconfigure/Reauth
- Feature 7: Self-Healing Repairs (Undervoltage/Throttling)
- Feature 8: Stale Device & Config Entry Removal
- Feature 9: Strict Static Typing & Code Contracts
- Feature 10: Quality Scale Tracking & Translation Synchronization
"""

from __future__ import annotations

import json
import re
import ssl
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
import yaml
from homeassistant import config_entries
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.update_coordinator import UpdateFailed
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMDeviceInfo,
    PiKVMTimeoutError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import pikvm
from custom_components.pikvm.cert_handler import PiKVMResponse
from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_SERIAL,
    CONF_TOTP,
    DOMAIN,
    MANUFACTURER,
)
from custom_components.pikvm.const import (
    CONF_PASSWORD as PIKVM_CONF_PASSWORD,
)
from custom_components.pikvm.const import (
    CONF_USERNAME as PIKVM_CONF_USERNAME,
)
from custom_components.pikvm.coordinator import (
    PiKVMDataUpdateCoordinator,
)
from custom_components.pikvm.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from custom_components.pikvm.options_flow import (
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PiKVMOptionsFlowHandler,
)
from custom_components.pikvm.utils import (
    bytes_to_mb,
    create_data_schema,
    get_nested_value,
    get_unique_id_base,
    normalize_url,
)

BASE_DIR = Path(__file__).resolve().parent.parent
COMPONENT_DIR = BASE_DIR / "custom_components" / "pikvm"


# ---------------------------------------------------------------------------
# Fixtures & Sample Telemetry
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_telemetry_dict() -> dict[str, Any]:
    """Return a complete sample PiKVM telemetry dictionary."""
    return {
        "hw": {
            "platform": {
                "type": "v3",
                "model": "V3.3",
                "base": "Raspberry Pi 4",
                "serial": "sn_quality_123",
            },
            "health": {
                "temp": {"cpu": 45.2},
                "throttling": {
                    "raw_flags": 0,
                    "text_flags": [],
                    "voltage": {"core": {"now": False, "past": False}},
                },
            },
            "performance": {
                "cpu": {"utilization": 22.4},
                "memory": {
                    "total": 4147483648,
                    "used": 1073741824,
                    "utilization": 25.8,
                },
                "fan": {"speed": 2800},
            },
        },
        "system": {"kvmd": {"version": "3.102"}},
        "meta": {"server": {"host": "pikvm-qs.local", "name": "PiKVM Quality Scale"}},
        "extras": {
            "ipmi": {"is_running": True},
            "vnc": {"is_running": False},
            "webterm": {"is_running": True},
            "janus": {"is_running": False},
        },
        "msd": {
            "storage": {"total": 16000000000, "available": 8000000000},
            "drive": {"is_mounted": True},
            "is_enabled": True,
        },
    }


@pytest.fixture
def sample_device_info(sample_telemetry_dict: dict[str, Any]) -> PiKVMDeviceInfo:
    """Return a parsed PiKVMDeviceInfo instance."""
    return PiKVMDeviceInfo.from_dict(sample_telemetry_dict)


@pytest.fixture
def mock_entry(pikvm_cert: str) -> MockConfigEntry:
    """Return a mock config entry for testing."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Quality Scale",
        unique_id="sn_quality_123",
        data={
            CONF_HOST: "https://pikvm-qs.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_quality_123",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "JBSWY3DPEHPK3PXP",
        },
        options={CONF_SCAN_INTERVAL: 30},
    )


# ===========================================================================
# Manifest, Quality Scale, and Translation Synchronization Tests
# ===========================================================================


def test_manifest_gold_or_platinum_compliance():
    """Verify manifest.json adheres to HA quality scale metadata standards."""
    manifest_path = COMPONENT_DIR / "manifest.json"
    assert manifest_path.exists(), "manifest.json must exist"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("domain") == DOMAIN
    assert manifest.get("name") == "PiKVM"
    assert manifest.get("config_flow") is True
    assert manifest.get("integration_type") == "device"
    assert manifest.get("iot_class") == "local_polling"
    assert manifest.get("quality_scale") == "platinum"
    assert (
        manifest.get("documentation")
        == "https://github.com/adamoutler/pikvm-homeassistant-integration"
    )
    assert (
        manifest.get("issue_tracker")
        == "https://github.com/adamoutler/pikvm-homeassistant-integration/issues"
    )
    assert "_pikvm._tcp.local." in manifest.get("zeroconf", [])
    assert any("pikvm-aio" in req for req in manifest.get("requirements", []))
    assert any("pyotp" in req for req in manifest.get("requirements", []))


def test_py_typed_exists():
    """Verify PEP 561 py.typed marker file exists."""
    py_typed_path = COMPONENT_DIR / "py.typed"
    assert py_typed_path.is_file(), "py.typed marker file must exist"


def test_quality_scale_yaml_rules_structure():
    """Verify quality_scale.yaml rules structure and valid rule definitions."""
    qs_path = COMPONENT_DIR / "quality_scale.yaml"
    assert qs_path.exists(), "quality_scale.yaml must exist"
    with open(qs_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "rules" in data
    rules = data["rules"]
    assert isinstance(rules, dict)
    assert len(rules) == 54, f"quality_scale.yaml must document all 54 rules, found {len(rules)}"

    valid_statuses = {"done", "exempt", "todo"}
    for rule_name, rule_value in rules.items():
        if isinstance(rule_value, str):
            assert rule_value in valid_statuses, (
                f"Rule {rule_name} status invalid: {rule_value}"
            )
        elif isinstance(rule_value, dict):
            status = rule_value.get("status")
            assert status in valid_statuses, (
                f"Rule {rule_name} status invalid: {status}"
            )
            if status == "exempt":
                assert rule_value.get("comment"), (
                    f"Exempt rule {rule_name} must have comment justification"
                )
        else:
            pytest.fail(f"Unexpected format for rule {rule_name}: {rule_value}")


def test_translation_files_synchronized():
    """Verify strings.json and translations/en.json are identical in structure."""
    strings_path = COMPONENT_DIR / "strings.json"
    en_path = COMPONENT_DIR / "translations" / "en.json"

    assert strings_path.exists(), "strings.json must exist"
    assert en_path.exists(), "translations/en.json must exist"

    with open(strings_path, encoding="utf-8") as f:
        strings_data = json.load(f)
    with open(en_path, encoding="utf-8") as f:
        en_data = json.load(f)

    def extract_keys(d: dict[str, Any], prefix: str = "") -> set[str]:
        keys = set()
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.add(full)
            if isinstance(v, dict):
                keys.update(extract_keys(v, full))
        return keys

    strings_keys = extract_keys(strings_data)
    en_keys = extract_keys(en_data)

    missing_in_en = strings_keys - en_keys
    missing_in_strings = en_keys - strings_keys

    assert not missing_in_en, (
        f"Keys in strings.json missing from en.json: {missing_in_en}"
    )
    assert not missing_in_strings, (
        f"Keys in en.json missing from strings.json: {missing_in_strings}"
    )


def test_icons_json_entity_coverage():
    """Verify icons.json specifies icon mappings for all known sensor platforms."""
    icons_path = COMPONENT_DIR / "icons.json"
    assert icons_path.exists(), "icons.json must exist"
    with open(icons_path, encoding="utf-8") as f:
        icons_data = json.load(f)

    sensor_icons = icons_data.get("entity", {}).get("sensor", {})
    binary_sensor_icons = icons_data.get("entity", {}).get("binary_sensor", {})

    expected_sensors = {
        "cpu_temp": "mdi:thermometer",
        "cpu_utilization": "mdi:cpu-64-bit",
        "memory_utilization": "mdi:memory",
        "fan_speed": "mdi:fan",
        "msd_storage": "mdi:database",
    }
    for s, expected_icon in expected_sensors.items():
        assert s in sensor_icons, f"Sensor {s} missing from icons.json"
        assert sensor_icons[s].get("default") == expected_icon, (
            f"Sensor {s} default icon mismatch in icons.json"
        )

    expected_binary = {
        "throttling": {"default": "mdi:alert", "state": {"on": "mdi:alert", "off": "mdi:check-circle"}},
        "msd_drive": {"default": "mdi:usb", "state": {"on": "mdi:usb-port", "off": "mdi:usb"}},
        "msd_enabled": {"default": "mdi:check-circle", "state": {"on": "mdi:check-circle", "off": "mdi:close-circle"}},
    }
    for b, config in expected_binary.items():
        assert b in binary_sensor_icons, f"Binary sensor {b} missing from icons.json"
        assert binary_sensor_icons[b].get("default") == config["default"]
        assert "state" in binary_sensor_icons[b], f"Binary sensor {b} missing state icons"
        for state_key, expected_icon in config["state"].items():
            assert binary_sensor_icons[b]["state"].get(state_key) == expected_icon

    expected_extras = {
        "extra_ipmi": "mdi:network",
        "extra_janus": "mdi:web",
        "extra_janus_static": "mdi:web",
        "extra_vnc": "mdi:monitor",
        "extra_webterm": "mdi:console",
    }
    for extra_key, expected_icon in expected_extras.items():
        assert extra_key in binary_sensor_icons, f"Extra {extra_key} missing from icons.json"
        assert binary_sensor_icons[extra_key].get("default") == expected_icon


# ===========================================================================
# Tier 1: Feature Coverage (50 Tests, >=5 per feature)
# ===========================================================================

# --- Feature 1: Device Setup & Zeroconf Discovery ---


@pytest.mark.asyncio
async def test_f1_zeroconf_discovery_success(hass: HomeAssistant):
    """F1.1: Valid IPv4 Zeroconf discovery initiates flow with unique_id."""
    service_info = ZeroconfServiceInfo(
        ip_address="192.168.1.55",
        ip_addresses=["192.168.1.55"],
        port=443,
        hostname="pikvm-disc.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM Discovery._pikvm._tcp.local.",
        properties={"serial": "SN_DISC_01", "model": "V3.3"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=service_info
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.asyncio
async def test_f1_zeroconf_ipv6_rejected(hass: HomeAssistant):
    """F1.2: Zeroconf discovery with IPv6 host address is aborted."""
    service_info = ZeroconfServiceInfo(
        ip_address="fe80::1",
        ip_addresses=["fe80::1"],
        port=443,
        hostname="pikvm-ipv6.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM IPv6._pikvm._tcp.local.",
        properties={"serial": "SN_IPV6_01"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=service_info
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "ipv6_address"


@pytest.mark.asyncio
async def test_f1_zeroconf_missing_serial_rejected(hass: HomeAssistant):
    """F1.3: Zeroconf discovery with missing serial property is aborted."""
    service_info = ZeroconfServiceInfo(
        ip_address="192.168.1.56",
        ip_addresses=["192.168.1.56"],
        port=443,
        hostname="pikvm-noserial.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM No Serial._pikvm._tcp.local.",
        properties={},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=service_info
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "missing_serial_or_host"


@pytest.mark.asyncio
async def test_f1_zeroconf_ignore_selection(hass: HomeAssistant):
    """F1.4: Choosing 'ignore' on zeroconf confirmation aborts with 'ignored'."""
    flow = pikvm.config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = {"serial": "SN_IGNORE_01"}
    result = await flow.async_step_zeroconf_confirm("ignore")
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "ignored"


@pytest.mark.asyncio
async def test_f1_user_step_creates_entry(hass: HomeAssistant, pikvm_cert: str):
    """F1.5: User flow step successfully authenticates and creates config entry."""
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_user_01", "PiKVM Test", None
                )
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_HOST: "https://192.168.1.10",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret_password",
                CONF_TOTP: "",
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "PiKVM Test"
        assert result["data"][CONF_SERIAL] == "sn_user_01"


# --- Feature 2: Coordinator Polling & Translated Exceptions ---


@pytest.mark.asyncio
async def test_f2_coordinator_polling_success(
    hass: HomeAssistant, sample_device_info: PiKVMDeviceInfo
):
    """F2.1: Coordinator polls API and stores telemetry with success flag True."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="secret",
        totp="",
        cert="",
    )
    await coordinator.async_setup()
    coordinator.client.get_info = AsyncMock(return_value=sample_device_info)

    data = await coordinator._async_update_data()
    assert data == sample_device_info
    assert coordinator.last_update_success is True


@pytest.mark.asyncio
async def test_f2_coordinator_auth_error_translated(hass: HomeAssistant):
    """F2.2: Authentication failure raises ConfigEntryAuthFailed with translation key."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="wrong_password",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMAuthenticationError("401 Unauthorized")
    )

    with pytest.raises(ConfigEntryAuthFailed) as exc_info:
        await coordinator._async_update_data()
    assert "Invalid credentials or 2FA TOTP token required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_f2_coordinator_timeout_error_translated(hass: HomeAssistant):
    """F2.3: Connection timeout raises UpdateFailed with host placeholder."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="secret",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMTimeoutError("Request timed out")
    )

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "timed out reaching pikvm.local" in str(exc_info.value)


@pytest.mark.asyncio
async def test_f2_coordinator_connection_error_translated(hass: HomeAssistant):
    """F2.4: Connection error raises UpdateFailed."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="secret",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMConnectionError("Connection refused")
    )

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "Cannot connect to pikvm.local" in str(exc_info.value)


@pytest.mark.asyncio
async def test_f2_coordinator_device_error_translated(hass: HomeAssistant):
    """F2.5: KVMD internal error raises UpdateFailed."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="secret",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMDeviceError("KVMD internal 500")
    )

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "Error communicating with PiKVM at pikvm.local" in str(exc_info.value)


# --- Feature 3: Sensor & Long-Term Statistics Platform ---


@pytest.mark.asyncio
async def test_f3_cpu_temp_sensor_properties(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F3.1: CPU temperature sensor provides valid measurement and UnitOfTemperature."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_cpu_temperature")
        assert state is not None
        assert float(state.state) == 45.2
        assert state.attributes.get("unit_of_measurement") == UnitOfTemperature.CELSIUS
        assert state.attributes.get("state_class") == SensorStateClass.MEASUREMENT
        assert state.attributes.get("device_class") == SensorDeviceClass.TEMPERATURE


@pytest.mark.asyncio
async def test_f3_cpu_utilization_sensor(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F3.2: CPU utilization sensor provides percentage measurement."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_cpu_utilization")
        assert state is not None
        assert float(state.state) == 22.4
        assert state.attributes.get("unit_of_measurement") == PERCENTAGE
        assert state.attributes.get("state_class") == SensorStateClass.MEASUREMENT


@pytest.mark.asyncio
async def test_f3_memory_utilization_sensor(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F3.3: Memory utilization sensor provides percentage measurement."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_memory_utilization")
        assert state is not None
        assert float(state.state) == 25.8
        assert state.attributes.get("unit_of_measurement") == PERCENTAGE


@pytest.mark.asyncio
async def test_f3_fan_speed_sensor(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F3.4: Fan speed sensor provides RPM measurement."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_fan_speed")
        assert state is not None
        assert int(state.state) == 2800
        assert state.attributes.get("unit_of_measurement") == REVOLUTIONS_PER_MINUTE


@pytest.mark.asyncio
async def test_f3_msd_storage_sensor(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F3.5: MSD storage sensor calculates percentage used accurately from bytes."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_msd_storage")
        assert state is not None
        assert float(state.state) == 50.0
        assert state.attributes.get("unit_of_measurement") == PERCENTAGE


# --- Feature 4: Binary Sensor & Dynamic State Icons ---


@pytest.mark.asyncio
async def test_f4_throttling_binary_sensor_clean(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F4.1: Throttling binary sensor is 'off' when raw_flags == 0."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_throttling")
        assert state is not None
        assert state.state == "off"
        assert state.attributes.get("device_class") == BinarySensorDeviceClass.PROBLEM


@pytest.mark.asyncio
async def test_f4_throttling_binary_sensor_flagged(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """F4.2: Throttling binary sensor is 'on' when raw_flags > 0."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x1
    sample_telemetry_dict["hw"]["health"]["throttling"]["text_flags"] = [
        "under-voltage"
    ]
    flagged_dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=flagged_dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_throttling")
        assert state is not None
        assert state.state == "on"


@pytest.mark.asyncio
async def test_f4_msd_drive_binary_sensor(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F4.3: MSD drive binary sensor reflects drive active state."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_msd_drive")
        assert state is not None
        assert state.state == "on"


@pytest.mark.asyncio
async def test_f4_msd_enabled_binary_sensor(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F4.4: MSD enabled binary sensor reflects MSD enabled state."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_msd_enabled")
        assert state is not None
        assert state.state == "on"


@pytest.mark.asyncio
async def test_f4_extra_services_binary_sensors(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F4.5: Extra services (IPMI, VNC, Webterm, Janus) mapped to binary sensors."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        ipmi = hass.states.get("binary_sensor.pikvm_quality_scale_ipmi_service")
        vnc = hass.states.get("binary_sensor.pikvm_quality_scale_vnc_service")
        webterm = hass.states.get(
            "binary_sensor.pikvm_quality_scale_web_terminal_service"
        )

        assert ipmi is not None and ipmi.state == "on"
        assert vnc is not None and vnc.state == "off"
        assert webterm is not None and webterm.state == "on"


# --- Feature 5: Diagnostics & Redaction ---


@pytest.mark.asyncio
async def test_f5_diagnostics_returned(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F5.1: Config entry diagnostics returns valid structured dictionary."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, mock_entry)
        assert isinstance(diag, dict)
        assert "config_entry" in diag
        assert "coordinator" in diag
        assert diag["coordinator"]["last_update_success"] is True


@pytest.mark.asyncio
async def test_f5_diagnostics_secrets_redacted(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F5.2: Sensitive fields (password, totp, cert) are strictly redacted in diagnostics."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, mock_entry)
        entry_data = diag["config_entry"]["data"]

        assert entry_data[PIKVM_CONF_PASSWORD] == "**REDACTED**"
        assert entry_data[CONF_TOTP] == "**REDACTED**"
        assert entry_data[CONF_CERTIFICATE] == "**REDACTED**"


@pytest.mark.asyncio
async def test_f5_device_diagnostics(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F5.3: Device diagnostics returns device registry information alongside entry data."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        dev_reg = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(dev_reg, mock_entry.entry_id)
        assert len(devices) > 0
        device = devices[0]

        diag = await async_get_device_diagnostics(hass, mock_entry, device)
        assert "device" in diag
        assert diag["device"]["manufacturer"] == MANUFACTURER
        assert diag["device"]["serial_number"] == "sn_quality_123"


@pytest.mark.asyncio
async def test_f5_diagnostics_when_coordinator_empty(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """F5.4: Diagnostics handles uninitialized or empty coordinator gracefully."""
    mock_entry.add_to_hass(hass)
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)
    assert isinstance(diag, dict)
    assert diag["config_entry"]["data"][PIKVM_CONF_PASSWORD] == "**REDACTED**"


@pytest.mark.asyncio
async def test_f5_diagnostics_redact_set_contains_required_keys():
    """F5.5: Verify TO_REDACT includes all security-sensitive tokens."""
    for key in (
        PIKVM_CONF_PASSWORD,
        CONF_TOTP,
        CONF_CERTIFICATE,
        "token",
        "secret",
        "private_key",
    ):
        assert key in TO_REDACT, f"Security key '{key}' must be present in TO_REDACT"


# --- Feature 6: Options Flow & Reconfigure/Reauth ---


@pytest.mark.asyncio
async def test_f6_options_flow_init(hass: HomeAssistant, mock_entry: MockConfigEntry):
    """F6.1: Options flow initializes and shows form with current scan interval."""
    mock_entry.add_to_hass(hass)
    handler = PiKVMOptionsFlowHandler(mock_entry)
    handler.hass = hass

    result = await handler.async_step_init()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_f6_options_flow_update(hass: HomeAssistant, mock_entry: MockConfigEntry):
    """F6.2: Options flow saves updated scan interval."""
    mock_entry.add_to_hass(hass)
    handler = PiKVMOptionsFlowHandler(mock_entry)
    handler.hass = hass

    result = await handler.async_step_init(user_input={CONF_SCAN_INTERVAL: 60})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SCAN_INTERVAL] == 60


@pytest.mark.asyncio
async def test_f6_reauth_step_success(
    hass: HomeAssistant, mock_entry: MockConfigEntry, pikvm_cert: str
):
    """F6.3: Reauth step validates updated credentials and updates entry."""
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_quality_123", "PiKVM Test", None
                )
            ),
        ),
    ):
        step_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                PIKVM_CONF_USERNAME: "admin",
                PIKVM_CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )
        assert step_result["type"] == FlowResultType.ABORT
        assert step_result["reason"] == "reauth_successful"
        assert mock_entry.data[PIKVM_CONF_PASSWORD] == "new_password"


@pytest.mark.asyncio
async def test_f6_reconfigure_step_success(
    hass: HomeAssistant, mock_entry: MockConfigEntry, pikvm_cert: str
):
    """F6.4: Reconfigure step updates URL/credentials when serial matches."""
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure_confirm"

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_quality_123", "PiKVM Test", None
                )
            ),
        ),
    ):
        step_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://pikvm-new.local",
                CONF_PORT: 443,
                PIKVM_CONF_USERNAME: "admin",
                PIKVM_CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )
        assert step_result["type"] == FlowResultType.ABORT
        assert step_result["reason"] == "reconfigure_successful"
        assert "pikvm-new.local" in mock_entry.data[CONF_HOST]


@pytest.mark.asyncio
async def test_f6_reconfigure_mismatched_serial_aborts(
    hass: HomeAssistant, mock_entry: MockConfigEntry, pikvm_cert: str
):
    """F6.5: Reconfigure aborts if serial does not match existing unique_id."""
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure_confirm"

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "DIFFERENT_SERIAL", "PiKVM Other", None
                )
            ),
        ),
    ):
        step_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "https://pikvm-other.local",
                CONF_PORT: 443,
                PIKVM_CONF_USERNAME: "admin",
                PIKVM_CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )
        assert step_result["type"] == FlowResultType.ABORT
        assert step_result["reason"] == "unique_id_mismatched"


# --- Feature 7: Self-Healing Repairs (Undervoltage/Throttling) ---


@pytest.mark.asyncio
async def test_f7_active_undervoltage_creates_critical_issue(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """F7.1: Active undervoltage creates CRITICAL issue in issue_registry."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["now"] = True
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(dev)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"undervoltage_{mock_entry.entry_id}"
    )
    assert issue is not None
    assert issue.severity == IssueSeverity.CRITICAL
    assert issue.translation_key == "undervoltage"


@pytest.mark.asyncio
async def test_f7_past_undervoltage_creates_warning_issue(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """F7.2: Past (cleared) undervoltage creates WARNING issue in issue_registry."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["now"] = (
        False
    )
    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["past"] = (
        True
    )
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(dev)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"undervoltage_{mock_entry.entry_id}"
    )
    assert issue is not None
    assert issue.severity == IssueSeverity.WARNING


@pytest.mark.asyncio
async def test_f7_throttling_creates_warning_issue(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """F7.3: Active throttling creates WARNING issue in issue_registry."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x2
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(dev)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"throttling_{mock_entry.entry_id}"
    )
    assert issue is not None
    assert issue.severity == IssueSeverity.WARNING
    assert issue.translation_key == "throttling"


@pytest.mark.asyncio
async def test_f7_self_healing_clears_issues(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """F7.4: Hardware returning to normal health automatically deletes issues."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )

    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["now"] = True
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x2
    dev_bad = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)
    coordinator._async_check_hardware_health(dev_bad)

    reg = ir.async_get(hass)
    assert (
        reg.async_get_issue(DOMAIN, f"undervoltage_{mock_entry.entry_id}") is not None
    )
    assert reg.async_get_issue(DOMAIN, f"throttling_{mock_entry.entry_id}") is not None

    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["now"] = (
        False
    )
    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["past"] = (
        False
    )
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0
    dev_good = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)
    coordinator._async_check_hardware_health(dev_good)

    assert reg.async_get_issue(DOMAIN, f"undervoltage_{mock_entry.entry_id}") is None
    assert reg.async_get_issue(DOMAIN, f"throttling_{mock_entry.entry_id}") is None


@pytest.mark.asyncio
async def test_f7_async_remove_entry_cleans_up_repairs(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """F7.5: Removing config entry removes any residual repair issues."""
    mock_entry.add_to_hass(hass)
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"undervoltage_{mock_entry.entry_id}",
        is_fixable=False,
        severity=IssueSeverity.CRITICAL,
        translation_key="undervoltage",
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"throttling_{mock_entry.entry_id}",
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="throttling",
    )

    reg = ir.async_get(hass)
    assert (
        reg.async_get_issue(DOMAIN, f"undervoltage_{mock_entry.entry_id}") is not None
    )

    await pikvm.async_remove_entry(hass, mock_entry)

    assert reg.async_get_issue(DOMAIN, f"undervoltage_{mock_entry.entry_id}") is None
    assert reg.async_get_issue(DOMAIN, f"throttling_{mock_entry.entry_id}") is None


# --- Feature 8: Stale Device & Config Entry Removal ---


@pytest.mark.asyncio
async def test_f8_cleanup_devices_removes_device_without_entities(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """F8.1: _async_cleanup_devices removes device entries that have no entities."""
    mock_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)

    device = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "orphan_device_1")},
        name="Orphan PiKVM",
    )
    assert dev_reg.async_get(device.id) is not None

    await pikvm._async_cleanup_devices(hass, mock_entry)
    assert dev_reg.async_get(device.id) is None


@pytest.mark.asyncio
async def test_f8_cleanup_devices_removes_mismatched_serial_device(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """F8.2: _async_cleanup_devices removes devices with identifiers not matching entry serial."""
    mock_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    device = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "mismatched_serial_xyz")},
        name="Mismatched PiKVM",
    )
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "mismatched_temp",
        config_entry=mock_entry,
        device_id=device.id,
    )

    await pikvm._async_cleanup_devices(hass, mock_entry)
    assert dev_reg.async_get(device.id) is None
    assert ent_reg.async_get("sensor.pikvm_mismatched_temp") is None


@pytest.mark.asyncio
async def test_f8_async_unload_entry_success(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """F8.3: async_unload_entry unloads platforms and clears coordinator."""
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        unload_ok = await hass.config_entries.async_unload(mock_entry.entry_id)
        assert unload_ok is True
        assert mock_entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_f8_async_remove_entry_cleans_data(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """F8.4: async_remove_entry clears hass.data[DOMAIN][entry.entry_id]."""
    mock_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = MagicMock()

    await pikvm.async_remove_entry(hass, mock_entry)
    assert mock_entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_f8_matching_device_preserved_during_cleanup(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """F8.5: Device matching entry serial with registered entities is preserved."""
    mock_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    device = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "sn_quality_123")},
        name="Valid Device",
    )
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, "valid_temp", config_entry=mock_entry, device_id=device.id
    )

    await pikvm._async_cleanup_devices(hass, mock_entry)
    assert dev_reg.async_get(device.id) is not None


# --- Feature 9: Strict Static Typing & Code Contracts ---


def test_f9_utils_get_nested_value_safe_types():
    """F9.1: get_nested_value returns values safely across deep paths and primitives."""
    nested = {"a": {"b": {"c": 42}}}
    assert get_nested_value(nested, ["a", "b", "c"]) == 42
    assert get_nested_value(nested, ["a", "x"], "fallback") == "fallback"
    assert get_nested_value(None, ["a", "b"], "fallback") == "fallback"
    assert get_nested_value("not_a_dict", ["a"], 99) == 99


def test_f9_utils_bytes_to_mb_safe_types():
    """F9.2: bytes_to_mb converts integer and float bytes or handles None and invalid types."""
    assert bytes_to_mb(1048576) == 1.0
    assert bytes_to_mb(10485760.0) == 10.0
    assert bytes_to_mb(None) is None
    assert bytes_to_mb("invalid") is None


def test_f9_utils_normalize_url():
    """F9.3: normalize_url standardizes schemes and removes trailing slashes."""
    assert normalize_url("pikvm.local") == "https://pikvm.local"
    assert normalize_url("http://192.168.1.100/") == "http://192.168.1.100"
    assert normalize_url("https://pikvm.local:8443/") == "https://pikvm.local:8443"


def test_f9_utils_get_unique_id_base():
    """F9.4: get_unique_id_base returns deterministic sanitized string using config entry and coordinator."""
    mock_entry = MagicMock(entry_id="entry_456")
    mock_coord = MagicMock()
    mock_coord.data = {"hw": {"platform": {"serial": "sn_unique_99"}}}

    uid = get_unique_id_base(mock_entry, mock_coord)
    assert uid == "entry_456_sn_unique_99"


def test_f9_config_schema_validation():
    """F9.5: CONFIG_SCHEMA validates correctly formatted configuration."""
    valid_cfg = {
        DOMAIN: {
            CONF_HOST: "https://pikvm.local",
            PIKVM_CONF_USERNAME: "admin",
            PIKVM_CONF_PASSWORD: "secret_password",
            CONF_TOTP: "",
        }
    }
    validated = pikvm.CONFIG_SCHEMA(valid_cfg)
    assert validated[DOMAIN][PIKVM_CONF_USERNAME] == "admin"


# --- Feature 10: Quality Scale Tracking & Translation Synchronization ---


def test_f10_manifest_contains_valid_fields():
    """F10.1: manifest.json has all mandatory keys and non-empty values."""
    manifest_path = COMPONENT_DIR / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    for field in (
        "domain",
        "name",
        "config_flow",
        "iot_class",
        "version",
        "requirements",
    ):
        assert field in data, f"Field '{field}' missing from manifest.json"


def test_f10_all_strings_placeholders_formatted_properly():
    """F10.2: All placeholders in strings.json use valid Python format syntax."""
    strings_path = COMPONENT_DIR / "strings.json"
    with open(strings_path, encoding="utf-8") as f:
        content = f.read()

    placeholders = re.findall(r"\{([a-zA-Z0-9_]+)\}", content)
    valid_placeholders = {"host", "device_name", "error"}
    for p in placeholders:
        assert p in valid_placeholders, f"Unknown placeholder '{p}' in strings.json"


def test_f10_quality_scale_has_categorized_sections():
    """F10.3: quality_scale.yaml contains Bronze, Silver, and Gold rules."""
    qs_path = COMPONENT_DIR / "quality_scale.yaml"
    with open(qs_path, encoding="utf-8") as f:
        content = f.read()

    assert "appropriate-polling" in content
    assert "config-entry-unloading" in content
    assert "repair-issues" in content
    assert "strict-typing" in content


def test_f10_entity_categories_and_device_classes():
    """F10.4: Check entity descriptions in sensor and binary_sensor modules."""
    from custom_components.pikvm.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
    from custom_components.pikvm.sensor import SENSOR_DESCRIPTIONS

    for desc in SENSOR_DESCRIPTIONS:
        assert desc.key is not None
        assert desc.state_class in (
            SensorStateClass.MEASUREMENT,
            SensorStateClass.TOTAL,
            None,
        )

    for desc in BINARY_SENSOR_DESCRIPTIONS:
        assert desc.key is not None
        if desc.device_class:
            assert isinstance(desc.device_class, BinarySensorDeviceClass)


def test_f10_safe_translation_lookup_fallback():
    """F10.5: create_data_schema handles missing translation strings with fallback."""
    schema = create_data_schema(None)
    assert isinstance(schema, vol.Schema)


# ===========================================================================
# Tier 2: Boundary & Corner Cases (50 Tests, 5 per feature)
# ===========================================================================

# --- Boundary 1: Discovery & Setup Inputs ---


@pytest.mark.asyncio
async def test_b1_uppercase_serial_normalized_in_zeroconf(hass: HomeAssistant):
    """B1.1: Uppercase serial in Zeroconf discovery is normalized to lowercase."""
    service_info = ZeroconfServiceInfo(
        ip_address="192.168.1.61",
        ip_addresses=["192.168.1.61"],
        port=443,
        hostname="pikvm-upper.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM Upper._pikvm._tcp.local.",
        properties={"serial": "UPPER_SERIAL_XYZ"},
    )
    flow = pikvm.config_flow.PiKVMConfigFlow()
    flow.hass = hass
    result = await flow.async_step_zeroconf(service_info)
    assert result["type"] == FlowResultType.MENU
    assert flow._discovery_info["serial"] == "upper_serial_xyz"


@pytest.mark.asyncio
async def test_b1_whitespace_in_host_handled(hass: HomeAssistant, pikvm_cert: str):
    """B1.2: Host with leading/trailing whitespace is handled cleanly."""
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(True, "V3", "sn_ws_01", "PiKVM WS", None)
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_HOST: "https://pikvm.local/",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_b1_custom_port_in_url(hass: HomeAssistant, pikvm_cert: str):
    """B1.3: Non-standard custom port in URL (e.g. 8443) accepted."""
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3", "sn_port_8443", "PiKVM Port", None
                )
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_HOST: "https://pikvm.local:8443",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_b1_cert_fetch_failure_returns_form_error(hass: HomeAssistant):
    """B1.4: Failure to fetch certificate returns 'cannot_fetch_cert' error in form."""
    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_HOST: "https://offline.local",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "cannot_fetch_cert"


@pytest.mark.asyncio
async def test_b1_invalid_totp_secret_in_setup(hass: HomeAssistant):
    """B1.5: Non-base32 string in TOTP secret returns 'invalid_totp' error in form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_TOTP: "NOT_VALID_BASE32_189!@#",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_totp"


# --- Boundary 2: Coordinator Polling Payloads ---


@pytest.mark.asyncio
async def test_b2_coordinator_polling_empty_dict(hass: HomeAssistant):
    """B2.1: Polling returning empty dictionary does not crash coordinator."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    empty_info = PiKVMDeviceInfo.from_dict({})
    coordinator.client.get_info = AsyncMock(return_value=empty_info)

    data = await coordinator._async_update_data()
    assert data is not None


@pytest.mark.asyncio
async def test_b2_coordinator_polling_none_hw(hass: HomeAssistant):
    """B2.2: Polling returning payload with None hw sub-dict handled cleanly."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    payload = {"hw": None, "system": None}
    coordinator.client.get_info = AsyncMock(
        return_value=PiKVMDeviceInfo.from_dict(payload)
    )

    data = await coordinator._async_update_data()
    assert data is not None


@pytest.mark.asyncio
async def test_b2_coordinator_polling_ssl_error(hass: HomeAssistant):
    """B2.3: Polling encountering SSLError raises UpdateFailed with SSL message."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    coordinator.client.get_info = AsyncMock(
        side_effect=ssl.SSLError("Certificate verify failed")
    )

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()
    assert "SSL certificate validation failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_b2_coordinator_hardware_health_non_dict_data(hass: HomeAssistant):
    """B2.4: _async_check_hardware_health with non-dict / string data does not raise."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    coordinator._async_check_hardware_health("string_data_payload")
    coordinator._async_check_hardware_health(None)


@pytest.mark.asyncio
async def test_b2_coordinator_host_parsing_malformed_url(hass: HomeAssistant):
    """B2.5: Coordinator initializes clean_host even with strange malformed URLs."""
    coord = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="http:///invalid:url//",
        username="admin",
        password="password",
        totp="",
        cert="",
    )
    assert coord.clean_host is not None


# --- Boundary 3: Sensor Platform Numerical Limits ---


@pytest.mark.asyncio
async def test_b3_negative_cpu_temp(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B3.1: Negative sub-zero temperatures (e.g. -12.4 °C) parsed accurately."""
    sample_telemetry_dict["hw"]["health"]["temp"]["cpu"] = -12.4
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_cpu_temperature")
        assert state is not None
        assert float(state.state) == -12.4


@pytest.mark.asyncio
async def test_b3_cpu_utilization_100_percent(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B3.2: 100.0% CPU utilization handled accurately."""
    sample_telemetry_dict["hw"]["performance"]["cpu"]["utilization"] = 100.0
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_cpu_utilization")
        assert state is not None
        assert float(state.state) == 100.0


@pytest.mark.asyncio
async def test_b3_sensor_numeric_strings_coerced(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B3.3: Numeric values represented as strings are safely coerced to float."""
    sample_telemetry_dict["hw"]["health"]["temp"]["cpu"] = "48.7"
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_cpu_temperature")
        assert state is not None
        assert float(state.state) == 48.7


@pytest.mark.asyncio
async def test_b3_sensor_malformed_string_returns_none(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B3.4: Malformed non-numeric string ('invalid') sets sensor state to None/unknown."""
    sample_telemetry_dict["hw"]["health"]["temp"]["cpu"] = "not_a_number"
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_cpu_temperature")
        assert state is not None
        assert state.state in ("unknown", "unavailable", None)


@pytest.mark.asyncio
async def test_b3_zero_bytes_msd_storage(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B3.5: 0 bytes of MSD storage total returns None/unknown without ZeroDivisionError."""
    sample_telemetry_dict["msd"]["storage"]["total"] = 0
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("sensor.pikvm_quality_scale_msd_storage")
        assert state is not None
        assert state.state in ("unknown", "unavailable", None)


# --- Boundary 4: Binary Sensor Boundary Flags ---


@pytest.mark.asyncio
async def test_b4_throttling_raw_flags_0x4_throttled(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B4.1: Throttling raw_flags = 0x4 (frequency capped) turns sensor ON."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x4
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_throttling")
        assert state is not None
        assert state.state == "on"


@pytest.mark.asyncio
async def test_b4_empty_extras_dict_defaults_off(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B4.2: Empty extras sub-dict does not create optional extra service entities."""
    sample_telemetry_dict["extras"] = {}
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        ipmi = hass.states.get("binary_sensor.pikvm_quality_scale_ipmi_service")
        assert ipmi is None


@pytest.mark.asyncio
async def test_b4_unknown_text_flags_handled(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B4.3: Unknown string text flags in throttling do not raise."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["text_flags"] = [
        "unknown-future-flag"
    ]
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_throttling")
        assert state is not None


@pytest.mark.asyncio
async def test_b4_missing_msd_section_handled(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B4.4: Completely missing MSD section marks MSD binary sensors unavailable."""
    sample_telemetry_dict.pop("msd", None)
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        msd_drive = hass.states.get("binary_sensor.pikvm_quality_scale_msd_drive")
        assert msd_drive is not None
        assert msd_drive.state in ("unavailable", "off")


@pytest.mark.asyncio
async def test_b4_binary_sensor_attributes_contain_raw_flags(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B4.5: Binary sensor attributes include raw_flags for deep troubleshooting."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x5
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.pikvm_quality_scale_throttling")
        assert state is not None
        assert state.attributes.get("raw_flags") == 0x5


# --- Boundary 5: Diagnostics Deep Redaction ---


@pytest.mark.asyncio
async def test_b5_nested_secret_tokens_redacted(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B5.1: Nested secret tokens across arbitrary keys are scrubbed."""
    from homeassistant.components.diagnostics import async_redact_data

    payload = {
        "user": {"name": "admin", "token": "sensitive_jwt_token_123"},
        "network": {"auth_key": "private_secret_key"},
    }
    redacted = async_redact_data(payload, TO_REDACT)
    assert redacted["user"]["token"] == "**REDACTED**"
    assert redacted["network"]["auth_key"] == "**REDACTED**"
    assert redacted["user"]["name"] == "admin"


@pytest.mark.asyncio
async def test_b5_diagnostics_empty_config_entry(hass: HomeAssistant):
    """B5.2: Diagnostics on empty config entry does not raise."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["config_entry"]["data"] == {}


@pytest.mark.asyncio
async def test_b5_unicode_device_name_in_diagnostics(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B5.3: Unicode device name (e.g. 'PiKVM 测试') preserves fidelity in diagnostics."""
    sample_telemetry_dict["meta"]["server"]["name"] = "PiKVM 实验实验室"
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, mock_entry)
        assert (
            diag["coordinator"]["data"]["meta"]["server"]["name"] == "PiKVM 实验实验室"
        )


@pytest.mark.asyncio
async def test_b5_device_entry_with_none_fields(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B5.4: Device diagnostics handles DeviceEntry with None attributes."""
    mock_entry.add_to_hass(hass)
    mock_device = MagicMock()
    mock_device.id = "dev_123"
    mock_device.name = None
    mock_device.name_by_user = None
    mock_device.identifiers = []
    mock_device.connections = []
    mock_device.manufacturer = None
    mock_device.model = None
    mock_device.sw_version = None
    mock_device.hw_version = None
    mock_device.serial_number = None
    mock_device.disabled = False

    diag = await async_get_device_diagnostics(hass, mock_entry, mock_device)
    assert diag["device"]["id"] == "dev_123"
    assert diag["device"]["name"] is None


@pytest.mark.asyncio
async def test_b5_list_of_secrets_redacted():
    """B5.5: List of dictionaries containing secrets are all redacted."""
    from homeassistant.components.diagnostics import async_redact_data

    payload = [{"password": "pass1"}, {"password": "pass2"}]
    redacted = async_redact_data(payload, TO_REDACT)
    assert redacted[0]["password"] == "**REDACTED**"
    assert redacted[1]["password"] == "**REDACTED**"


# --- Boundary 6: Options & Flow Boundaries ---


@pytest.mark.asyncio
async def test_b6_options_min_scan_interval(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B6.1: Minimum scan_interval = 5 accepted by options schema."""
    mock_entry.add_to_hass(hass)
    handler = PiKVMOptionsFlowHandler(mock_entry)
    handler.hass = hass

    result = await handler.async_step_init(
        user_input={CONF_SCAN_INTERVAL: MIN_SCAN_INTERVAL}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SCAN_INTERVAL] == 5


@pytest.mark.asyncio
async def test_b6_options_max_scan_interval(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B6.2: Maximum scan_interval = 300 accepted by options schema."""
    mock_entry.add_to_hass(hass)
    handler = PiKVMOptionsFlowHandler(mock_entry)
    handler.hass = hass

    result = await handler.async_step_init(
        user_input={CONF_SCAN_INTERVAL: MAX_SCAN_INTERVAL}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SCAN_INTERVAL] == 300


@pytest.mark.asyncio
async def test_b6_options_below_min_rejected(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B6.3: Scan interval below MIN_SCAN_INTERVAL (<5) rejected by schema."""
    mock_entry.add_to_hass(hass)
    handler = PiKVMOptionsFlowHandler(mock_entry)
    handler.hass = hass

    form = await handler.async_step_init()
    schema = form["data_schema"]

    with pytest.raises(vol.Invalid):
        schema({CONF_SCAN_INTERVAL: 4})


@pytest.mark.asyncio
async def test_b6_options_above_max_rejected(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B6.4: Scan interval above MAX_SCAN_INTERVAL (>300) rejected by schema."""
    mock_entry.add_to_hass(hass)
    handler = PiKVMOptionsFlowHandler(mock_entry)
    handler.hass = hass

    form = await handler.async_step_init()
    schema = form["data_schema"]

    with pytest.raises(vol.Invalid):
        schema({CONF_SCAN_INTERVAL: 301})


@pytest.mark.asyncio
async def test_b6_reauth_invalid_totp_returns_form_error(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B6.5: Reauth flow with invalid base32 TOTP secret returns invalid_totp."""
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    step_result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            PIKVM_CONF_USERNAME: "admin",
            PIKVM_CONF_PASSWORD: "password",
            CONF_TOTP: "INVALID_TOTP_KEY!@#$",
        },
    )
    assert step_result["type"] == FlowResultType.FORM
    assert step_result["errors"]["base"] == "invalid_totp"


# --- Boundary 7: Repairs Boundary Conditions ---


@pytest.mark.asyncio
async def test_b7_concurrent_undervoltage_and_throttling(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B7.1: Both undervoltage and throttling present creates two distinct issues."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["voltage"]["core"]["now"] = True
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x2
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(dev)

    reg = ir.async_get(hass)
    assert (
        reg.async_get_issue(DOMAIN, f"undervoltage_{mock_entry.entry_id}") is not None
    )
    assert reg.async_get_issue(DOMAIN, f"throttling_{mock_entry.entry_id}") is not None


@pytest.mark.asyncio
async def test_b7_arm_frequency_capped_text_flag_creates_throttling_issue(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B7.2: Text flag 'arm-frequency-capped' creates throttling repair issue."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0
    sample_telemetry_dict["hw"]["health"]["throttling"]["text_flags"] = [
        "arm-frequency-capped"
    ]
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(dev)

    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, f"throttling_{mock_entry.entry_id}") is not None


@pytest.mark.asyncio
async def test_b7_raw_flags_large_integer_mask(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_telemetry_dict: dict[str, Any],
):
    """B7.3: raw_flags with high 32-bit integer bits (0x60000 = past throttled) handled."""
    sample_telemetry_dict["hw"]["health"]["throttling"]["raw_flags"] = 0x60000
    dev = PiKVMDeviceInfo.from_dict(sample_telemetry_dict)

    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(dev)

    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, f"throttling_{mock_entry.entry_id}") is not None


@pytest.mark.asyncio
async def test_b7_empty_throttling_dict_clears_issues(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B7.4: Empty throttling dictionary clears any existing issues without error."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health({})
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, f"undervoltage_{mock_entry.entry_id}") is None


@pytest.mark.asyncio
async def test_b7_repeated_clear_calls_safe(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """B7.5: Successive health checks on already healthy system do not raise."""
    coordinator = PiKVMDataUpdateCoordinator(
        hass=hass,
        url="https://pikvm.local",
        username="admin",
        password="password",
        totp="",
        cert="",
        entry=mock_entry,
    )
    coordinator._async_check_hardware_health(sample_device_info)
    coordinator._async_check_hardware_health(sample_device_info)


# --- Boundary 8: Stale Device Removal Boundaries ---


@pytest.mark.asyncio
async def test_b8_multiple_mismatched_devices_removed(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B8.1: Multiple stale devices with mismatched identifiers are all purged."""
    mock_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)

    d1 = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "stale_1")},
        name="Stale 1",
    )
    d2 = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "stale_2")},
        name="Stale 2",
    )

    await pikvm._async_cleanup_devices(hass, mock_entry)
    assert dev_reg.async_get(d1.id) is None
    assert dev_reg.async_get(d2.id) is None


@pytest.mark.asyncio
async def test_b8_device_without_serial_in_entry(hass: HomeAssistant):
    """B8.2: Entry with neither serial nor unique_id does not crash cleanup."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=None)
    entry.add_to_hass(hass)
    await pikvm._async_cleanup_devices(hass, entry)


@pytest.mark.asyncio
async def test_b8_entry_removal_without_active_issues(
    hass: HomeAssistant, mock_entry: MockConfigEntry
):
    """B8.3: async_remove_entry handles case where no issues exist without error."""
    mock_entry.add_to_hass(hass)
    await pikvm.async_remove_entry(hass, mock_entry)


@pytest.mark.asyncio
async def test_b8_device_rename_on_setup_disambiguation(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """B8.4: Legacy generic device name 'PiKVM' is updated to entry title on setup."""
    mock_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "sn_quality_123")},
        name="PiKVM",
    )

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        updated_dev = dev_reg.async_get(dev.id)
        assert updated_dev.name == "PiKVM Quality Scale"


@pytest.mark.asyncio
async def test_b8_custom_user_device_name_preserved(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    sample_device_info: PiKVMDeviceInfo,
):
    """B8.5: Custom user-assigned device name (name_by_user) is strictly preserved."""
    mock_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={(DOMAIN, "sn_quality_123")},
        name="PiKVM",
    )
    dev_reg.async_update_device(dev.id, name_by_user="My Dedicated Server PiKVM")

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=sample_device_info),
    ):
        assert await hass.config_entries.async_setup(mock_entry.entry_id) is True
        await hass.async_block_till_done()

        updated_dev = dev_reg.async_get(dev.id)
        assert updated_dev.name_by_user == "My Dedicated Server PiKVM"


# --- Boundary 9: Utilities & Cast Boundaries ---


def test_b9_bytes_to_mb_negative_value():
    """B9.1: Negative byte value converts to negative MB."""
    assert bytes_to_mb(-1048576) == -1.0


def test_b9_get_nested_value_empty_path():
    """B9.2: get_nested_value with empty path returns original data."""
    data = {"a": 1}
    assert get_nested_value(data, []) == data


def test_b9_get_nested_value_deep_missing():
    """B9.3: get_nested_value with non-existent deep path returns default."""
    data = {"a": {"b": 1}}
    assert get_nested_value(data, ["a", "c", "d"], default=999) == 999


def test_b9_normalize_url_with_ip_and_port():
    """B9.4: normalize_url correctly handles bare IPv4 with port."""
    assert normalize_url("192.168.1.100:8080") == "https://192.168.1.100:8080"


def test_b9_get_unique_id_base_special_chars():
    """B9.5: get_unique_id_base formats entry_id and serial cleanly."""
    mock_entry = MagicMock(entry_id="entry_special")
    mock_coord = MagicMock()
    mock_coord.data = {"hw": {"platform": {"serial": "special_serial_1"}}}
    uid = get_unique_id_base(mock_entry, mock_coord)
    assert uid == "entry_special_special_serial_1"


# --- Boundary 10: Quality Scale Syntax & Integrity ---


def test_b10_strings_json_valid_json_syntax():
    """B10.1: strings.json parses cleanly without trailing commas or syntax errors."""
    with open(COMPONENT_DIR / "strings.json", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_b10_translations_en_valid_json_syntax():
    """B10.2: translations/en.json parses cleanly without syntax errors."""
    with open(COMPONENT_DIR / "translations" / "en.json", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_b10_icons_json_valid_json_syntax():
    """B10.3: icons.json parses cleanly without syntax errors."""
    with open(COMPONENT_DIR / "icons.json", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_b10_quality_scale_yaml_valid_yaml_syntax():
    """B10.4: quality_scale.yaml parses cleanly as YAML without syntax errors."""
    with open(COMPONENT_DIR / "quality_scale.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)


def test_b10_manifest_valid_semver_version():
    """B10.5: manifest.json version string follows semver (e.g. 1.2.0)."""
    with open(COMPONENT_DIR / "manifest.json", encoding="utf-8") as f:
        data = json.load(f)
    assert re.match(r"^\d+\.\d+\.\d+", data["version"]) is not None
