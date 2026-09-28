"""Tests for the sensor platform in the PiKVM integration."""

from unittest.mock import MagicMock
import pytest

from homeassistant.const import UnitOfTemperature, PERCENTAGE, REVOLUTIONS_PER_MINUTE

from custom_components.pikvm_ha.sensors.pikvm_cpu_temp_sensor import PiKVMCpuTempSensor
from custom_components.pikvm_ha.sensors.pikvm_cpu_utilization_sensor import PiKVMCpuUtilizationSensor
from custom_components.pikvm_ha.sensors.pikvm_memory_utilization_sensor import PiKVMMemoryUtilizationSensor
from custom_components.pikvm_ha.sensors.pikvm_fan_speed_sensor import PiKVMFanSpeedSensor
from custom_components.pikvm_ha.sensors.pikvm_throttling_sensor import PiKVMThrottlingSensor
from custom_components.pikvm_ha.sensors.pikvm_msd_enabled_sensor import PiKVMSDEnabledSensor
from custom_components.pikvm_ha.sensors.pikvm_msd_drive_sensor import PiKVMSDDriveSensor
from custom_components.pikvm_ha.sensors.pikvm_msd_storage_sensor import PiKVMSDStorageSensor
from custom_components.pikvm_ha.sensors.pikvm_extra_sensor import PiKVMExtraSensor


@pytest.fixture
def mock_coordinator():
    """Fixture for a mock coordinator."""
    coordinator = MagicMock()
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

