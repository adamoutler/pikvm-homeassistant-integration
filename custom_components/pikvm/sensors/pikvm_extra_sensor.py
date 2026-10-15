"""Module for PiKVM extra sensor integration."""

from __future__ import annotations

from homeassistant.const import EntityCategory

from ..sensor import PiKVMBaseSensor
from ..utils import get_nested_value


class PiKVMExtraSensor(PiKVMBaseSensor):
    """Representation of a PiKVM extra sensor."""

    ICONS = {
        "ipmi": "mdi:network",
        "janus": "mdi:web",
        "janus_static": "mdi:web",
        "vnc": "mdi:monitor",
        "webterm": "mdi:console",
    }

    def __init__(self, coordinator, name, data, unique_id_base, device_name) -> None:
        """Initialize the sensor."""
        icon = self.ICONS.get(name, "mdi:information")
        sensor_name = f"{device_name} {name.capitalize()}"
        super().__init__(
            coordinator,
            unique_id_base,
            f"extra_{name}",
            sensor_name,
            icon=icon,
        )
        self._extra_name = name
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        if not super().available:
            return False
        extras = get_nested_value(self.coordinator.data, ["extras"], {})
        return self._extra_name in extras

    @property
    def native_value(self) -> bool:
        """Return the native running state."""
        extra_data = get_nested_value(
            self.coordinator.data, ["extras", self._extra_name], {}
        )
        return bool(extra_data.get("is_running", False))

    @property
    def state(self) -> bool:
        """Return the state of the sensor."""
        return self.native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        extra_data = get_nested_value(
            self.coordinator.data, ["extras", self._extra_name], {}
        )
        attributes.update(extra_data)
        return attributes
