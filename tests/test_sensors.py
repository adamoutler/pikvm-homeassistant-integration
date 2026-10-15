"""Tests for the sensor platform in the PiKVM integration."""

from unittest.mock import MagicMock, patch
import pytest

from homeassistant.const import UnitOfTemperature, PERCENTAGE, REVOLUTIONS_PER_MINUTE

from custom_components.pikvm.sensors.pikvm_cpu_temp_sensor import (
    PiKVMCpuTempSensor,
    convert_temperature,
)
from custom_components.pikvm.sensors.pikvm_cpu_utilization_sensor import PiKVMCpuUtilizationSensor
from custom_components.pikvm.sensors.pikvm_memory_utilization_sensor import PiKVMMemoryUtilizationSensor
from custom_components.pikvm.sensors.pikvm_fan_speed_sensor import PiKVMFanSpeedSensor
from custom_components.pikvm.sensors.pikvm_throttling_sensor import PiKVMThrottlingSensor
from custom_components.pikvm.sensors.pikvm_msd_enabled_sensor import PiKVMSDEnabledSensor
from custom_components.pikvm.sensors.pikvm_msd_drive_sensor import PiKVMSDDriveSensor
from custom_components.pikvm.sensors.pikvm_msd_storage_sensor import PiKVMSDStorageSensor
from custom_components.pikvm.sensors.pikvm_extra_sensor import PiKVMExtraSensor
from custom_components.pikvm.sensor import (
    CPU_TEMP_SENSOR_DESCRIPTION,
    CPU_UTILIZATION_SENSOR_DESCRIPTION,
    FAN_SPEED_SENSOR_DESCRIPTION,
    MEMORY_UTILIZATION_SENSOR_DESCRIPTION,
    MSD_STORAGE_SENSOR_DESCRIPTION,
    _get_cpu_temp,
    _get_cpu_utilization,
    _get_fan_attributes,
    _get_fan_speed,
    _get_memory_attributes,
    _get_memory_utilization,
    _get_msd_storage,
    _get_msd_storage_attributes,
)


@pytest.fixture
def mock_coordinator():
    """Fixture for a mock coordinator."""
    coordinator = MagicMock()
    coordinator.url = "https://pikvm.local"
    coordinator.data = {
        "hw": {
            "health": {
                "temp": {"cpu": 45.5},
                "throttling": {
                    "raw_flags": 0,
                    "text_flags": [],
                    "voltage": {
                        "core": {
                            "now": False,
                            "past": False
                        }
                    }
                }
            },
            "performance": {
                "cpu": {"utilization": 15.2},
                "memory": {"utilization": 30.8},
                "fan": {"speed": 1234}
            }
        },
        "msd": {
            "is_enabled": True,
            "drive": {"is_mounted": True},
            "storage": {"available": 987654321, "total": 1000000000}
        },
        "extras": {
            "vnc": {"is_running": True}
        }
    }
    # Mock the Home Assistant specific parts
    coordinator.hass.config.units.temperature_unit = UnitOfTemperature.CELSIUS
    def temperature_converter(value, from_unit):
        return value # Simplified for testing
    coordinator.hass.config.units.temperature = temperature_converter

    return coordinator

def test_cpu_temp_sensor(mock_coordinator):
    """Test the PiKVMCpuTempSensor."""
    sensor = PiKVMCpuTempSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_cpu_temp"
    assert sensor.name == "Test PiKVM CPU Temp"
    assert sensor.state == 45.5
    assert sensor.unit_of_measurement == UnitOfTemperature.CELSIUS

def test_cpu_utilization_sensor(mock_coordinator):
    """Test the PiKVMCpuUtilizationSensor."""
    sensor = PiKVMCpuUtilizationSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_cpu_utilization"
    assert sensor.name == "Test PiKVM CPU Utilization"
    assert sensor.state == 15.2
    assert sensor.unit_of_measurement == PERCENTAGE

def test_memory_utilization_sensor(mock_coordinator):
    """Test the PiKVMMemoryUtilizationSensor."""
    sensor = PiKVMMemoryUtilizationSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_memory_utilization"
    assert sensor.name == "Test PiKVM Memory Utilization"
    assert sensor.state == 30.8
    assert sensor.unit_of_measurement == PERCENTAGE

def test_fan_speed_sensor(mock_coordinator):
    """Test the PiKVMFanSpeedSensor."""
    sensor = PiKVMFanSpeedSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_fan_speed"
    assert sensor.name == "Test PiKVM Fan Speed"
    assert sensor.state == 1234
    assert sensor.unit_of_measurement == REVOLUTIONS_PER_MINUTE

def test_throttling_sensor(mock_coordinator):
    """Test the PiKVMThrottlingSensor."""
    sensor = PiKVMThrottlingSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_throttling"
    assert sensor.name == "Test PiKVM Throttling"
    assert sensor.state is False

def test_msd_enabled_sensor(mock_coordinator):
    """Test the PiKVMSDEnabledSensor."""
    sensor = PiKVMSDEnabledSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_msd_enabled"
    assert sensor.name == "Test PiKVM MSD Enabled"
    assert sensor.state is True

def test_msd_drive_sensor(mock_coordinator):
    """Test the PiKVMSDDriveSensor."""
    sensor = PiKVMSDDriveSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_msd_drive"
    assert sensor.name == "Test PiKVM MSD Drive"
    assert sensor.state == "on"

def test_msd_storage_sensor(mock_coordinator):
    """Test the PiKVMSDStorageSensor."""
    sensor = PiKVMSDStorageSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_msd_storage"
    assert sensor.name == "Test PiKVM MSD Storage"
    assert sensor.state == 1.23
    assert sensor.extra_state_attributes["total_size_mb"] == pytest.approx(953.67)
    assert sensor.extra_state_attributes["free_size_mb"] == pytest.approx(941.9)

def test_extra_sensor(mock_coordinator):
    """Test the PiKVMExtraSensor."""
    extra_name = "vnc"
    extra_data = mock_coordinator.data["extras"]["vnc"]
    sensor = PiKVMExtraSensor(mock_coordinator, extra_name, extra_data, "test_id", "Test PiKVM")
    assert sensor.unique_id == "test_id_extra_vnc"
    assert sensor.name == "Test PiKVM Vnc"
    assert sensor.state is True


# ---------------------------------------------------------------------------
# Coverage for pikvm_cpu_temp_sensor.py (lines 18-20, 49-50, 63)
# ---------------------------------------------------------------------------

def test_convert_temperature_same_unit():
    """Test convert_temperature returns unchanged value when units match (lines 18-19)."""
    assert convert_temperature(45.5, UnitOfTemperature.CELSIUS, UnitOfTemperature.CELSIUS) == 45.5


def test_convert_temperature_different_unit():
    """Test convert_temperature delegates to temperature.convert_temperature when units differ (line 20)."""
    with patch(
        "custom_components.pikvm.sensors.pikvm_cpu_temp_sensor.temperature.convert_temperature",
        create=True,
        return_value=113.9,
    ) as mock_conv:
        result = convert_temperature(45.5, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT)
        assert result == 113.9
        mock_conv.assert_called_once_with(
            45.5, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
        )


def test_cpu_temp_sensor_invalid_state_and_attributes(mock_coordinator):
    """Test PiKVMCpuTempSensor error handling on invalid temp and extra attributes (lines 49-50, 63)."""
    sensor = PiKVMCpuTempSensor(mock_coordinator, "test_id", "Test PiKVM")

    # Line 63: super().extra_state_attributes
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # Lines 49-50: TypeError when cpu temp is None or missing
    mock_coordinator.data["hw"]["health"]["temp"]["cpu"] = None
    assert sensor.state is None

    # Lines 49-50: ValueError when cpu temp is non-numeric string
    mock_coordinator.data["hw"]["health"]["temp"]["cpu"] = "invalid_temp"
    assert sensor.state is None

    # Lines 49-50: KeyError/missing subdict returns None via get_nested_value -> TypeError
    mock_coordinator.data["hw"]["health"] = {}
    assert sensor.state is None


# ---------------------------------------------------------------------------
# Coverage for pikvm_cpu_utilization_sensor.py (lines 45, 55)
# ---------------------------------------------------------------------------

def test_cpu_utilization_sensor_available_and_attributes(mock_coordinator):
    """Test PiKVMCpuUtilizationSensor available and extra_state_attributes (lines 45, 55)."""
    sensor = PiKVMCpuUtilizationSensor(mock_coordinator, "test_id", "Test PiKVM")

    # Line 45 (True branch)
    assert sensor.available is True

    # Line 55: super().extra_state_attributes
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # Line 45 (False branch)
    mock_coordinator.data["hw"] = {}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Coverage for pikvm_extra_sensor.py (lines 45-50)
# ---------------------------------------------------------------------------

def test_extra_sensor_extra_state_attributes(mock_coordinator):
    """Test PiKVMExtraSensor extra_state_attributes with and without extra data (lines 45-50)."""
    extra_name = "vnc"
    extra_data = {"is_running": True, "port": 5900}
    mock_coordinator.data["extras"]["vnc"] = extra_data

    sensor = PiKVMExtraSensor(mock_coordinator, extra_name, extra_data, "test_id", "Test PiKVM")

    # Lines 45-50: super().extra_state_attributes merged with extras data
    assert sensor.extra_state_attributes == {
        "ip": "https://pikvm.local",
        "is_running": True,
        "port": 5900,
    }

    # When extras has no data for this sensor key
    mock_coordinator.data["extras"] = {}
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}


# ---------------------------------------------------------------------------
# Coverage for pikvm_fan_speed_sensor.py (lines 22, 32-36)
# ---------------------------------------------------------------------------

def test_fan_speed_sensor_available_and_attributes(mock_coordinator):
    """Test PiKVMFanSpeedSensor available and extra_state_attributes branches (lines 22, 32-36)."""
    sensor = PiKVMFanSpeedSensor(mock_coordinator, "test_id", "Test PiKVM")

    # Line 22 (True branch)
    assert sensor.available is True

    # Lines 32-36 (True branch: fan_state is truthy)
    assert sensor.extra_state_attributes == {
        "ip": "https://pikvm.local",
        "speed": 1234,
    }

    # Lines 32-36 (False branch: fan_state is empty)
    mock_coordinator.data["hw"]["performance"]["fan"] = {}
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}

    # Line 22 (False branch: fan not in performance)
    mock_coordinator.data["hw"]["performance"] = {}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Coverage for pikvm_memory_utilization_sensor.py (lines 53, 63-74)
# ---------------------------------------------------------------------------

def test_memory_utilization_sensor_available(mock_coordinator):
    """Test available property of PiKVMMemoryUtilizationSensor."""
    sensor = PiKVMMemoryUtilizationSensor(mock_coordinator, "test_id", "Test PiKVM")
    # True when 'performance' is present
    assert sensor.available is True

    # False when 'performance' is missing
    mock_coordinator.data = {"hw": {}}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False


def test_memory_utilization_sensor_extra_state_attributes(mock_coordinator):
    """Test extra_state_attributes of PiKVMMemoryUtilizationSensor."""
    mock_coordinator.data = {
        "hw": {
            "performance": {
                "memory": {
                    "utilization": 50.0,
                    "available": 524288000,  # 500 MB
                    "total": 1048576000,     # 1000 MB
                }
            }
        }
    }
    sensor = PiKVMMemoryUtilizationSensor(mock_coordinator, "test_id", "Test PiKVM")
    attrs = sensor.extra_state_attributes
    assert attrs["ip"] == "https://pikvm.local"
    assert attrs["available MB"] == pytest.approx(500.0)
    assert attrs["total MB"] == pytest.approx(1000.0)

    # Test branches where available and total bytes are None/omitted
    mock_coordinator.data = {
        "hw": {
            "performance": {
                "memory": {
                    "utilization": 50.0,
                }
            }
        }
    }
    attrs_empty = sensor.extra_state_attributes
    assert "available MB" not in attrs_empty
    assert "total MB" not in attrs_empty


# ---------------------------------------------------------------------------
# Coverage for pikvm_msd_drive_sensor.py (lines 24-28)
# ---------------------------------------------------------------------------

def test_msd_drive_sensor_extra_state_attributes(mock_coordinator):
    """Test extra_state_attributes of PiKVMSDDriveSensor."""
    mock_coordinator.data = {
        "msd": {
            "drive": {
                "is_mounted": True,
                "image": "ubuntu-server.iso",
                "cdrom": True,
                "rw": False,
            }
        }
    }
    sensor = PiKVMSDDriveSensor(mock_coordinator, "test_id", "Test PiKVM")
    attrs = sensor.extra_state_attributes
    assert attrs["ip"] == "https://pikvm.local"
    assert attrs["is_mounted"] is True
    assert attrs["image"] == "ubuntu-server.iso"
    assert attrs["cdrom"] is True
    assert attrs["rw"] is False

    # Branch where drive_data is empty
    mock_coordinator.data = {"msd": {"drive": {}}}
    attrs_empty = sensor.extra_state_attributes
    assert attrs_empty == {"ip": "https://pikvm.local"}


# ---------------------------------------------------------------------------
# Coverage for pikvm_msd_storage_sensor.py (lines 32-33, 60-66)
# ---------------------------------------------------------------------------

def test_msd_storage_sensor_invalid_state(mock_coordinator):
    """Test state and attributes when MSD storage data is invalid or missing."""
    sensor = PiKVMSDStorageSensor(mock_coordinator, "test_id", "Test PiKVM")

    # total <= 0
    mock_coordinator.data = {"msd": {"storage": {"total": 0, "available": 0}}}
    assert sensor.state is None
    attrs = sensor.extra_state_attributes
    assert "percent_used" not in attrs

    # total is None / missing
    mock_coordinator.data = {"msd": {"storage": {"available": 500000000}}}
    assert sensor.state is None

    # available is None / missing
    mock_coordinator.data = {"msd": {"storage": {"total": 1000000000}}}
    assert sensor.state is None


def test_msd_storage_sensor_images_under_twenty(mock_coordinator):
    """Test MSD storage attributes when image count is less than 20."""
    mock_coordinator.data = {
        "msd": {
            "storage": {
                "total": 1000000000,
                "available": 500000000,
                "images": {
                    "ubuntu.iso": {"size": 1500000000},
                    "arch.iso": {"size": 800000000},
                    "nosize.iso": {"size": None},
                },
            }
        }
    }
    sensor = PiKVMSDStorageSensor(mock_coordinator, "test_id", "Test PiKVM")
    attrs = sensor.extra_state_attributes
    assert attrs["ubuntu.iso"] == 1500000000
    assert attrs["arch.iso"] == 800000000
    assert "nosize.iso" not in attrs
    assert "file count" not in attrs


def test_msd_storage_sensor_images_twenty_or_more(mock_coordinator):
    """Test MSD storage attributes when image count is 20 or more."""
    images_dict = {f"distro_{i}.iso": {"size": 1000000} for i in range(22)}
    mock_coordinator.data = {
        "msd": {
            "storage": {
                "total": 1000000000,
                "available": 500000000,
                "images": images_dict,
            }
        }
    }
    sensor = PiKVMSDStorageSensor(mock_coordinator, "test_id", "Test PiKVM")
    attrs = sensor.extra_state_attributes
    assert attrs["file count"] == 22
    assert "distro_0.iso" not in attrs


# ---------------------------------------------------------------------------
# Coverage for pikvm_throttling_sensor.py (line 29)
# ---------------------------------------------------------------------------

def test_throttling_sensor_extra_state_attributes(mock_coordinator):
    """Test extra_state_attributes and active state of PiKVMThrottlingSensor."""
    throttling_payload = {
        "raw_flags": 0x50005,
        "text_flags": ["throttled", "undervoltage"],
        "voltage": {"core": {"now": True, "past": True}},
    }
    mock_coordinator.data = {
        "hw": {
            "health": {
                "throttling": throttling_payload
            }
        }
    }
    sensor = PiKVMThrottlingSensor(mock_coordinator, "test_id", "Test PiKVM")
    assert sensor.state is True
    assert sensor.extra_state_attributes == throttling_payload

    # Branch where throttling data is missing
    mock_coordinator.data = {"hw": {"health": {}}}
    assert sensor.extra_state_attributes == {}
    assert sensor.state is False


# ---------------------------------------------------------------------------
# Coverage for pikvm_extra_sensor.py (lines 39-42)
# ---------------------------------------------------------------------------

def test_extra_sensor_available(mock_coordinator):
    """Test available property of PiKVMExtraSensor (lines 39-42)."""
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {"extras": {"vnc": {"is_running": True}}}
    sensor = PiKVMExtraSensor(mock_coordinator, "vnc", {}, "test_id", "Test PiKVM")

    # Lines 41-42: True when super().available is True and extra name is in extras
    assert sensor.available is True

    # Lines 41-42: False when extra name is not in extras
    mock_coordinator.data = {"extras": {}}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False

    # Lines 39-40: False when coordinator update failed (super().available is False)
    mock_coordinator.data = {"extras": {"vnc": {"is_running": True}}}
    mock_coordinator.last_update_success = False
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Coverage for pikvm_msd_drive_sensor.py (line 20)
# ---------------------------------------------------------------------------

def test_msd_drive_sensor_available(mock_coordinator):
    """Test available property of PiKVMSDDriveSensor (line 20)."""
    sensor = PiKVMSDDriveSensor(mock_coordinator, "test_id", "Test PiKVM")

    # True when super().available is True and msd drive data exists
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {"msd": {"drive": {"is_mounted": True}}}
    assert sensor.available is True

    # False when drive is None or missing
    mock_coordinator.data = {"msd": {"drive": None}}
    assert sensor.available is False

    mock_coordinator.data = {"msd": {}}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False

    # False when coordinator update failed (super().available is False)
    mock_coordinator.data = {"msd": {"drive": {"is_mounted": True}}}
    mock_coordinator.last_update_success = False
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Coverage for pikvm_msd_enabled_sensor.py (line 29)
# ---------------------------------------------------------------------------

def test_msd_enabled_sensor_available(mock_coordinator):
    """Test available property of PiKVMSDEnabledSensor (line 29)."""
    sensor = PiKVMSDEnabledSensor(mock_coordinator, "test_id", "Test PiKVM")

    # True when super().available is True and msd data exists
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {"msd": {"is_enabled": True}}
    assert sensor.available is True

    # False when msd is None or missing
    mock_coordinator.data = {"msd": None}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False

    # False when coordinator update failed (super().available is False)
    mock_coordinator.data = {"msd": {"is_enabled": True}}
    mock_coordinator.last_update_success = False
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Coverage for pikvm_throttling_sensor.py (lines 26-29)
# ---------------------------------------------------------------------------

def test_throttling_sensor_available(mock_coordinator):
    """Test available property branches of PiKVMThrottlingSensor (lines 26-29)."""
    sensor = PiKVMThrottlingSensor(mock_coordinator, "test_id", "Test PiKVM")

    # Branch 1: super().available is True and "throttling" in hw.health
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {"hw": {"health": {"throttling": {"raw_flags": 0}}}}
    assert sensor.available is True

    # Branch 2: super().available is True, "throttling" not in health, but "health" in hw
    mock_coordinator.data = {"hw": {"health": {}}}
    assert sensor.available is True

    # Branch 3: super().available is True, neither "throttling" nor "health" in hw
    mock_coordinator.data = {"hw": {}}
    assert sensor.available is False

    mock_coordinator.data = {}
    assert sensor.available is False

    # Branch 4: super().available is False (coordinator update failed)
    mock_coordinator.data = {"hw": {"health": {"throttling": {"raw_flags": 0}}}}
    mock_coordinator.last_update_success = False
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Helper functions coverage in sensor.py (lines 47-51, 55-59, 63-67, 82-86, 93-130)
# ---------------------------------------------------------------------------

def test_get_cpu_temp_error_handling():
    """Test _get_cpu_temp valid values, None handling, and ValueError/TypeError handling (lines 47-51)."""
    # Valid float and int values
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": 42.5}}}}) == 42.5
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": 40}}}}) == 40.0
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": "43.2"}}}}) == 43.2

    # None and missing keys
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": None}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {}}}}) is None
    assert _get_cpu_temp({}) is None

    # ValueError branch (line 50-51)
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": "not_a_number"}}}}) is None

    # TypeError branch (line 50-51)
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": ["invalid_type"]}}}}) is None
    assert _get_cpu_temp({"hw": {"health": {"temp": {"cpu": {"nested": "dict"}}}}}) is None


def test_get_cpu_utilization_error_handling():
    """Test _get_cpu_utilization valid values, None, and ValueError/TypeError handling (lines 55-59)."""
    # Valid float and int values
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": 15.5}}}}) == 15.5
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": 20}}}}) == 20.0
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": "25.0"}}}}) == 25.0

    # None and missing keys
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": None}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {}}}}) is None
    assert _get_cpu_utilization({}) is None

    # ValueError branch (line 58-59)
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": "invalid"}}}}) is None

    # TypeError branch (line 58-59)
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": [50.0]}}}}) is None
    assert _get_cpu_utilization({"hw": {"performance": {"cpu": {"utilization": {}}}}}) is None


def test_get_memory_utilization_error_handling():
    """Test _get_memory_utilization valid values, None, and ValueError/TypeError handling (lines 63-67)."""
    # Valid float and int values
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": 60.5}}}}) == 60.5
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": 50}}}}) == 50.0
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": "70.2"}}}}) == 70.2

    # None and missing keys
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": None}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {}}}}) is None
    assert _get_memory_utilization({}) is None

    # ValueError branch (line 66-67)
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": "bad_value"}}}}) is None

    # TypeError branch (line 66-67)
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": ["bad"]}}}}) is None
    assert _get_memory_utilization({"hw": {"performance": {"memory": {"utilization": {}}}}}) is None


def test_get_fan_speed_error_handling():
    """Test _get_fan_speed valid values, None, and ValueError/TypeError handling (lines 82-86)."""
    # Valid int and string-int values
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": 2400}}}}) == 2400
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": "3000"}}}}) == 3000

    # None and missing keys
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": None}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {}}}}) is None
    assert _get_fan_speed({}) is None

    # ValueError branch (line 85-86)
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": "fast"}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": "12.34"}}}}) is None

    # TypeError branch (line 85-86)
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": [2400]}}}}) is None
    assert _get_fan_speed({"hw": {"performance": {"fan": {"speed": {"rpm": 2400}}}}}) is None


def test_sensor_helper_memory_and_fan_attributes():
    """Test _get_memory_attributes and _get_fan_attributes branches (lines 70-78, 89-91)."""
    # Memory attributes: both present
    data_full = {
        "hw": {
            "performance": {
                "memory": {
                    "available": 1048576,  # 1 MB
                    "total": 2097152,      # 2 MB
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

    # Memory attributes: missing keys
    assert _get_memory_attributes({}) == {}
    assert _get_memory_attributes({"hw": {"performance": {"memory": {}}}}) == {}

    # Fan attributes: missing or empty
    assert _get_fan_attributes({}) == {}
    assert _get_fan_attributes({"hw": {"performance": {"fan": None}}}) == {}


def test_sensor_helper_msd_storage_and_attributes():
    """Test _get_msd_storage and _get_msd_storage_attributes coverage (lines 93-130)."""
    # Invalid / missing storage
    assert _get_msd_storage({}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 0, "available": 0}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": -100, "available": 10}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": None, "available": 10}}}) is None
    assert _get_msd_storage({"msd": {"storage": {"total": 100, "available": None}}}) is None

    # Valid storage
    data_valid = {
        "msd": {
            "storage": {
                "total": 1048576000,
                "available": 524288000,
                "images": {
                    "boot.iso": {"size": 209715200},
                    "empty.iso": {"size": None},
                },
            }
        }
    }
    assert _get_msd_storage(data_valid) == 50.0

    attrs = _get_msd_storage_attributes(data_valid)
    assert attrs["percent_used"] == 50.0
    assert attrs["boot.iso"] == 209715200
    assert "empty.iso" not in attrs

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
    """Test available_fn closures across all SENSOR_DESCRIPTIONS (lines 144, 157, 171, 184, 198)."""
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
    # True branches
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn(valid_data) is True
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn(valid_data) is True
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn(valid_data) is True
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn(valid_data) is True
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn(valid_data) is True

    # False branches
    empty_data = {}
    assert CPU_TEMP_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert CPU_UTILIZATION_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert MEMORY_UTILIZATION_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert FAN_SPEED_SENSOR_DESCRIPTION.available_fn(empty_data) is False
    assert MSD_STORAGE_SENSOR_DESCRIPTION.available_fn(empty_data) is False



