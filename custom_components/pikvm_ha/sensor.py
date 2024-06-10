"""Platform for sensor integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class PiKVMBaseSensor(CoordinatorEntity):
    """Base class for a PiKVM sensor."""

    def __init__(self, coordinator, device_info, unique_id_base, sensor_type, name, unit=None, icon=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{unique_id_base}_{sensor_type}"
        self._attr_name = name
        self._attr_unit_of_measurement = unit
        self._attr_icon = icon
        self._unique_id_base = unique_id_base
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

    unique_id_base = f"{config_entry.entry_id}_{coordinator.data['hw']['platform']['serial']}"

    device_info = DeviceInfo(
        identifiers={(DOMAIN, unique_id_base)},
        name="PiKVM",
        model=coordinator.data["hw"]["platform"]["base"],
        manufacturer="PiKVM",
        sw_version=coordinator.data["system"]["kvmd"]["version"],
    )

    # Dynamically import sensor classes
    from .sensors.pikvm_cpu_temp_sensor import PiKVMCpuTempSensor
    from .sensors.pikvm_fan_speed_sensor import PiKVMFanSpeedSensor
    from .sensors.pikvm_throttling_sensor import PiKVMThrottlingSensor
    from .sensors.pikvm_msd_enabled_sensor import PiKVMSDEnabledSensor
    from .sensors.pikvm_msd_drive_sensor import PiKVMSDDriveSensor
    from .sensors.pikvm_msd_storage_sensor import PiKVMSDStorageSensor
    from .sensors.pikvm_extra_sensor import PiKVMExtraSensor

    # List of sensors to create
    sensors = [
        PiKVMCpuTempSensor(coordinator, device_info, unique_id_base),
        PiKVMFanSpeedSensor(coordinator, device_info, unique_id_base),
        PiKVMThrottlingSensor(coordinator, device_info, unique_id_base),
        PiKVMSDEnabledSensor(coordinator, device_info, unique_id_base),
        PiKVMSDDriveSensor(coordinator, device_info, unique_id_base),
        PiKVMSDStorageSensor(coordinator, device_info, unique_id_base),
    ]

    # Dynamically create sensors for extras
    for extra_name, extra_data in coordinator.data["extras"].items():
        sensors.append(PiKVMExtraSensor(coordinator, extra_name, extra_data, device_info, unique_id_base))

    _LOGGER.debug("Created PiKVM sensors: %s", sensors)
    async_add_entities(sensors, True)
    _LOGGER.debug("PiKVM sensors added to Home Assistant")