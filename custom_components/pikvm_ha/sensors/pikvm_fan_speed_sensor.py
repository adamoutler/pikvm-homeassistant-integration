"""Support for PiKVM fan speed sensor."""

from homeassistant.const import REVOLUTIONS_PER_MINUTE
from ..sensor import PiKVMBaseSensor
from ..utils import get_nested_value


class PiKVMFanSpeedSensor(PiKVMBaseSensor):
    """Representation of a PiKVM fan speed sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} Fan Speed"
        super().__init__(coordinator, unique_id_base, "fan_speed", name, icon="mdi:fan")

        # Set the unit of measurement based on hall availability
        self._attr_unit_of_measurement = REVOLUTIONS_PER_MINUTE

    @property
    def available(self):
        """Return True if the sensor data is available."""
        return "fan" in get_nested_value(self.coordinator.data, ["hw", "performance"], {})

    @property
    def state(self):
        """Return the state of the sensor."""
        return get_nested_value(self.coordinator.data, ["hw", "performance", "fan", "speed"])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        fan_state = get_nested_value(self.coordinator.data, ["hw", "performance", "fan"], {})
        if fan_state:
            attributes.update(fan_state)
        return attributes
