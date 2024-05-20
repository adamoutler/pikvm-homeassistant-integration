from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMExtraSensor(SensorEntity):
    """Representation of an Extra Sensor."""

    def __init__(self, coordinator, extra_name, extra_data, device_info):
        """Initialize the extra sensor."""
        self.coordinator = coordinator
        self._extra_name = extra_name
        self._extra_data = extra_data
        self._attr_device_info = device_info
        self._attr_name = f"PiKVM {extra_name}"
        self._attr_unique_id = f"pikvm_extra_{extra_name.lower()}"
        _LOGGER.debug("Initialized PiKVM extra sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the extra sensor."""
        return self._extra_data["enabled"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        attributes.update(self._extra_data)
        return attributes

    async def async_update(self):
        """Update PiKVM entity."""
        _LOGGER.debug("Updating PiKVM extra sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()
