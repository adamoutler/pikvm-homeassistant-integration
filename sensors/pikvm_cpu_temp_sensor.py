"""PiKVM CPU Temperature Sensor."""
from .sensor import PiKVMBaseSensor

class PiKVMCpuTempSensor(PiKVMBaseSensor):
    """Representation of a PiKVM CPU temperature sensor."""

    def __init__(self, coordinator, device_info, serial_number):
        """Initialize the sensor."""
        super().__init__(coordinator, device_info, serial_number, "cpu_temp", "PiKVM CPU Temperature", "°C")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["hw"]["health"]["temp"]["cpu"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        attributes["throttling"] = self.coordinator.data["hw"]["health"].get("throttling", {})
        return attributes
