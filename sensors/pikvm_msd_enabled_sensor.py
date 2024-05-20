from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMSDEnabledSensor(SensorEntity):
    """Representation of MSD Enabled Sensor."""

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "PiKVM MSD Enabled"
        self._attr_unique_id = "pikvm_msd_enabled"
        _LOGGER.debug("Initialized PiKVM MSD Enabled sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            return self.coordinator.data["msd"]["enabled"]
        except KeyError as e:
            _LOGGER.error("Key error accessing MSD enabled data: %s", e)
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        try:
            attributes.update(self.coordinator.data["msd"]["drive"]["image"])
        except KeyError as e:
            _LOGGER.error("Key error accessing MSD enabled attributes: %s", e)
        return attributes

    async def async_update(self):
        """Update PiKVM MSD Enabled sensor."""
        _LOGGER.debug("Updating PiKVM MSD Enabled sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()
