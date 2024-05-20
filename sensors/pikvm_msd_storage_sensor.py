from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMSDStorageSensor(SensorEntity):
    """Representation of MSD Storage Sensor."""

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "PiKVM Storage"
        self._attr_unique_id = "pikvm_msd_storage"
        _LOGGER.debug("Initialized PiKVM MSD Storage sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            free_space = self.coordinator.data["msd"]["storage"]["parts"][""]["free"]
            total_space = self.coordinator.data["msd"]["storage"]["parts"][""]["size"]
            return round((total_space - free_space) / total_space * 100, 2)
        except KeyError as e:
            _LOGGER.error("Key error accessing MSD storage data: %s", e)
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        try:
            attributes.update({
                "images": list(self.coordinator.data["msd"]["storage"]["images"].keys()),
                "downloading": self.coordinator.data["msd"]["storage"]["downloading"],
                "uploading": self.coordinator.data["msd"]["storage"]["uploading"]
            })
        except KeyError as e:
            _LOGGER.error("Key error accessing MSD storage attributes: %s", e)
        return attributes

    async def async_update(self):
        """Update PiKVM MSD Storage sensor."""
        _LOGGER.debug("Updating PiKVM MSD Storage sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()
