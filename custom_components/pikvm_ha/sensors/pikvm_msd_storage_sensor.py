"""Support for PiKVM MSD storage sensor."""

import logging

from ..sensor import PiKVMBaseSensor

_LOGGER = logging.getLogger(__name__)


class PiKVMSDStorageSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD storage sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} MSD Storage"
        super().__init__(
            coordinator,
            unique_id_base,
            "msd_storage",
            name,
            "%",
            "mdi:database",
        )

    @property
    def state(self):
        data = self.coordinator.data.get("msd", {}).get("storage", {})
        total = data.get("size")
        free = data.get("free")
        if total is None or free is None or total <= 0:
            _LOGGER.warning("MSD storage key missing or invalid: %r", data)
            return None  # marks sensor unavailable
        return round((free / total) * 100, 2)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        storage_data = self.coordinator.data["msd"]["storage"]
        images = self.coordinator.data["msd"]["storage"]["images"]
        if storage_data:
            if "size" in storage_data:
                attributes["total_size_mb"] = round(storage_data["size"] / (1024 * 1024), 2)
            if "free" in storage_data:
                attributes["free_size_mb"] = round(storage_data["free"] / (1024 * 1024), 2)
            if "free" in storage_data and "size" in storage_data:
                attributes["used_size_mb"] = round(
                    (storage_data["size"] - storage_data["free"]) / (1024 * 1024), 2
                )
            state = self.state
            if state is not None:
                attributes["percent_free"] = self.state
        if images and len(images.items()) < 20:
            for image, details in images.items():
                attributes[image] = details["size"]
        elif images:
            attributes["file count"] = len(images.items())
        return attributes
