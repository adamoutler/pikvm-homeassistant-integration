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

    
    @property
    def extra_state_attributes(self):    
        throttling_data = self.coordinator.data["hw"]["health"].get("throttling", {})
        flattened_data = {}
        for key, value in throttling_data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, dict):
                        for sub_sub_key, sub_sub_value in sub_value.items():
                            flattened_data[f"{sub_key}.{sub_sub_key}"] = sub_sub_value
                    else:
                        flattened_data[f"{key}.{sub_key}"] = sub_value
            else:
                flattened_data[key] = value
        return flattened_data
