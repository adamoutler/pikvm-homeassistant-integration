"""Support for PiKVM MSD enabled sensor."""

from __future__ import annotations

from homeassistant.const import EntityCategory

from ..sensor import PiKVMBaseSensor
from ..utils import get_nested_value


class PiKVMSDEnabledSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD enabled sensor."""

    def __init__(self, coordinator, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        name = f"{device_name} MSD Enabled"
        super().__init__(
            coordinator,
            unique_id_base,
            "msd_enabled",
            name,
            icon="mdi:check-circle",
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return True if the sensor data is available."""
        return super().available and get_nested_value(self.coordinator.data, ["msd"]) is not None

    @property
    def native_value(self) -> bool:
        """Return the native state of the sensor."""
        return bool(get_nested_value(self.coordinator.data, ["msd", "is_enabled"], False))

    @property
    def state(self) -> bool:
        """Return the state of the sensor."""
        return self.native_value
