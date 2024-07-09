from ..sensor import PiKVMBaseSensor

class PiKVMFanSpeedSensor(PiKVMBaseSensor):
    """Representation of a PiKVM fan speed sensor."""

    def __init__(self, coordinator, device_info, unique_id_base, device_name):
        """Initialize the sensor."""
        name = f"{device_name} Fan Speed"
        super().__init__(coordinator, device_info, unique_id_base, "fan_speed", name, icon="mdi:fan")

        # Ensure fan_data is not None
        self.hall_available = False
        if coordinator.data and coordinator.data.get("fan"):
            fan_data = coordinator.data.get("fan", {}).get("state", {})
            if fan_data:
                hall_data = fan_data.get("hall", {})
                if hall_data:
                    self.hall_available = hall_data.get("available", False)

        # Set the unit of measurement based on hall availability
        self._attr_unit_of_measurement = "RPM" if self.hall_available else "%"
    
    @property
    def available(self):
        """Return True if the sensor data is available."""
        return "state" in self.coordinator.data["fan"]
    
    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.get("fan") or not self.coordinator.data.get("fan", {}).get("state"):
            return None

        if self.hall_available:
            hall_data = self.coordinator.data.get("fan", {}).get("state", {}).get("hall", {})
            return hall_data.get("rpm", None) if hall_data else None
        else:
            fan_data = self.coordinator.data.get("fan", {}).get("state", {}).get("fan", {})
            return fan_data.get("speed", None) if fan_data else None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        if self.coordinator.data and self.coordinator.data.get("fan") and self.coordinator.data.get("fan", {}).get("state"):
            fan_data = self.coordinator.data.get("fan", {}).get("state", {})
            if fan_data:
                attributes.update(fan_data)
        return attributes
