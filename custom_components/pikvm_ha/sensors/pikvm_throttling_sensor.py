"""Support for PiKVM throttling sensor."""

from ..sensor import PiKVMBaseSensor
from ..utils import get_nested_value


class PiKVMThrottlingSensor(PiKVMBaseSensor):
    """Representation of a PiKVM throttling sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} Throttling"
        super().__init__(
            coordinator,
            unique_id_base,
            "throttling",
            name,
            icon="mdi:alert",
        )

    @property
    def state(self):
        """Return the state of the sensor."""
        return get_nested_value(self.coordinator.data, ["hw", "health", "throttling", "raw_flags"], 0) > 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return get_nested_value(self.coordinator.data, ["hw", "health", "throttling"], {})
