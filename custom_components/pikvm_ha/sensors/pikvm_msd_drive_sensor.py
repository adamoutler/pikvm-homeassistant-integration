"""Support for PiKVM MSD drive sensor."""

from ..sensor import PiKVMBaseSensor


class PiKVMSDDriveSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD drive sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} MSD Drive"
        super().__init__(coordinator, unique_id_base, "msd_drive", name, icon="mdi:usb")

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
