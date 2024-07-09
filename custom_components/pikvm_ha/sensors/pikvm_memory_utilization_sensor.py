
import logging
from ..sensor import PiKVMBaseSensor
from .. import PiKVMDataUpdateCoordinator
_LOGGER = logging.getLogger(__name__)


                                          
class PiKVMMemoryUtilizationSensor(PiKVMBaseSensor):
    """Representation of a PiKVM CPU temperature sensor."""

    def __init__(self, coordinator: PiKVMDataUpdateCoordinator, device_info, unique_id_base, device_name):
        """Initialize the sensor."""
        name = f"{device_name} Memory Utilization"
        super().__init__(coordinator, device_info, unique_id_base, "memory_utilization", name, "%", "mdi:memory")

    @property
    def state(self):
        """Return the state of the sensor in preferred units."""
        return self.coordinator.data["hw"]["health"]["mem"]["percent"]
    
    @property
    def available(self):
        """Return True if the sensor data is available."""
        return "mem" in self.coordinator.data["hw"]["health"]
    
    @property
    def unit_of_measurement(self):
        """Return the preferred units of measure"""
        return "%"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes
        attributes["total"]=self.coordinator.data["hw"]["health"]["mem"]["available"]
        attributes["total"]=self.coordinator.data["hw"]["health"]["mem"]["total"]
        return attributes
