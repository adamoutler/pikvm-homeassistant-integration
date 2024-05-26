"""Platform for sensor integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .sensors import pikvm_cpu_temp_sensor
from .sensors import pikvm_extra_sensor
from .sensors import pikvm_fan_speed_sensor
from .sensors import pikvm_msd_drive_sensor
from .sensors import pikvm_msd_enabled_sensor
from .sensors import pikvm_msd_storage_sensor
from .sensors import pikvm_throttling_sensor

import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class PiKVMBaseSensor(CoordinatorEntity, Entity):
    """Base class for a PiKVM sensor."""

    def __init__(self, coordinator, device_info, serial_number, sensor_type, name, unit=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{serial_number}_{sensor_type}"
        self._attr_name = name
        self._attr_unit_of_measurement = unit
        self._serial_number = serial_number
        self._sensor_type = sensor_type

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"ip": self.coordinator.url}
        return attributes

    @property
    def state(self):
        """Return the state of the sensor."""
        raise NotImplementedError("The state method must be implemented by the subclass.")

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up PiKVM sensors from a config entry."""
    _LOGGER.debug("Setting up PiKVM sensors from config entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    serial_number = coordinator.data["hw"]["platform"]["serial"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, serial_number)},
        name="PiKVM",
        model=coordinator.data["hw"]["platform"]["base"],
        manufacturer="PiKVM",
        sw_version=coordinator.data["system"]["kvmd"]["version"],
    )

    # List of sensors to create
    sensors = [
        PiKVMCpuTempSensor(coordinator, device_info, serial_number),
        PiKVMFanSpeedSensor(coordinator, device_info, serial_number),
        PiKVMThrottlingSensor(coordinator, device_info, serial_number),
        PiKVMSDEnabledSensor(coordinator, device_info, serial_number),
        PiKVMSDDriveSensor(coordinator, device_info, serial_number),
        PiKVMSDStorageSensor(coordinator, device_info, serial_number),
    ]

    # Dynamically create sensors for extras
    for extra_name, extra_data in coordinator.data["extras"].items():
        sensors.append(PiKVMExtraSensor(coordinator, extra_name, extra_data, device_info, serial_number))

    _LOGGER.debug("Created PiKVM sensors: %s", sensors)
    async_add_entities(sensors, True)
    _LOGGER.debug("PiKVM sensors added to Home Assistant")
