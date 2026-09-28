"""Tests for PiKVM sensor platform setup and base sensor classes."""

from unittest.mock import MagicMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.pikvm_ha.sensor import (
    PiKVMBaseSensor,
    async_setup_entry,
    lazy_import_sensors,
)


@pytest.fixture
def mock_coordinator():
    """Create a coordinator with comprehensive device data."""
    coordinator = MagicMock()
    coordinator.url = "https://pikvm.local"
    coordinator.data = {
        "hw": {
            "platform": {"serial": "pikvm_serial_99"},
            "health": {"temp": {"cpu": 42.0}, "throttling": {"raw_flags": 0}},
            "performance": {
                "cpu": {"utilization": 20.0},
                "memory": {
                    "utilization": 40.0,
                    "available": 500000000,
                    "total": 1000000000,
                },
                "fan": {"speed": 1500},
            },
        },
        "msd": {
            "is_enabled": True,
            "drive": {"is_mounted": True},
            "storage": {"available": 500000000, "total": 1000000000},
        },
        "meta": {"server": {"host": "pikvm.local"}},
        "extras": {},
    }
    return coordinator


def test_base_sensor_attributes(mock_coordinator):
    """Test PiKVMBaseSensor attributes and properties."""
    sensor = PiKVMBaseSensor(
        mock_coordinator,
        "base_uid",
        "cpu_temp",
        "CPU Temp",
        unit="°C",
        icon="mdi:thermometer",
    )
    assert sensor.unique_id == "base_uid_cpu_temp"
    assert sensor.name == "CPU Temp"
    assert sensor.unit_of_measurement == "°C"
    assert sensor.icon == "mdi:thermometer"
    assert sensor.extra_state_attributes == {"ip": "https://pikvm.local"}
    assert sensor.has_entity_name is True


def test_base_sensor_state_not_implemented(mock_coordinator):
    """Test that PiKVMBaseSensor.state raises NotImplementedError."""
    sensor = PiKVMBaseSensor(
        mock_coordinator,
        "base_uid",
        "cpu_temp",
        "CPU Temp",
    )
    with pytest.raises(NotImplementedError) as exc_info:
        _ = sensor.state
    assert "The state method must be implemented by the subclass" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_standard_sensors(hass, mock_coordinator):
    """Test async_setup_entry registers all 8 standard sensors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_id",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "pikvm_serial_99",
            CONF_CERTIFICATE: "test_cert",
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    assert mock_add_entities.call_count == 1
    entities, update_before_add = mock_add_entities.call_args[0]
    assert update_before_add is True
    assert len(entities) == 8

    entity_types = [type(e).__name__ for e in entities]
    assert "PiKVMCpuUtilizationSensor" in entity_types
    assert "PiKVMMemoryUtilizationSensor" in entity_types
    assert "PiKVMCpuTempSensor" in entity_types
    assert "PiKVMFanSpeedSensor" in entity_types
    assert "PiKVMThrottlingSensor" in entity_types
    assert "PiKVMSDEnabledSensor" in entity_types
    assert "PiKVMSDDriveSensor" in entity_types
    assert "PiKVMSDStorageSensor" in entity_types


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_with_extras(hass, mock_coordinator):
    """Test async_setup_entry dynamically adds extras sensors."""
    mock_coordinator.data["extras"] = {
        "vnc": {"is_running": True},
        "ipmi": {"is_running": False},
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_id_extras",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "pikvm_serial_99",
            CONF_CERTIFICATE: "test_cert",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    entities, _ = mock_add_entities.call_args[0]
    assert len(entities) == 10  # 8 standard + 2 extras


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host_name,expected_prefix",
    [
        ("localhost.localdomain", "pikvm"),
        ("my.custom.pikvm", "my_custom_pikvm"),
    ],
)
async def test_sensor_device_name_formatting(
    hass, mock_coordinator, host_name, expected_prefix
):
    """Test device name formatting with localhost and custom host names."""
    mock_coordinator.data["meta"] = {"server": {"host": host_name}}

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=f"entry_{expected_prefix}",
        data={
            CONF_HOST: f"https://{host_name}",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "pikvm_serial_99",
            CONF_CERTIFICATE: "test_cert",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    entities, _ = mock_add_entities.call_args[0]
    assert len(entities) == 8


def test_lazy_import_sensors():
    """Test lazy_import_sensors returns dictionary of valid sensor classes."""
    classes = lazy_import_sensors()
    assert isinstance(classes, dict)
    expected_keys = {
        "cpu_temp",
        "cpu_utilization",
        "extra",
        "fan_speed",
        "memory_utilization",
        "msd_drive",
        "msd_enabled",
        "msd_storage",
        "throttling",
    }
    assert set(classes.keys()) == expected_keys
    for key, cls in classes.items():
        assert issubclass(cls, PiKVMBaseSensor)
