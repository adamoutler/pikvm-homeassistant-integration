"""Tests for the utility functions in the PiKVM integration."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_TOTP,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
)
from custom_components.pikvm_ha.utils import (
    bytes_to_mb,
    create_data_schema,
    find_existing_entry,
    format_url,
    get_nested_value,
    get_translations,
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


@pytest.mark.asyncio
async def test_get_translations(hass):
    """Test get_translations returns lookup callable."""
    with patch(
        "custom_components.pikvm_ha.utils.async_get_translations",
        new=AsyncMock(return_value={"component.pikvm_ha.step.user.title": "PiKVM Setup"}),
    ):
        translate = await get_translations(hass, "en", DOMAIN)
        assert translate("step.user.title", "Default") == "PiKVM Setup"
        assert translate("step.user.missing", "Fallback") == "Fallback"

    # Test error when hass is None
    with pytest.raises(ValueError):
        await get_translations(None, "en", DOMAIN)


def test_get_unique_id_base():
    """Test get_unique_id_base with coordinator serial or fallback."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"

    coordinator = MagicMock()
    coordinator.data = {"hw": {"platform": {"serial": "SN-555"}}}
    assert get_unique_id_base(config_entry, coordinator) == "test_entry_SN-555"

    coordinator.data = {}
    assert get_unique_id_base(config_entry, coordinator) == "test_entry_unknown"


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

    # Test non-dict without get
    assert get_nested_value(12345, ["a", "b"], default="invalid") == "invalid"

    # Test object whose get() raises an exception
    class BrokenGetter:
        def get(self, key, default=None):
            raise RuntimeError("Broken getter")

    assert get_nested_value(BrokenGetter(), ["key"], default="caught") == "caught"


def test_bytes_to_mb():
    """Test the bytes_to_mb function."""
    assert bytes_to_mb(1048576) == 1.0
    assert bytes_to_mb(0) == 0.0
    assert pytest.approx(bytes_to_mb(500000), 0.001) == 0.476837
