from homeassistant.helpers.entity import EntityCategory
from ..sensor import PiKVMBaseSensor

from homeassistant.helpers.entity import EntityCategory
from ..sensor import PiKVMBaseSensor

class PiKVMSDEnabledSensor(PiKVMBaseSensor):
    """Representation of a PiKVM MSD enabled sensor."""

    def __init__(self, coordinator, device_info, unique_id_base, device_name):
        """Initialize the sensor."""
        name = f"{device_name} MSD Enabled"
        super().__init__(coordinator, device_info, unique_id_base, "msd_enabled", name, icon="mdi:check-circle")
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["msd"]["enabled"]

