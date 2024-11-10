"""Module for PiKVM extra sensor integration."""

from homeassistant.const import EntityCategory

from ..sensor import PiKVMBaseSensor


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
        self._data = data
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._data["enabled"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        attributes.update(self._data)
        return attributes
