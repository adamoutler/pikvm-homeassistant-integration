"""Tests for the sensor platform in the PiKVM integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
)

from custom_components.pikvm.sensor import (
    CPU_TEMP_SENSOR_DESCRIPTION,
    CPU_UTILIZATION_SENSOR_DESCRIPTION,
    FAN_SPEED_SENSOR_DESCRIPTION,
    MEMORY_UTILIZATION_SENSOR_DESCRIPTION,
    MSD_STORAGE_SENSOR_DESCRIPTION,
    SENSOR_DESCRIPTIONS,
    PiKVMSensor,
    _get_cpu_temp,
    _get_cpu_utilization,
    _get_fan_attributes,
    _get_fan_speed,
    _get_memory_attributes,
    _get_memory_utilization,
    _get_msd_storage,
    _get_msd_storage_attributes,
)
from custom_components.pikvm.utils import bytes_to_mb, get_unique_id_base


@pytest.fixture
def mock_coordinator():
    """Fixture for a mock coordinator with full telemetry data."""
    coordinator = MagicMock()
    coordinator.url = "https://pikvm.local"
    coordinator.last_update_success = True
    coordinator.data = {
        "hw": {
            "health": {
                "temp": {"cpu": 45.5},
                "throttling": {
                    "raw_flags": 0,
                    "text_flags": [],
                    "voltage": {"core": {"now": False, "past": False}},
                },
            },
            "performance": {
                "cpu": {"utilization": 15.2},
                "memory": {
                    "utilization": 30.8,
                    "available": 524288000,
                    "total": 1048576000,
                },
                "fan": {"speed": 1234, "status": "ok"},
            },
        },
        "msd": {
            "is_enabled": True,
            "drive": {"is_mounted": True},
            "storage": {
                "available": 987654321,
                "total": 1000000000,
                "images": {
                    "ubuntu.iso": {"size": 750000000},
                },
            },
        },
    }
    return coordinator


def test_sensor_descriptions_count():
    """Test that SENSOR_DESCRIPTIONS contains all 5 numeric sensor descriptions."""
    assert len(SENSOR_DESCRIPTIONS) == 5
    keys = [desc.key for desc in SENSOR_DESCRIPTIONS]
    assert keys == [
        "cpu_temp",
        "cpu_utilization",
        "memory_utilization",
        "fan_speed",
        "msd_storage",
    ]


def test_cpu_temp_sensor(mock_coordinator):
    """Test PiKVMSensor instantiated with CPU_TEMP_SENSOR_DESCRIPTION."""
    sensor = PiKVMSensor(mock_coordinator, "test_id", CPU_TEMP_SENSOR_DESCRIPTION)
    assert sensor.unique_id == "test_id_cpu_temp"
    assert sensor.translation_key == "cpu_temp"
    assert sensor.device_class == SensorDeviceClass.TEMPERATURE
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert sensor.suggested_display_precision == 1
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.has_entity_name is True
    assert sensor.native_value == 45.5
    assert sensor.available is True
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}


def test_cpu_utilization_sensor(mock_coordinator):
    """Test PiKVMSensor instantiated with CPU_UTILIZATION_SENSOR_DESCRIPTION."""
    sensor = PiKVMSensor(mock_coordinator, "test_id", CPU_UTILIZATION_SENSOR_DESCRIPTION)
    assert sensor.unique_id == "test_id_cpu_utilization"
    assert sensor.translation_key == "cpu_utilization"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_unit_of_measurement == PERCENTAGE
    assert sensor.suggested_display_precision == 1
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.native_value == 15.2
    assert sensor.available is True
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}


def test_memory_utilization_sensor(mock_coordinator):
    """Test PiKVMSensor instantiated with MEMORY_UTILIZATION_SENSOR_DESCRIPTION."""
    sensor = PiKVMSensor(mock_coordinator, "test_id", MEMORY_UTILIZATION_SENSOR_DESCRIPTION)
    assert sensor.unique_id == "test_id_memory_utilization"
    assert sensor.translation_key == "memory_utilization"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_unit_of_measurement == PERCENTAGE
    assert sensor.suggested_display_precision == 1
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.native_value == 30.8
    assert sensor.available is True

    attrs = sensor.extra_state_attributes
    assert attrs["ip"] == "https://pikvm.local"
    assert attrs["available MB"] == pytest.approx(500.0)
    assert attrs["total MB"] == pytest.approx(1000.0)


def test_fan_speed_sensor(mock_coordinator):
    """Test PiKVMSensor instantiated with FAN_SPEED_SENSOR_DESCRIPTION."""
    sensor = PiKVMSensor(mock_coordinator, "test_id", FAN_SPEED_SENSOR_DESCRIPTION)
    assert sensor.unique_id == "test_id_fan_speed"
    assert sensor.translation_key == "fan_speed"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_unit_of_measurement == REVOLUTIONS_PER_MINUTE
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.native_value == 1234
    assert sensor.available is True
    assert sensor.extra_state_attributes == {
        "ip": "https://pikvm.local",
        "speed": 1234,
        "status": "ok",
    }


def test_msd_storage_sensor(mock_coordinator):
    """Test PiKVMSensor instantiated with MSD_STORAGE_SENSOR_DESCRIPTION."""
    sensor = PiKVMSensor(mock_coordinator, "test_id", MSD_STORAGE_SENSOR_DESCRIPTION)
    assert sensor.unique_id == "test_id_msd_storage"
    assert sensor.translation_key == "msd_storage"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_unit_of_measurement == PERCENTAGE
    assert sensor.suggested_display_precision == 2
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.native_value == 1.23
    assert sensor.available is True

    attrs = sensor.extra_state_attributes
    assert attrs["ip"] == "https://pikvm.local"
    assert attrs["total_size_mb"] == pytest.approx(953.67)
    assert attrs["free_size_mb"] == pytest.approx(941.90)
    assert attrs["used_size_mb"] == pytest.approx(11.77)
    assert attrs["percent_used"] == 1.23
    assert attrs["ubuntu.iso"] == 750000000


def test_get_cpu_temp_error_handling():
    """Test _get_cpu_temp valid values, None handling, and ValueError/TypeError handling."""
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": 42.5}}}}) == 42.5
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": 40}}}}) == 40.0
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": "43.2"}}}}) == 43.2
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": None}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {}}}}) is None
    assert _get_cpu_temp({}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": "not_a_number"}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": ["invalid_type"]}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": {"nested": "dict"}}}}}) is None


def test_get_cpu_utilization_error_handling():
    """Test _get_cpu_utilization valid values, None, and ValueError/TypeError handling."""
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": 15.5}}}}) == 15.5
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": 20}}}}) == 20.0
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": "25.0"}}}}) == 25.0
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": None}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {}}}}) is None
    assert _get_cpu_utilization({}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": "invalid"}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": [50.0]}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": {}}}}}) is None


def test_get_memory_utilization_error_handling():
    """Test _get_memory_utilization valid values, None, and ValueError/TypeError handling."""
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": 60.5}}}}) == 60.5
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": 50}}}}) == 50.0
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": "70.2"}}}}) == 70.2
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": None}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {}}}}) is None
    assert _get_memory_utilization({}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": "bad_value"}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": ["bad"]}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": {}}}}}) is None


def test_get_fan_speed_error_handling():
    """Test _get_fan_speed valid values, None, and ValueError/TypeError/OverflowError handling."""
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": 2400}}}}) == 2400
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": "3000"}}}}) == 3000
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": None}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {}}}}) is None
    assert _get_fan_speed({}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": "fast"}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": "12.34"}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": [2400]}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": {"rpm": 2400}}}}}) is None
    # Float infinity and overflow handling
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": float("inf")}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": float("-inf")}}}}) is None
    # Bounds and huge integer overflow
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": 10**400}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": -5}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": 150_000}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": 0}}}}) == 0
    # Fallback to ["hw", "fan", "speed"]
    assert _get_fan_speed({"hw": {"fan": {"speed": 1800}}}) == 1800
    assert _get_fan_speed({"hw": {"fan": {"speed": "2100"}}}) == 2100


def test_sensor_helper_memory_and_fan_attributes():
    """Test _get_memory_attributes and _get_fan_attributes branches."""
    data_full = {
        "hw": {
            "performance": {
                "memory": {
                    "available": 1048576,
                    "total": 2097152,
                },
                "fan": {
                    "speed": 1500,
                    "status": "ok",
                },
            }
        }
    }
    mem_attrs = _get_memory_attributes(data_full)
    assert mem_attrs["available MB"] == 1.0
    assert mem_attrs["total MB"] == 2.0

    fan_attrs = _get_fan_attributes(data_full)
    assert fan_attrs == {"speed": 1500, "status": "ok"}

    assert _get_memory_attributes({}) == {}
    assert _get_memory_attributes({"hw": {"performance": {"memory": {}}}}) == {}

    assert _get_fan_attributes({}) == {}
    assert _get_fan_attributes({"hw": {"performance": {"fan": None}}}) == {}
    assert _get_fan_attributes({"hw": {"performance": {"fan": "not_a_dict"}}}) == {}
    # Fallback to ["hw", "fan"]
    assert _get_fan_attributes({"hw": {"fan": {"speed": 1600, "status": "ok"}}}) == {
        "speed": 1600,
        "status": "ok",
    }


def test_sensor_helper_msd_storage_and_attributes():
    """Test _get_msd_storage and _get_msd_storage_attributes coverage and branches."""
    assert _get_msd_storage({}) is None
    assert _get_msd_storage({"msd": {"storage": "invalid_non_dict"}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 0, "available": 0}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": -100, "available": 10}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": None, "available": 10}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 100, "available": None}}}) is None

    # String representations of numbers and 'free' key
    assert _get_msd_storage({"msd": {"storage": {"total": "1000", "available": "500"}}}) == 50.0
    assert _get_msd_storage({"msd": {"storage": {"total": 1000, "free": 200}}}) == 80.0
    assert _get_msd_storage({"msd": {"storage": {"total": "1000", "free": "300"}}}) == 70.0
    assert _get_msd_storage({"msd": {"storage": {"total": 1000, "available": 2000}}}) == 0.0

    # Non-finite numbers & exception branches (lines 121-122)
    assert _get_msd_storage({"msd": {"storage": {"total": float("inf"), "available": 500}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 1000, "available": float("inf")}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": "bad", "available": 500}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 1000, "available": "bad"}}}) is None

    # Invalid non-dict storage in attributes
    assert _get_msd_storage_attributes({"msd": {"storage": "invalid_type"}}) == {}

    # Partial storage data (total only, available only)
    attrs_total_only = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": 1048576}}}
    )
    assert attrs_total_only["total_size_mb"] == 1.0
    assert "free_size_mb" not in attrs_total_only
    assert "used_size_mb" not in attrs_total_only

    attrs_avail_only = _get_msd_storage_attributes(
        {"msd": {"storage": {"available": 1048576}}}
    )
    assert attrs_avail_only["free_size_mb"] == 1.0
    assert "total_size_mb" not in attrs_avail_only
    assert "used_size_mb" not in attrs_avail_only

    # Attributes with 'free' key and string numbers
    attrs_free = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": "1000000000", "free": "500000000"}}}
    )
    assert attrs_free["percent_used"] == 50.0
    assert "total_size_mb" in attrs_free
    assert "free_size_mb" in attrs_free
    assert "used_size_mb" in attrs_free

    # Attributes with bad total/available triggering exception branch (lines 157-158)
    attrs_bad = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": "bad_total", "available": 500000}}}
    )
    assert "used_size_mb" not in attrs_bad

    # Attributes with invalid available and non-finite total
    attrs_invalid_avail = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": 1000, "available": "not_a_number"}}}
    )
    assert "free_size_mb" not in attrs_invalid_avail

    attrs_inf_total = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": float("inf"), "available": 500}}}
    )
    assert "used_size_mb" not in attrs_inf_total

    # Attributes where used bytes overflows to infinity
    attrs_overflow_used = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": 1e308, "available": -1e308}}}
    )
    assert "used_size_mb" not in attrs_overflow_used

    data_valid = {
        "msd": {
            "storage": {
                "total": 1048576000,
                "available": 524288000,
                "images": {
                    "boot.iso": {"size": 209715200},
                    "empty.iso": {"size": None},
                    "invalid_entry": "not_a_dict",
                },
            }
        }
    }
    assert _get_msd_storage(data_valid) == 50.0

    attrs = _get_msd_storage_attributes(data_valid)
    assert attrs["percent_used"] == 50.0
    assert attrs["boot.iso"] == 209715200
    assert "empty.iso" not in attrs
    assert "invalid_entry" not in attrs

    # Images >= 20 branch
    images_large = {f"img_{i}.iso": {"size": 1000} for i in range(25)}
    data_large = {
        "msd": {
            "storage": {
                "total": 1000000,
                "available": 500000,
                "images": images_large,
            }
        }
    }
    attrs_large = _get_msd_storage_attributes(data_large)
    assert attrs_large["file count"] == 25


def test_sensor_descriptions_available_fn():
    """Test available_fn closures across all SENSOR_DESCRIPTIONS."""
    valid_data = {
        "hw": {
            "health": {"temp": {"cpu": 45.0}},
            "performance": {
                "cpu": {"utilization": 20.0},
                "memory": {"utilization": 40.0},
                "fan": {"speed": 1200},
            },
        },
        "msd": {
            "storage": {"total": 1000, "available": 500},
        },
    }
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn is not None
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn(valid_data) is True

    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn is not None
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn(valid_data) is True

    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn is not None
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn(valid_data) is True

    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn is not None
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn(valid_data) is True

    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn is not None
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn(valid_data) is True

    empty_data: dict[str, object] = {}
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn(empty_data) is False

    # Intermediate keys None and raw None inputs
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn(None) is False
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn({"hw": None}) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn(None) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": None}) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": None}}) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn(None) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": None}) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": None}}) is False
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn(None) is False
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn({"hw": None}) is False
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": None}}) is False
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn(None) is False
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn({"msd": None}) is False
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn({"msd": {"storage": None}}) is False


def test_sensor_unavailable_when_coordinator_fails(mock_coordinator):
    """Test PiKVMSensor available returns False when coordinator last_update_success is False."""
    sensor = PiKVMSensor(mock_coordinator, "test_id", CPU_TEMP_SENSOR_DESCRIPTION)
    assert sensor.available is True

    mock_coordinator.last_update_success = False
    assert sensor.available is False


def test_bytes_to_mb_handles_none():
    """Test bytes_to_mb returns None when given None."""
    assert bytes_to_mb(None) is None
    assert bytes_to_mb(1048576) == 1.0


def test_bytes_to_mb_invalid():
    """Test bytes_to_mb returns None on invalid non-numeric inputs."""
    assert bytes_to_mb("invalid") is None
    assert bytes_to_mb([123]) is None


def test_get_unique_id_base_host_port_variants():
    """Test get_unique_id_base with host and port signatures and protocol stripping."""
    assert get_unique_id_base("https://pikvm.local:8443/", 443) == "pikvm.local_8443_443"
    assert get_unique_id_base("http://192.168.1.100/", 80) == "192.168.1.100_80"
    assert get_unique_id_base("pikvm.local", 443) == "pikvm.local_443"


def test_sensors_numeric_hardening_overflow_and_non_finite():
    """Test _get_* functions handle 10**400, NaN, and Inf by returning None."""
    huge_int = 10**400

    # _get_cpu_temp
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": huge_int}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": float("nan")}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": float("inf")}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": float("-inf")}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": "nan"}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": "inf"}}}}) is None

    # _get_cpu_utilization
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": huge_int}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": float("nan")}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": float("inf")}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": float("-inf")}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": "nan"}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": "inf"}}}}) is None

    # _get_memory_utilization
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": huge_int}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": float("nan")}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": float("inf")}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": float("-inf")}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": "nan"}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": "inf"}}}}) is None

    # _get_msd_storage
    assert _get_msd_storage({"msd": {"storage": {"total": huge_int, "available": 500}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 1000, "available": huge_int}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": float("nan"), "available": 500}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 1000, "available": float("nan")}}}) is None

    # _get_msd_storage_attributes with huge_int
    attrs_overflow = _get_msd_storage_attributes(
        {"msd": {"storage": {"total": huge_int, "available": huge_int}}}
    )
    assert attrs_overflow == {}

    # available_fn behavior with huge_int and nan
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn({"hw": {"health": {"temp": {"cpu": huge_int}}}}) is False
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn({"hw": {"health": {"temp": {"cpu": float("nan")}}}}) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": {"cpu": {"utilization": huge_int}}}}) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": {"cpu": {"utilization": float("nan")}}}}) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": {"memory": {"utilization": huge_int}}}}) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn({"hw": {"performance": {"memory": {"utilization": float("nan")}}}}) is False
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn({"msd": {"storage": {"total": huge_int, "available": 500}}}) is False


def test_sensor_descriptions_have_no_hardcoded_icons() -> None:
    """Verify sensor descriptions do not hardcode icons, allowing icons.json to take effect."""
    for desc in SENSOR_DESCRIPTIONS:
        assert desc.icon is None


def test_sensor_entity_icon_is_none(mock_coordinator) -> None:
    """Verify sensor entities do not define icon, allowing icons.json to take effect."""
    for desc in SENSOR_DESCRIPTIONS:
        sensor = PiKVMSensor(mock_coordinator, "test_uid", desc)
        assert sensor.icon is None




