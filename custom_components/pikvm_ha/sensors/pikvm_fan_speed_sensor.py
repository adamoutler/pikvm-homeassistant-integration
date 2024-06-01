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
        fan_data = self.coordinator.data.get("fan")
        
        # Check if fan_data is not None and if the state key exists
        if fan_data and fan_data.get("state"):
            return fan_data["state"]["fan"]["speed"]
        
        # Return a default value or None if fan data is not available
        return None
