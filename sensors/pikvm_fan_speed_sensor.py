"""PiKVM Fan Speed Sensor."""
from ..sensor import PiKVMBaseSensor

class PiKVMFanSpeedSensor(PiKVMBaseSensor):
    """Representation of a PiKVM fan speed sensor."""

    def __init__(self, coordinator, device_info, unique_id_base):
        """Initialize the sensor."""
        super().__init__(coordinator, device_info, unique_id_base, "fan_speed", "PiKVM Fan Speed", "%", "mdi:fan")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["fan"]["state"]["fan"]["speed"]
