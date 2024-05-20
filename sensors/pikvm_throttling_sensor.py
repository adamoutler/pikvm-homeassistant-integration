from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMThrottlingSensor(SensorEntity):
    """Representation of a Throttling Sensor."""

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "PiKVM Throttling"
        self._attr_unique_id = "pikvm_throttling"
        _LOGGER.debug("Initialized PiKVM Throttling sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            return self.coordinator.data["hw"]["health"]["throttling"]["raw_flags"]
        except KeyError as e:
            _LOGGER.error("Key error accessing Throttling data: %s", e)
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        try:
            attributes.update({
                "ignore_past": self.coordinator.data["hw"]["health"]["throttling"]["ignore_past"],
                "freq_capped_now": self.coordinator.data["hw"]["health"]["throttling"]["parsed_flags"]["freq_capped"]["now"],
                "freq_capped_past": self.coordinator.data["hw"]["health"]["throttling"]["parsed_flags"]["freq_capped"]["past"],
                "throttled_now": self.coordinator.data["hw"]["health"]["throttling"]["parsed_flags"]["throttled"]["now"],
                "throttled_past": self.coordinator.data["hw"]["health"]["throttling"]["parsed_flags"]["throttled"]["past"],
                "undervoltage_now": self.coordinator.data["hw"]["health"]["throttling"]["parsed_flags"]["undervoltage"]["now"],
                "undervoltage_past": self.coordinator.data["hw"]["health"]["throttling"]["parsed_flags"]["undervoltage"]["past"],
                "raw_flags": self.coordinator.data["hw"]["health"]["throttling"]["raw_flags"]
            })
        except KeyError as e:
            _LOGGER.error("Key error accessing Throttling attributes: %s", e)
        return attributes

    async def async_update(self):
        """Update PiKVM Throttling sensor."""
        _LOGGER.debug("Updating PiKVM Throttling sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()
