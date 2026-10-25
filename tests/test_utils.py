"""Tests for the utility functions in the PiKVM integration."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_TOTP,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.pikvm.utils import (
    bytes_to_mb,
    create_data_schema,
    find_existing_entry,
    format_url,
    get_nested_value,
    get_unique_id_base,
    update_existing_entry,
)


def test_format_url():
    """Test the format_url function."""
    assert format_url("192.168.1.100") == "https://192.168.1.100"
    assert format_url("http://192.168.1.100") == "http://192.168.1.100"
    assert format_url("https://192.168.1.100/") == "https://192.168.1.100"
    assert format_url("pikvm.local") == "https://pikvm.local"


def test_create_data_schema():
    """Test creating voluptuous data schema with defaults and overrides."""
    schema = create_data_schema({})
    assert CONF_HOST in schema.schema
    assert CONF_USERNAME in schema.schema
    assert CONF_PASSWORD in schema.schema
    assert CONF_TOTP in schema.schema

    schema_with_vals = create_data_schema({
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "my_user",
        CONF_PASSWORD: "my_password",
        CONF_TOTP: "123456",
    })
    validated = schema_with_vals({
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "my_user",
        CONF_PASSWORD: "my_password",
        CONF_TOTP: "123456",
    })
    assert validated[CONF_HOST] == "https://pikvm.local"
    assert validated[CONF_USERNAME] == "my_user"


def test_update_existing_entry(hass):
    """Test updating existing config entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "https://old.pikvm",
            "serial": "sn_123",
        },
    )
    entry.add_to_hass(hass)

    update_existing_entry(hass, entry, {CONF_HOST: "https://new.pikvm"})
    assert entry.data[CONF_HOST] == "https://new.pikvm"
    assert entry.data["serial"] == "sn_123"

    # Test when hass is None
    update_existing_entry(None, entry, {CONF_HOST: "https://standalone.pikvm"})

    # Test when entry has no serial
    entry_no_serial = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "https://old.pikvm"})
    entry_no_serial.add_to_hass(hass)
    update_existing_entry(hass, entry_no_serial, {CONF_HOST: "https://new.pikvm"})
    assert entry_no_serial.data["serial"] is None


def test_find_existing_entry():
    """Test finding existing entry matching serial number."""
    entry1 = MagicMock()
    entry1.data = {"serial": "SN-001"}
    entry2 = MagicMock()
    entry2.data = {"serial": "SN-002"}

    flow_handler = MagicMock()
    flow_handler._async_current_entries.return_value = [entry1, entry2]

    # Matching serial case-insensitively
    assert find_existing_entry(flow_handler, "sn-001") == entry1
    assert find_existing_entry(flow_handler, "SN-002") == entry2
    # Non-matching serial
    assert find_existing_entry(flow_handler, "SN-999") is None
    # Empty serial
    assert find_existing_entry(flow_handler, "") is None
    assert find_existing_entry(flow_handler, None) is None


def test_get_unique_id_base():
    """Test get_unique_id_base with full hierarchy and edge cases."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {}
    config_entry.unique_id = None

    coordinator = MagicMock()
    coordinator.data = {"hw": {"platform": {"serial": "SN-555"}}}
    # 1. Coordinator serial takes precedence
    assert get_unique_id_base(config_entry, coordinator) == "test_entry_SN-555"

    # 2. Coordinator serial empty / None / "None" -> fallback to config_entry.data["serial"]
    coordinator.data = {"hw": {"platform": {"serial": None}}}
    config_entry.data = {"serial": "SN-DATA"}
    assert get_unique_id_base(config_entry, coordinator) == "test_entry_SN-DATA"

    coordinator.data = {"hw": {"platform": {"serial": "None"}}}
    assert get_unique_id_base(config_entry, coordinator) == "test_entry_SN-DATA"

    # 3. Coordinator is None -> check config_entry.data["serial"]
    assert get_unique_id_base(config_entry, None) == "test_entry_SN-DATA"

    # 4. config_entry.data has no serial or "None" -> check config_entry.unique_id
    config_entry.data = {"serial": " none "}
    config_entry.unique_id = "UID-777"
    assert get_unique_id_base(config_entry, None) == "test_entry_UID-777"

    # 5. Integer serials
    config_entry.data = {"serial": 12345}
    assert get_unique_id_base(config_entry, None) == "test_entry_12345"

    config_entry.data = {}
    config_entry.unique_id = 67890
    assert get_unique_id_base(config_entry, None) == "test_entry_67890"

    # 6. Fallback to "unknown" when all are None / whitespace / "none"
    config_entry.data = {"serial": "   "}
    config_entry.unique_id = "None"
    coordinator.data = {}
    assert get_unique_id_base(config_entry, coordinator) == "test_entry_unknown"

    # 7. Non-mapping data or missing data attribute on config_entry
    class BareEntry:
        entry_id = "bare_entry"

    assert get_unique_id_base(BareEntry(), None) == "bare_entry_unknown"

    # 8. Boolean serials are ignored and fallback to "unknown"
    coord_bool = MagicMock()
    coord_bool.data = {"hw": {"platform": {"serial": True}}}
    assert get_unique_id_base(config_entry, coord_bool) == "test_entry_unknown"
    coord_bool.data = {"hw": {"platform": {"serial": False}}}
    assert get_unique_id_base(config_entry, coord_bool) == "test_entry_unknown"

    config_entry_bool = MagicMock()
    config_entry_bool.entry_id = "test_entry"
    config_entry_bool.data = {"serial": True}
    config_entry_bool.unique_id = None
    assert get_unique_id_base(config_entry_bool, None) == "test_entry_unknown"
    config_entry_bool.data = {"serial": False}
    assert get_unique_id_base(config_entry_bool, None) == "test_entry_unknown"

    config_entry_bool.data = {}
    config_entry_bool.unique_id = True
    assert get_unique_id_base(config_entry_bool, None) == "test_entry_unknown"
    config_entry_bool.unique_id = False
    assert get_unique_id_base(config_entry_bool, None) == "test_entry_unknown"


def test_get_nested_value():
    """Test the get_nested_value function with dicts, objects, and edge cases."""
    data = {"a": {"b": {"c": 1}}}
    assert get_nested_value(data, ["a", "b", "c"]) == 1
    assert get_nested_value(data, ["a", "b", "d"]) is None
    assert get_nested_value(data, ["a", "b", "d"], default="default") == "default"
    assert get_nested_value(data, ["x", "y", "z"], default="not_found") == "not_found"
    assert get_nested_value(None, ["a", "b"], default="none") == "none"
    assert get_nested_value(data, ["a", "c"], default="missing") == "missing"
    assert get_nested_value({"a": {"b": {}}}, ["a", "b"]) == {}

    # Single string key
    assert get_nested_value({"host": "example.com"}, "host") == "example.com"
    assert get_nested_value({"host": "example.com"}, "missing", default="def") == "def"

    # keys is None or non-iterable
    assert get_nested_value({"a": 1}, None, default="fallback") == "fallback"
    assert get_nested_value({"a": 1}, 123, default="fallback") == "fallback"

    # Test non-dict without get
    assert get_nested_value(12345, ["a", "b"], default="invalid") == "invalid"

    # Test object whose get() raises exceptions
    class BrokenGetter:
        def get(self, key, default=None):
            raise RuntimeError("Broken getter")

    assert get_nested_value(BrokenGetter(), ["key"], default="caught") == "caught"

    class ZeroDivisionGetter:
        def get(self, key, default=None):
            return 1 / 0

    assert get_nested_value(ZeroDivisionGetter(), ["key"], default="math_err") == "math_err"

    class LookupErrorGetter:
        def get(self, key, default=None):
            raise KeyError("missing")

    assert get_nested_value(LookupErrorGetter(), ["key"], default="lookup_err") == "lookup_err"

    class OSErrorGetter:
        def get(self, key, default=None):
            raise OSError("I/O error")

    assert get_nested_value(OSErrorGetter(), ["key"], default="os_err") == "os_err"


def test_bytes_to_mb():
    """Test the bytes_to_mb function with normal and edge cases."""
    assert bytes_to_mb(1048576) == 1.0
    assert bytes_to_mb(0) == 0.0
    assert pytest.approx(bytes_to_mb(500000), 0.001) == 0.476837
    assert bytes_to_mb(None) is None
    assert bytes_to_mb(float("inf")) is None
    assert bytes_to_mb(float("nan")) is None
    assert bytes_to_mb("invalid") is None
