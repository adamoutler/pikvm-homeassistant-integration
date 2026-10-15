"""Support for PiKVM fan speed sensor."""

from __future__ import annotations

from homeassistant.const import REVOLUTIONS_PER_MINUTE

from ..sensor import FAN_SPEED_SENSOR_DESCRIPTION, PiKVMBaseSensor
from ..utils import get_nested_value


class PiKVMFanSpeedSensor(PiKVMBaseSensor):
    """Representation of a PiKVM fan speed sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} Fan Speed"
        super().__init__(
            coordinator,
            unique_id_base,
            "fan_speed",
            name,
            icon="mdi:fan",
            unit=REVOLUTIONS_PER_MINUTE,
            description=FAN_SPEED_SENSOR_DESCRIPTION,
        )

        self._attr_unit_of_measurement = REVOLUTIONS_PER_MINUTE

    @property
    def available(self) -> bool:
        """Return True if the sensor data is available."""
        return super().available and "fan" in get_nested_value(
            self.coordinator.data, ["hw", "performance"], {}
        )

    @property
    def native_value(self):
        """Return the native state of the sensor."""
        return get_nested_value(self.coordinator.data, ["hw", "performance", "fan", "speed"])

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        fan_state = get_nested_value(self.coordinator.data, ["hw", "performance", "fan"], {})
        if fan_state:
            attributes.update(fan_state)
        return attributes
