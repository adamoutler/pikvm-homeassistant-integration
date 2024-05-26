"""PiKVM MSD Drive Sensor."""
from ..sensor import PiKVMBaseSensor

class PiKVMSDDriveSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD drive sensor."""

    def __init__(self, coordinator, device_info, unique_id_base):
        """Initialize the sensor."""
        super().__init__(coordinator, device_info, unique_id_base, "msd_drive", "PiKVM MSD Drive", icon="mdi:usb")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["msd"]["drive"]["connected"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        drive_data = self.coordinator.data["msd"]["drive"]
        if drive_data:
            attributes.update(drive_data)
        return attributes
