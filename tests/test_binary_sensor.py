"""Tests for the PiKVM binary sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    PiKVMBinarySensor,
    PiKVMBinarySensorEntityDescription,
    PiKVMExtraBinarySensor,
    _async_cleanup_legacy_sensors,
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
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    assert mock_add_entities.call_count == 1
    entities = mock_add_entities.call_args[0][0]
    # 3 standard (throttling, msd_enabled, msd_drive) + 2 extras (vnc, ipmi) = 5
    assert len(entities) == 5

    keys = [e.entity_description.key if hasattr(e, "entity_description") else e._extra_name for e in entities]
    assert "throttling" in keys
    assert "msd_enabled" in keys
    assert "msd_drive" in keys
    assert "vnc" in keys
    assert "ipmi" in keys


@pytest.mark.asyncio
async def test_cleanup_legacy_sensors(hass, mock_coordinator):
    """Test _async_cleanup_legacy_sensors removes old sensor entries."""
    ent_reg = er.async_get(hass)
    unique_id_base = "sn_123"

    old_entity = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{unique_id_base}_throttling",
        suggested_object_id="pikvm_throttling",
    )
    assert ent_reg.async_get(old_entity.entity_id) is not None

    _async_cleanup_legacy_sensors(hass, unique_id_base, mock_coordinator.data)
    assert ent_reg.async_get(old_entity.entity_id) is None


def test_pikvm_binary_sensor_properties(mock_coordinator):
    """Test PiKVMBinarySensor properties, states, attributes, and availability."""
    throttling_desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "throttling")
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
    enabled_desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "msd_enabled")
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

    # Test when MSD is None
    mock_coordinator.data["msd"] = None
    assert sensor_enabled.available is False
    assert sensor_drive.available is False


def test_pikvm_extra_binary_sensor(mock_coordinator):
    """Test PiKVMExtraBinarySensor."""
    extra_sensor = PiKVMExtraBinarySensor(
        coordinator=mock_coordinator,
        extra_name="vnc",
        extra_data={"is_running": True, "port": 5900},
        unique_id_base="test_uid",
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

