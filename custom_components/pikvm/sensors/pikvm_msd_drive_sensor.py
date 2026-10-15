"""Support for PiKVM MSD drive sensor."""

from __future__ import annotations

from ..sensor import PiKVMBaseSensor
from ..utils import get_nested_value


class PiKVMSDDriveSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD drive sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} MSD Drive"
        super().__init__(coordinator, unique_id_base, "msd_drive", name, icon="mdi:usb")

    @property
    def available(self) -> bool:
        """Return True if the sensor data is available."""
        return super().available and get_nested_value(self.coordinator.data, ["msd", "drive"]) is not None

    @property
    def native_value(self) -> str:
        """Return the native state of the sensor."""
        is_mounted = get_nested_value(self.coordinator.data, ["msd", "drive", "is_mounted"], False)
        return "on" if is_mounted else "off"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        drive_data = get_nested_value(self.coordinator.data, ["msd", "drive"], {})
        if drive_data:
            attributes.update(drive_data)
        return attributes
