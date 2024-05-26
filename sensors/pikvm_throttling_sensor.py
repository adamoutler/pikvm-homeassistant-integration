"""PiKVM Throttling Sensor."""
from ..sensor import PiKVMBaseSensor

class PiKVMThrottlingSensor(PiKVMBaseSensor):
    """Representation of a PiKVM throttling sensor."""

    def __init__(self, coordinator, device_info, unique_id_base):
        """Initialize the sensor."""
        super().__init__(coordinator, device_info, unique_id_base, "throttling", "PiKVM Throttling", icon="mdi:alert")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["hw"]["health"].get("throttling", {}).get("raw_flags", 0)
