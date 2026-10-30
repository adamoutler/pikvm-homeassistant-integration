"""Tests for the PiKVM binary sensor platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    PiKVMBinarySensor,
    PiKVMBinarySensorEntityDescription,
    _get_msd_drive_attributes,
    _get_throttling_attributes,
    _is_throttling_on,
    _make_extra_description,
    async_setup_entry,
)
from custom_components.pikvm.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with complete telemetry data."""
    coordinator = MagicMock()
    coordinator.url = "https://pikvm.local"
    coordinator.last_update_success = True
    coordinator.data = {
        "hw": {
            "health": {
                "throttling": {
                    "raw_flags": 0x4,
                    "text_flags": ["throttled"],
                    "voltage": {"core": {"now": True, "past": False}},
                }
            }
        },
        "msd": {
            "is_enabled": True,
            "drive": {
                "is_mounted": True,
                "mode": "ro",
            },
        },
        "extras": {
            "vnc": {"is_running": True, "port": 5900},
            "ipmi": {"is_running": False},
        },
    }
    return coordinator


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry(hass, mock_coordinator):
    """Test binary sensor async_setup_entry registers all standard binary sensors and extras."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_id",
        data={"host": "https://pikvm.local", "serial": "sn_123"},
    )
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    stale_bin = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_stale_other_throttling",
        config_entry=entry,
    )
    # Add non-binary_sensor entity for branch coverage of ent_entry.domain != "binary_sensor"
    other_sensor = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_temp",
        config_entry=entry,
    )
    # Add valid binary_sensor entity for branch coverage of unique_id in valid_uids
    valid_bin = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_sn_123_throttling",
        config_entry=entry,
    )
    assert ent_reg.async_get(stale_bin.entity_id) is not None
    assert ent_reg.async_get(other_sensor.entity_id) is not None
    assert ent_reg.async_get(valid_bin.entity_id) is not None

    entry.runtime_data = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    assert ent_reg.async_get(stale_bin.entity_id) is None
    assert ent_reg.async_get(other_sensor.entity_id) is not None
    assert ent_reg.async_get(valid_bin.entity_id) is not None
    assert mock_add_entities.call_count == 1
    entities = mock_add_entities.call_args[0][0]
    # 3 standard (throttling, msd_enabled, msd_drive) + 2 extras (vnc, ipmi) = 5
    assert len(entities) == 5

    keys = [e.entity_description.key for e in entities]
    assert "throttling" in keys
    assert "msd_enabled" in keys
    assert "msd_drive" in keys
    assert "extra_vnc" in keys
    assert "extra_ipmi" in keys


def test_pikvm_binary_sensor_properties(mock_coordinator):
    """Test PiKVMBinarySensor properties, states, attributes, and availability."""
    throttling_desc = next(
        d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "throttling"
    )
    sensor = PiKVMBinarySensor(mock_coordinator, "test_uid", throttling_desc)

    assert sensor.unique_id == "test_uid_throttling"
    assert sensor.translation_key == "throttling"
    assert sensor.has_entity_name is True
    assert sensor.is_on is True
    assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.available is True
    assert sensor.extra_state_attributes["ip"] == "https://pikvm.local"
    assert "raw_flags" in sensor.extra_state_attributes

    # Test unavailable when coordinator fails
    mock_coordinator.last_update_success = False
    assert sensor.available is False

    # Test when coordinator data is missing metric
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {}
    assert sensor.available is False
    assert sensor.is_on is False


def test_msd_binary_sensors(mock_coordinator):
    """Test MSD enabled and drive binary sensors."""
    enabled_desc = next(
        d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "msd_enabled"
    )
    drive_desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "msd_drive")

    sensor_enabled = PiKVMBinarySensor(mock_coordinator, "test_uid", enabled_desc)
    sensor_drive = PiKVMBinarySensor(mock_coordinator, "test_uid", drive_desc)

    assert sensor_enabled.is_on is True
    assert sensor_enabled.available is True
    assert sensor_enabled.device_class == BinarySensorDeviceClass.POWER

    assert sensor_drive.is_on is True
    assert sensor_drive.available is True
    assert sensor_drive.device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert sensor_drive.extra_state_attributes["mode"] == "ro"

    # Test attributes when attributes_fn is None (msd_enabled)
    assert sensor_enabled.extra_state_attributes == {"ip": "https://pikvm.local"}

    # Test when MSD is None
    mock_coordinator.data["msd"] = None
    assert sensor_enabled.available is False
    assert sensor_drive.available is False


def test_pikvm_extra_binary_sensor(mock_coordinator):
    """Test extra service binary sensor via _make_extra_description."""
    extra_sensor = PiKVMBinarySensor(
        mock_coordinator, "test_uid", _make_extra_description("vnc")
    )

    assert extra_sensor.unique_id == "test_uid_extra_vnc"
    assert extra_sensor.translation_key == "extra_vnc"
    assert extra_sensor.has_entity_name is True
    assert extra_sensor.is_on is True
    assert extra_sensor.device_class == BinarySensorDeviceClass.RUNNING
    assert extra_sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert extra_sensor.available is True
    assert extra_sensor.extra_state_attributes["port"] == 5900
    assert extra_sensor.extra_state_attributes["ip"] == "https://pikvm.local"

    # Test when coordinator update fails
    mock_coordinator.last_update_success = False
    assert extra_sensor.available is False

    # Test when extra is not in extras
    mock_coordinator.last_update_success = True
    mock_coordinator.data["extras"] = {}
    assert extra_sensor.available is False
    assert extra_sensor.is_on is False


def test_pikvm_binary_sensor_name_fallback_and_available_fn_none(mock_coordinator):
    """Test PiKVMBinarySensor translation_key and available when available_fn is None."""
    desc = PiKVMBinarySensorEntityDescription(
        key="test_custom",
        translation_key="test_custom",
        is_on_fn=lambda data: True,
        available_fn=None,
    )
    sensor = PiKVMBinarySensor(mock_coordinator, "test_uid", desc)

    mock_coordinator.last_update_success = True
    assert sensor.available is True
    assert sensor.translation_key == "test_custom"

    mock_coordinator.last_update_success = False
    assert sensor.available is False


def test_pikvm_binary_sensor_empty_attributes(mock_coordinator):
    """Test PiKVMBinarySensor when attributes_fn returns empty dictionary (branch coverage)."""
    throttling_desc = next(
        d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "throttling"
    )
    sensor = PiKVMBinarySensor(mock_coordinator, "test_uid", throttling_desc)
    mock_coordinator.data = {"hw": {"health": {"throttling": {}}}}
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}


def test_pikvm_extra_binary_sensor_empty_attributes(mock_coordinator):
    """Test extra binary sensor when extra_data is empty dictionary (branch coverage)."""
    extra_sensor = PiKVMBinarySensor(
        mock_coordinator, "test_uid", _make_extra_description("vnc")
    )
    mock_coordinator.data = {"extras": {"vnc": {}}}
    assert extra_sensor.extra_state_attributes == {"ip": "https://pikvm.local"}


def test_binary_sensor_descriptions_have_no_hardcoded_icons():
    """Verify binary sensor descriptions do not hardcode icons, allowing icons.json to take effect."""
    for desc in BINARY_SENSOR_DESCRIPTIONS:
        assert desc.icon is None


def test_binary_sensor_entity_icon_is_none(mock_coordinator):
    """Verify binary sensor entities do not define icon, allowing icons.json to take effect."""
    for desc in BINARY_SENSOR_DESCRIPTIONS:
        sensor = PiKVMBinarySensor(mock_coordinator, "test_uid", desc)
        assert sensor.icon is None

    extra_sensor = PiKVMBinarySensor(
        mock_coordinator, "test_uid", _make_extra_description("vnc")
    )
    assert extra_sensor.icon is None


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry_unknown_serial(hass, mock_coordinator):
    """Test setup_entry preserves existing entities when unique_id_base ends with _unknown."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_unknown",
        data={},
    )
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    existing_entity = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "existing_unique_id",
        config_entry=entry,
    )
    assert ent_reg.async_get(existing_entity.entity_id) is not None

    entry.runtime_data = mock_coordinator

    mock_add_entities = MagicMock()
    with patch(
        "custom_components.pikvm.binary_sensor.get_unique_id_base",
        return_value="mock_entry_unknown_unknown",
    ):
        await async_setup_entry(hass, entry, mock_add_entities)

    # Existing entity should NOT be removed because unique_id_base ends in _unknown
    assert ent_reg.async_get(existing_entity.entity_id) is not None


def test_binary_sensor_throttling_defensive_telemetry(
    mock_coordinator: MagicMock,
) -> None:
    """Test throttling binary sensor handles missing, null, and malformed telemetry safely."""
    throttling_desc = next(
        d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "throttling"
    )
    sensor = PiKVMBinarySensor(mock_coordinator, "test_uid", throttling_desc)

    # 1. Null health -> unavailable, not on, empty extra attributes
    mock_coordinator.data = {"hw": {"health": None}}
    assert sensor.available is False
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # 2. Null hw -> unavailable, not on
    mock_coordinator.data = {"hw": None}
    assert sensor.available is False
    assert sensor.is_on is False

    # 3. Non-mapping hw/health
    mock_coordinator.data = {"hw": "invalid"}
    assert sensor.available is False
    mock_coordinator.data = {"hw": {"health": "invalid"}}
    assert sensor.available is False

    # 4. Null raw_flags -> is_on False
    mock_coordinator.data = {"hw": {"health": {"throttling": {"raw_flags": None}}}}
    assert sensor.is_on is False

    # 5. Non-numeric / zero / negative raw_flags -> is_on False
    mock_coordinator.data = {"hw": {"health": {"throttling": {"raw_flags": False}}}}
    assert sensor.is_on is False
    mock_coordinator.data = {"hw": {"health": {"throttling": {"raw_flags": 0}}}}
    assert sensor.is_on is False
    mock_coordinator.data = {"hw": {"health": {"throttling": {"raw_flags": -1}}}}
    assert sensor.is_on is False
    mock_coordinator.data = {
        "hw": {"health": {"throttling": {"raw_flags": "invalid_flags"}}}
    }
    assert sensor.is_on is False
    mock_coordinator.data = {
        "hw": {"health": {"throttling": {"raw_flags": float("nan")}}}
    }
    assert sensor.is_on is False
    mock_coordinator.data = {
        "hw": {"health": {"throttling": {"raw_flags": float("inf")}}}
    }
    assert sensor.is_on is False

    # 6. Non-mapping throttling -> attributes fallback to {"ip": ...}
    mock_coordinator.data = {"hw": {"health": {"throttling": "invalid_string"}}}
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}
    mock_coordinator.data = {"hw": {"health": {"throttling": 12345}}}
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # 7. Health is Mapping without throttling key, but hw has health
    mock_coordinator.data = {"hw": {"health": {}}}
    assert sensor.available is True


def test_binary_sensor_msd_defensive_telemetry(mock_coordinator: MagicMock) -> None:
    """Test MSD binary sensors handle null and malformed telemetry safely."""
    drive_desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "msd_drive")
    enabled_desc = next(
        d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "msd_enabled"
    )
    sensor_drive = PiKVMBinarySensor(mock_coordinator, "test_uid", drive_desc)
    sensor_enabled = PiKVMBinarySensor(mock_coordinator, "test_uid", enabled_desc)

    # 1. Null drive -> unavailable, is_on False, fallback attributes
    mock_coordinator.data = {"msd": {"drive": None}}
    assert sensor_drive.available is False
    assert sensor_drive.is_on is False
    assert sensor_drive.extra_state_attributes == {"ip": "https://pikvm.local"}

    # 2. Non-mapping drive -> unavailable, fallback attributes
    mock_coordinator.data = {"msd": {"drive": "invalid_drive"}}
    assert sensor_drive.available is False
    assert sensor_drive.extra_state_attributes == {"ip": "https://pikvm.local"}

    # 3. Non-mapping msd -> unavailable
    mock_coordinator.data = {"msd": "invalid_msd"}
    assert sensor_enabled.available is False
    assert sensor_enabled.is_on is False
    assert sensor_drive.is_on is False

    # 4. Unparseable data -> is_on False
    mock_coordinator.data = "not_a_dict"
    assert sensor_enabled.is_on is False
    assert sensor_drive.is_on is False

    # 5. Valid msd enabled
    mock_coordinator.data = {"msd": {"is_enabled": True}}
    assert sensor_enabled.available is True
    assert sensor_enabled.is_on is True


def test_pikvm_extra_binary_sensor_defensive_telemetry(
    mock_coordinator: MagicMock,
) -> None:
    """Test extra binary sensor handles null and non-mapping service payloads safely."""
    sensor = PiKVMBinarySensor(
        mock_coordinator, "test_uid", _make_extra_description("vnc")
    )

    # 1. Null extras mapping -> unavailable
    mock_coordinator.data = {"extras": None}
    assert sensor.available is False

    # 2. Non-mapping extras -> unavailable
    mock_coordinator.data = {"extras": "invalid_extras"}
    assert sensor.available is False

    # 3. Null extra service data -> is_on False, fallback attributes
    mock_coordinator.data = {"extras": {"vnc": None}}
    assert sensor.available is True
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # 4. Non-mapping extra service data (string, int, bool) -> is_on False, fallback attributes
    mock_coordinator.data = {"extras": {"vnc": "invalid_data"}}
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    mock_coordinator.data = {"extras": {"vnc": 12345}}
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    mock_coordinator.data = {"extras": {"vnc": True}}
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # 5. Valid mapping with is_running False
    mock_coordinator.data = {"extras": {"vnc": {"is_running": False}}}
    assert sensor.is_on is False


@pytest.mark.asyncio
async def test_binary_sensor_setup_and_cleanup_null_extras(
    hass: Any, mock_coordinator: MagicMock
) -> None:
    """Test async_setup_entry handles null extras safely."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_null_extras",
        data={"host": "https://pikvm.local", "serial": "sn_null_extras"},
    )
    entry.add_to_hass(hass)
    mock_coordinator.data = {"extras": None}
    entry.runtime_data = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    # Only the 3 standard binary sensors should be registered (no extras crashed setup)
    assert mock_add_entities.call_count == 1
    entities = mock_add_entities.call_args[0][0]
    assert len(entities) == 3

    # Setup with non-dict extra_data item
    entry_bad_extra = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_bad_extra",
        data={"host": "https://pikvm.local", "serial": "sn_bad_extra"},
    )
    entry_bad_extra.add_to_hass(hass)
    mock_coordinator.data = {"extras": {"broken": None, "valid": {"is_running": True}}}
    entry_bad_extra.runtime_data = mock_coordinator

    mock_add_entities.reset_mock()
    await async_setup_entry(hass, entry_bad_extra, mock_add_entities)
    assert mock_add_entities.call_count == 1
    entities = mock_add_entities.call_args[0][0]
    assert len(entities) == 5


def test_pikvm_binary_sensor_attributes_fn_non_mapping(
    mock_coordinator: MagicMock,
) -> None:
    """Test PiKVMBinarySensor when attributes_fn returns non-mapping truthy value."""
    desc = PiKVMBinarySensorEntityDescription(
        key="test_custom",
        translation_key="test_custom",
        is_on_fn=lambda data: True,
        attributes_fn=lambda data: "not_a_dict",  # type: ignore[return-value]
    )
    sensor = PiKVMBinarySensor(mock_coordinator, "test_uid", desc)
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}


def test_helper_functions_direct() -> None:
    """Test defensive helper functions directly for edge cases."""
    # _get_throttling_attributes
    assert _get_throttling_attributes(
        {"hw": {"health": {"throttling": {"flag": 1}}}}
    ) == {"flag": 1}
    assert _get_throttling_attributes({"hw": {"health": {"throttling": None}}}) == {}
    assert _get_throttling_attributes({}) == {}

    # _get_msd_drive_attributes
    assert _get_msd_drive_attributes({"msd": {"drive": {"is_mounted": True}}}) == {
        "is_mounted": True
    }
    assert _get_msd_drive_attributes({"msd": {"drive": None}}) == {}
    assert _get_msd_drive_attributes({}) == {}

    # _is_throttling_on
    assert (
        _is_throttling_on({"hw": {"health": {"throttling": {"raw_flags": 4}}}}) is True
    )
    assert (
        _is_throttling_on({"hw": {"health": {"throttling": {"raw_flags": 0}}}}) is False
    )
    assert _is_throttling_on({}) is False
    assert _is_throttling_on("invalid") is False
