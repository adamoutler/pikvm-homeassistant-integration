"""Home Assistant Quality Scale and static metadata compliance tests for PiKVM."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import voluptuous as vol
import yaml
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorStateClass

from custom_components import pikvm
from custom_components.pikvm.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
)
from custom_components.pikvm.binary_sensor import (
    PARALLEL_UPDATES as BINARY_SENSOR_PARALLEL_UPDATES,
)
from custom_components.pikvm.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_TOTP,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.pikvm.sensor import (
    PARALLEL_UPDATES as SENSOR_PARALLEL_UPDATES,
)
from custom_components.pikvm.sensor import (
    SENSOR_DESCRIPTIONS,
)
from custom_components.pikvm.utils import create_data_schema, normalize_url

BASE_DIR = Path(__file__).resolve().parent.parent
COMPONENT_DIR = BASE_DIR / "custom_components" / "pikvm"


def test_manifest_platinum_compliance():
    """Verify manifest.json adheres to HA Platinum quality scale metadata standards."""
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
    assert re.match(r"^\d+\.\d+\.\d+", manifest["version"]) is not None


def test_py_typed_exists():
    """Verify PEP 561 py.typed marker file exists."""
    py_typed_path = COMPONENT_DIR / "py.typed"
    assert py_typed_path.is_file(), "py.typed marker file must exist"


def test_quality_scale_yaml_rules_structure():
    """Verify quality_scale.yaml rules structure, tier headers, and valid rule definitions."""
    qs_path = COMPONENT_DIR / "quality_scale.yaml"
    assert qs_path.exists(), "quality_scale.yaml must exist"
    content = qs_path.read_text(encoding="utf-8")
    for tier in ("# Bronze", "# Silver", "# Gold", "# Platinum"):
        assert tier in content, f"Missing tier header '{tier}' in quality_scale.yaml"

    data = yaml.safe_load(content)
    assert "rules" in data
    rules = data["rules"]
    assert isinstance(rules, dict)
    assert len(rules) == 54, (
        f"quality_scale.yaml must document all 54 rules, found {len(rules)}"
    )

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
    """Verify strings.json and translations/en.json are identical in structure and placeholders."""
    strings_path = COMPONENT_DIR / "strings.json"
    en_path = COMPONENT_DIR / "translations" / "en.json"

    assert strings_path.exists(), "strings.json must exist"
    assert en_path.exists(), "translations/en.json must exist"

    strings_raw = strings_path.read_text(encoding="utf-8")
    strings_data = json.loads(strings_raw)
    en_data = json.loads(en_path.read_text(encoding="utf-8"))

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

    assert not (strings_keys - en_keys)
    assert not (en_keys - strings_keys)

    placeholders = re.findall(r"\{([a-zA-Z0-9_]+)\}", strings_raw)
    valid_placeholders = {"host", "device_name", "error"}
    for p in placeholders:
        assert p in valid_placeholders, f"Unknown placeholder '{p}' in strings.json"


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
        assert sensor_icons[s].get("default") == expected_icon

    expected_binary = {
        "throttling": {
            "default": "mdi:alert",
            "state": {"on": "mdi:alert", "off": "mdi:check-circle"},
        },
        "msd_drive": {
            "default": "mdi:usb",
            "state": {"on": "mdi:usb-port", "off": "mdi:usb"},
        },
        "msd_enabled": {
            "default": "mdi:check-circle",
            "state": {"on": "mdi:check-circle", "off": "mdi:close-circle"},
        },
    }
    for b, config in expected_binary.items():
        assert b in binary_sensor_icons, f"Binary sensor {b} missing from icons.json"
        assert binary_sensor_icons[b].get("default") == config["default"]
        assert "state" in binary_sensor_icons[b]
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
        assert extra_key in binary_sensor_icons
        assert binary_sensor_icons[extra_key].get("default") == expected_icon


def test_entity_categories_device_classes_and_parallel_updates():
    """Verify entity descriptions and PARALLEL_UPDATES across sensor and binary_sensor modules."""
    assert SENSOR_PARALLEL_UPDATES == 0
    assert BINARY_SENSOR_PARALLEL_UPDATES == 0

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


def test_config_schema_and_utils_contracts():
    """Verify CONFIG_SCHEMA, create_data_schema, and normalize_url contracts."""
    valid_cfg = {
        DOMAIN: {
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_TOTP: "",
        }
    }
    validated = pikvm.CONFIG_SCHEMA(valid_cfg)
    assert validated[DOMAIN][CONF_USERNAME] == "admin"

    schema = create_data_schema(None)
    assert isinstance(schema, vol.Schema)
    assert normalize_url("192.168.1.50") == "https://192.168.1.50"
