from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMSDDriveSensor(SensorEntity):
    """Representation of MSD Drive Sensor."""

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "PiKVM MSD Drive"
        self._attr_unique_id = "pikvm_msd_drive"
        _LOGGER.debug("Initialized PiKVM MSD Drive sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            return "connected" if self.coordinator.data["msd"]["drive"]["connected"] else "disconnected"
        except KeyError as e:
            _LOGGER.error("Key error accessing MSD drive data: %s", e)
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        try:
            if self.coordinator.data["msd"]["drive"]["image"] != None:
                attributes.update(self.coordinator.data["msd"]["drive"]["image"])
        except KeyError as e:
            _LOGGER.error("Key error accessing MSD drive attributes: %s", e)
        return attributes

    async def async_update(self):
        """Update PiKVM MSD Drive sensor."""
        _LOGGER.debug("Updating PiKVM MSD Drive sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()
