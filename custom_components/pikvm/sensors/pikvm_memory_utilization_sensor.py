"""Represents a sensor for monitoring memory utilization on a PiKVM device."""

from __future__ import annotations

import logging
from typing import NamedTuple

from homeassistant.const import PERCENTAGE

from ..coordinator import PiKVMDataUpdateCoordinator
from ..sensor import MEMORY_UTILIZATION_SENSOR_DESCRIPTION, PiKVMBaseSensor
from ..utils import bytes_to_mb, get_nested_value

_LOGGER = logging.getLogger(__name__)


class PiKVMResponse(NamedTuple):
    """Represents a PiKVM response."""

    success: bool
    model: str
    serial: str
    name: str
    error: str


class PiKVMMemoryUtilizationSensor(PiKVMBaseSensor):
    """Representation of a PiKVM memory utilization sensor."""

    def __init__(
        self,
        coordinator: PiKVMDataUpdateCoordinator,
        unique_id_base,
        device_name,
    ) -> None:
        """Initialize the sensor."""
        name = f"{device_name} Memory Utilization"
        super().__init__(
            coordinator,
            unique_id_base,
            "memory_utilization",
            name,
            PERCENTAGE,
            "mdi:memory",
            description=MEMORY_UTILIZATION_SENSOR_DESCRIPTION,
        )

    @property
    def native_value(self):
        """Return the state of the sensor in preferred units."""
        return get_nested_value(
            self.coordinator.data, ["hw", "performance", "memory", "utilization"]
        )

    @property
    def state(self):
        """Return the state of the sensor in preferred units."""
        return self.native_value

    @property
    def available(self) -> bool:
        """Return True if the sensor data is available."""
        return super().available and "performance" in get_nested_value(
            self.coordinator.data, ["hw"], {}
        )

    @property
    def unit_of_measurement(self):
        """Return the preferred units of measure."""
        return PERCENTAGE

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        available_bytes = get_nested_value(
            self.coordinator.data, ["hw", "performance", "memory", "available"]
        )
        total_bytes = get_nested_value(
            self.coordinator.data, ["hw", "performance", "memory", "total"]
        )
        if available_bytes is not None:
            attributes["available MB"] = bytes_to_mb(available_bytes)
        if total_bytes is not None:
            attributes["total MB"] = bytes_to_mb(total_bytes)
        return attributes
