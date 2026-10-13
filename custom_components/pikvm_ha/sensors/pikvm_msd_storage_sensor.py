"""Support for PiKVM MSD storage sensor."""

from __future__ import annotations

import logging

from homeassistant.const import PERCENTAGE

from ..sensor import MSD_STORAGE_SENSOR_DESCRIPTION, PiKVMBaseSensor
from ..utils import bytes_to_mb, get_nested_value

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
            PERCENTAGE,
            "mdi:database",
            description=MSD_STORAGE_SENSOR_DESCRIPTION,
        )

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        storage = get_nested_value(self.coordinator.data, ["msd", "storage"], {})
        total = storage.get("total")
        available = storage.get("available")
        if total is None or available is None or total <= 0:
            _LOGGER.debug("MSD storage data missing or invalid: %r", storage)
            return None
        used = total - available
        return round((used / total) * 100, 2)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        storage_data = get_nested_value(self.coordinator.data, ["msd", "storage"], {})
        
        total = storage_data.get("total")
        available = storage_data.get("available")

        if total is not None:
            attributes["total_size_mb"] = round(bytes_to_mb(total), 2)
        if available is not None:
            attributes["free_size_mb"] = round(bytes_to_mb(available), 2)
        if total is not None and available is not None:
            used = total - available
            attributes["used_size_mb"] = round(bytes_to_mb(used), 2)
        
        state = self.state
        if state is not None:
            attributes["percent_used"] = state

        images = storage_data.get("images", {}) or {}
        if images:
            if len(images) < 20:
                for image, details in images.items():
                    size = details.get("size")
                    if size is not None:
                        attributes[image] = size
            else:
                attributes["file count"] = len(images)
        return attributes
