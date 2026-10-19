"""Tests for PiKVM sensor platform setup and sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.pikvm.sensor import (
    PiKVMSensor,
    PiKVMSensorEntityDescription,
    async_setup_entry,
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

    ent_reg = er.async_get(hass)
    stale_ent = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_unknown_cpu_temp",
        config_entry=entry,
    )
    valid_ent = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_pikvm_serial_99_cpu_temp",
        config_entry=entry,
    )
    non_sensor_ent = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_other_binary",
        config_entry=entry,
    )
    assert ent_reg.async_get(stale_ent.entity_id) is not None
    assert ent_reg.async_get(valid_ent.entity_id) is not None
    assert ent_reg.async_get(non_sensor_ent.entity_id) is not None

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    assert ent_reg.async_get(stale_ent.entity_id) is None
    assert ent_reg.async_get(valid_ent.entity_id) is not None
    assert ent_reg.async_get(non_sensor_ent.entity_id) is not None

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
async def test_sensor_async_setup_entry_unknown_serial_does_not_purge_entities(
    hass, mock_coordinator
):
    """Test async_setup_entry does not purge registered entities when serial is unknown."""
    # Coordinator has no serial
    mock_coordinator.data["hw"]["platform"]["serial"] = None

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_unknown_entry",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
        },
    )
    entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    existing_user_ent = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_custom_serial_cpu_temp",
        config_entry=entry,
    )
    assert ent_reg.async_get(existing_user_ent.entity_id) is not None

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    mock_add_entities = MagicMock()
    await async_setup_entry(hass, entry, mock_add_entities)

    # The existing entity MUST NOT be removed because unique_id_base ends with "_unknown"
    assert ent_reg.async_get(existing_user_ent.entity_id) is not None
    assert mock_add_entities.call_count == 1


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
    ("host_name", "expected_prefix"),
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


def test_pikvm_sensor_name_resolution(mock_coordinator):
    """Test PiKVMSensor translation_key and has_entity_name properties."""
    desc = PiKVMSensorEntityDescription(
        key="test_sensor",
        translation_key="test_sensor",
        value_fn=lambda _: 10,
    )
    sensor = PiKVMSensor(mock_coordinator, "base_uid", desc)
    assert sensor.unique_id == "base_uid_test_sensor"
    assert sensor.translation_key == "test_sensor"
    assert sensor.has_entity_name is True


def test_pikvm_sensor_native_value(mock_coordinator):
    """Test PiKVMSensor native_value returns result of description value_fn."""
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
    """Test PiKVMSensor available property branches."""
    desc_with_fn = PiKVMSensorEntityDescription(
        key="test_avail",
        name="Test Avail",
        value_fn=lambda _: 0,
        available_fn=lambda data: "hw" in data,
    )
    sensor = PiKVMSensor(mock_coordinator, "base_uid", desc_with_fn)

    # super().available is False (last_update_success is False)
    mock_coordinator.last_update_success = False
    assert sensor.available is False

    # super().available is True, available_fn returns True
    mock_coordinator.last_update_success = True
    assert sensor.available is True

    # super().available is True, available_fn returns False
    mock_coordinator.data = {}
    assert sensor.available is False

    # super().available is True, available_fn is None -> returns True
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
    """Test PiKVMSensor extra_state_attributes with and without attributes_fn."""
    # attributes_fn is None
    desc_no_attrs = PiKVMSensorEntityDescription(
        key="no_attrs",
        name="No Attrs",
        value_fn=lambda _: 0,
        attributes_fn=None,
    )
    sensor_no_attrs = PiKVMSensor(mock_coordinator, "base_uid", desc_no_attrs)
    assert sensor_no_attrs.extra_state_attributes == {"ip": "https://pikvm.local"}

    # attributes_fn returns empty dict (if extra is False)
    desc_empty_attrs = PiKVMSensorEntityDescription(
        key="empty_attrs",
        name="Empty Attrs",
        value_fn=lambda _: 0,
        attributes_fn=lambda _: {},
    )
    sensor_empty_attrs = PiKVMSensor(mock_coordinator, "base_uid", desc_empty_attrs)
    assert sensor_empty_attrs.extra_state_attributes == {"ip": "https://pikvm.local"}

    # attributes_fn returns populated dict (if extra is True -> update)
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


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_with_runtime_data(hass, mock_coordinator):
    """Test async_setup_entry uses config_entry.runtime_data when present."""
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
