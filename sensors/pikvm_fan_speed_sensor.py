from homeassistant.components.sensor import SensorEntity
import logging

_LOGGER = logging.getLogger(__name__)

class PiKVMFanSpeedSensor(SensorEntity):
    """Representation of a Fan Speed Sensor."""

    def __init__(self, coordinator, device_info):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "PiKVM Fan Speed"
        self._attr_unique_id = "pikvm_fan_speed"
        _LOGGER.debug("Initialized PiKVM Fan Speed sensor: %s", self._attr_name)

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            return self.coordinator.data["fan"]["state"]["fan"]["speed"]
        except KeyError as e:
            _LOGGER.error("Key error accessing Fan Speed data: %s", e)
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        try:
            attributes.update({
                "fan_monitored": self.coordinator.data["fan"]["monitored"],
                "fan_last_fail_ts": self.coordinator.data["fan"]["state"]["fan"]["last_fail_ts"],
                "fan_ok": self.coordinator.data["fan"]["state"]["fan"]["ok"],
                "fan_pwm": self.coordinator.data["fan"]["state"]["fan"]["pwm"],
                "fan_speed": self.coordinator.data["fan"]["state"]["fan"]["speed"],
                "hall_available": self.coordinator.data["fan"]["state"]["hall"]["available"],
                "hall_rpm": self.coordinator.data["fan"]["state"]["hall"]["rpm"],
                "temp_fixed": self.coordinator.data["fan"]["state"]["temp"]["fixed"],
                "temp_real": self.coordinator.data["fan"]["state"]["temp"]["real"]
            })
        except KeyError as e:
            _LOGGER.error("Key error accessing Fan Speed attributes: %s", e)
        return attributes

    async def async_update(self):
        """Update PiKVM Fan Speed sensor."""
        _LOGGER.debug("Updating PiKVM Fan Speed sensor: %s", self._attr_name)
        await self.coordinator.async_request_refresh()