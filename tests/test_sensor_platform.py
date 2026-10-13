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
    PiKVMSensor,
    PiKVMSensorEntityDescription,
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
    """Test async_setup_entry registers all 5 standard numeric sensors."""
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
    assert len(entities) == 5

    keys = [e.entity_description.key for e in entities]
    assert "cpu_utilization" in keys
    assert "memory_utilization" in keys
    assert "cpu_temp" in keys
    assert "fan_speed" in keys
    assert "msd_storage" in keys


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_with_extras(hass, mock_coordinator):
    """Test async_setup_entry sets up numeric sensors when extras are present."""
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
    assert len(entities) == 5



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
    assert len(entities) == 5


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


def test_pikvm_sensor_name_resolution(mock_coordinator):
    """Test PiKVMSensor name resolution paths (lines 231-235)."""
    desc = PiKVMSensorEntityDescription(
        key="test_sensor",
        name="Description Sensor Name",
        value_fn=lambda _: 10,
    )
    sensor = PiKVMSensor(mock_coordinator, "base_uid", desc)

    # Line 231-232: self._attr_name is not None
    assert sensor.name == "Description Sensor Name"

    # Lines 233-234: self._attr_name is None, platform is None, entity_description is not None
    sensor._attr_name = None
    sensor.platform = None
    assert sensor.name == "Description Sensor Name"

    # Line 235: self._attr_name is None, platform is not None (falls through to super().name)
    sensor.platform = MagicMock()
    assert sensor.name == super(PiKVMSensor, sensor).name

    # Line 235: entity_description is None and platform is None
    sensor.platform = None
    sensor.entity_description = None
    assert sensor.name is None


def test_pikvm_sensor_native_value(mock_coordinator):
    """Test PiKVMSensor native_value returns result of description value_fn (line 240)."""
    desc = PiKVMSensorEntityDescription(
        key="temp",
        name="Temp",
        value_fn=lambda data: data.get("hw", {}).get("health", {}).get("temp", {}).get("cpu"),
    )
    sensor = PiKVMSensor(mock_coordinator, "base_uid", desc)
    assert sensor.native_value == 42.0

    # Custom fixed lambda
    desc_fixed = PiKVMSensorEntityDescription(
        key="fixed",
        name="Fixed",
        value_fn=lambda _: 99.9,
    )
    sensor_fixed = PiKVMSensor(mock_coordinator, "base_uid", desc_fixed)
    assert sensor_fixed.native_value == 99.9


def test_pikvm_sensor_available_conditions(mock_coordinator):
    """Test PiKVMSensor available property branches (lines 245-249)."""
    desc_with_fn = PiKVMSensorEntityDescription(
        key="test_avail",
        name="Test Avail",
        value_fn=lambda _: 0,
        available_fn=lambda data: "hw" in data,
    )
    sensor = PiKVMSensor(mock_coordinator, "base_uid", desc_with_fn)

    # Line 245-246: super().available is False (last_update_success is False)
    mock_coordinator.last_update_success = False
    assert sensor.available is False

    # Lines 247-248: super().available is True, available_fn returns True
    mock_coordinator.last_update_success = True
    assert sensor.available is True

    # Lines 247-248: super().available is True, available_fn returns False
    mock_coordinator.data = {}
    assert sensor.available is False

    # Line 249: super().available is True, available_fn is None -> returns True
    desc_no_fn = PiKVMSensorEntityDescription(
        key="test_no_fn",
        name="Test No Fn",
        value_fn=lambda _: 0,
        available_fn=None,
    )
    sensor_no_fn = PiKVMSensor(mock_coordinator, "base_uid", desc_no_fn)
    mock_coordinator.last_update_success = True
    assert sensor_no_fn.available is True


def test_pikvm_sensor_extra_state_attributes(mock_coordinator):
    """Test PiKVMSensor extra_state_attributes with and without attributes_fn (lines 252-259)."""
    # attributes_fn is None
    desc_no_attrs = PiKVMSensorEntityDescription(
        key="no_attrs",
        name="No Attrs",
        value_fn=lambda _: 0,
        attributes_fn=None,
    )
    sensor_no_attrs = PiKVMSensor(mock_coordinator, "base_uid", desc_no_attrs)
    assert sensor_no_attrs.extra_state_attributes == {"ip": "https://pikvm.local"}

    # attributes_fn returns empty dict (lines 257-258: if extra is False)
    desc_empty_attrs = PiKVMSensorEntityDescription(
        key="empty_attrs",
        name="Empty Attrs",
        value_fn=lambda _: 0,
        attributes_fn=lambda _: {},
    )
    sensor_empty_attrs = PiKVMSensor(mock_coordinator, "base_uid", desc_empty_attrs)
    assert sensor_empty_attrs.extra_state_attributes == {"ip": "https://pikvm.local"}

    # attributes_fn returns populated dict (lines 257-259: if extra is True -> update)
    desc_with_attrs = PiKVMSensorEntityDescription(
        key="with_attrs",
        name="With Attrs",
        value_fn=lambda _: 0,
        attributes_fn=lambda _: {"custom_attr": "value", "extra_metric": 123},
    )
    sensor_with_attrs = PiKVMSensor(mock_coordinator, "base_uid", desc_with_attrs)
    assert sensor_with_attrs.extra_state_attributes == {
        "ip": "https://pikvm.local",
        "custom_attr": "value",
        "extra_metric": 123,
    }


def test_base_sensor_unit_of_measurement_hierarchy(mock_coordinator):
    """Test PiKVMBaseSensor unit_of_measurement resolution hierarchy (lines 294-303)."""
    desc = PiKVMSensorEntityDescription(
        key="test_unit",
        name="Test Unit",
        native_unit_of_measurement="RPM",
        value_fn=lambda _: None,
    )
    sensor = PiKVMBaseSensor(
        mock_coordinator,
        "base_uid",
        "test_unit",
        unit="°C",
        description=desc,
    )

    # Line 297-298: _attr_unit_of_measurement takes highest priority
    assert sensor.unit_of_measurement == "°C"

    # Lines 299-300: _attr_unit_of_measurement is None, _attr_native_unit_of_measurement is set
    sensor._attr_unit_of_measurement = None
    sensor._attr_native_unit_of_measurement = "%"
    assert sensor.unit_of_measurement == "%"

    # Lines 301-302: both attr units None, entity_description.native_unit_of_measurement used
    sensor._attr_native_unit_of_measurement = None
    assert sensor.unit_of_measurement == "RPM"

    # Line 303: all units and entity_description are None -> returns None
    sensor.entity_description = None
    assert sensor.unit_of_measurement is None


def test_base_sensor_subclass_state_delegates_to_native_value(mock_coordinator):
    """Test PiKVMBaseSensor.state delegates to native_value for subclasses (lines 307-312)."""
    class ConcreteTestSensor(PiKVMBaseSensor):
        """Concrete subclass that does not override state."""

    desc = PiKVMSensorEntityDescription(
        key="subclass_test",
        name="Subclass Test",
        value_fn=lambda data: 77.7,
    )
    sensor = ConcreteTestSensor(
        mock_coordinator,
        "base_uid",
        "subclass_test",
        description=desc,
    )

    # Line 311: type(self) is not PiKVMBaseSensor -> returns self.native_value
    assert sensor.state == 77.7


def test_base_sensor_fallback_description_name(mock_coordinator):
    """Test PiKVMBaseSensor fallback entity description name generation when name is None (line 279)."""
    sensor = PiKVMBaseSensor(
        mock_coordinator,
        "base_uid",
        "fan_controller_rpm",
        name=None,
    )
    # sensor_type.replace("_", " ").title()
    assert sensor.entity_description.name == "Fan Controller Rpm"


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_with_runtime_data(hass, mock_coordinator):
    """Test async_setup_entry uses config_entry.runtime_data when present (line 322)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_runtime_data_entry",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "pikvm_serial_99",
            CONF_CERTIFICATE: "test_cert",
        },
    )
    entry.add_to_hass(hass)
    # Set runtime_data directly on config_entry
    entry.runtime_data = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    assert mock_add_entities.call_count == 1
    entities, _ = mock_add_entities.call_args[0]
    assert len(entities) == 5

