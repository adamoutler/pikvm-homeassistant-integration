"""Tests for the PiKVM base entity class."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.pikvm.const import DOMAIN
from custom_components.pikvm.entity import PiKVMEntity


def test_pikvm_entity_initialization() -> None:
    """Test PiKVMEntity properties and initialization."""
    coordinator = MagicMock()
    dev_info = DeviceInfo(identifiers={(DOMAIN, "test_serial")}, name="Test Device")
    coordinator.device_info = dev_info
    coordinator.data = {"test": "data"}
    coordinator.last_update_success = True

    entity = PiKVMEntity(coordinator, "test_unique_id_base")

    assert entity.has_entity_name is True
    assert entity.coordinator is coordinator
    assert entity.device_info == dev_info
    assert entity._attr_unique_id_base == "test_unique_id_base"
    assert entity.available is True


def test_pikvm_entity_available_when_coordinator_data_none() -> None:
    """Test PiKVMEntity is unavailable when coordinator.data is None."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = None

    entity = PiKVMEntity(coordinator, "test_unique_id_base")
    assert entity.available is False


def test_pikvm_entity_available_when_update_failed() -> None:
    """Test PiKVMEntity is unavailable when coordinator.last_update_success is False."""
    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.data = {"test": "data"}

    entity = PiKVMEntity(coordinator, "test_unique_id_base")
    assert entity.available is False
