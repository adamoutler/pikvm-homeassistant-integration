"""Module for the PiKVMCpuUtilizationSensor class.

Represents a sensor for monitoring the CPU utilization of a PiKVM device.
"""

from __future__ import annotations

import logging

from homeassistant.const import PERCENTAGE

from ..coordinator import PiKVMDataUpdateCoordinator
from ..sensor import CPU_UTILIZATION_SENSOR_DESCRIPTION, PiKVMBaseSensor
from ..utils import get_nested_value

_LOGGER = logging.getLogger(__name__)


class PiKVMCpuUtilizationSensor(PiKVMBaseSensor):
    """Representation of a PiKVM CPU utilization sensor."""

    def __init__(
        self,
        coordinator: PiKVMDataUpdateCoordinator,
        unique_id_base,
        device_name,
    ) -> None:
        """Initialize the sensor."""
        name = f"{device_name} CPU Utilization"
        super().__init__(
            coordinator,
            unique_id_base,
            "cpu_utilization",
            name,
            PERCENTAGE,
            "mdi:cpu-64-bit",
            description=CPU_UTILIZATION_SENSOR_DESCRIPTION,
        )

    @property
    def native_value(self):
        """Return the state of the sensor in preferred units."""
        return get_nested_value(
            self.coordinator.data, ["hw", "performance", "cpu", "utilization"]
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
        return super().extra_state_attributes
