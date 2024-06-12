from ..sensor import PiKVMBaseSensor

class PiKVMCpuTempSensor(PiKVMBaseSensor):
    """Representation of a PiKVM CPU temperature sensor."""

    def __init__(self, coordinator, device_info, unique_id_base, device_name):
        """Initialize the sensor."""
        name = f"{device_name} CPU Temp"
        super().__init__(coordinator, device_info, unique_id_base, "cpu_temp", name, "°C", "mdi:thermometer")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["hw"]["health"]["temp"]["cpu"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        return attributes
