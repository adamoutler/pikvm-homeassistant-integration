from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMCpuTempSensor(SensorEntity):
    """Representation of a CPU Temp Sensor."""

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "PiKVM CPU Temp"
        self._attr_unique_id = "pikvm_cpu_temp"
        _LOGGER.debug("Initialized PiKVM CPU Temp sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            return self.coordinator.data["hw"]["health"]["temp"]["cpu"]
        except KeyError as e:
            _LOGGER.error("Key error accessing CPU Temp data: %s", e)
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        try:
            attributes["cpu_temp"] = self.coordinator.data["hw"]["health"]["temp"]["cpu"]
        except KeyError as e:
            _LOGGER.error("Key error accessing CPU Temp attributes: %s", e)
        return attributes

    async def async_update(self):
        """Update PiKVM CPU Temp sensor."""
        _LOGGER.debug("Updating PiKVM CPU Temp sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()
