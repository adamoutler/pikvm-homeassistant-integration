"""PiKVM MSD Enabled Sensor."""
from ..sensor import PiKVMBaseSensor

class PiKVMSDEnabledSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD enabled sensor."""

    def __init__(self, coordinator, device_info, unique_id_base):
        """Initialize the sensor."""
        super().__init__(coordinator, device_info, unique_id_base, "msd_enabled", "PiKVM MSD Enabled", icon="mdi:check-circle")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["msd"]["enabled"]
