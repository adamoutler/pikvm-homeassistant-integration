"""Platform for sensor integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
import logging

from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD
from .coordinator import PiKVMDataUpdateCoordinator
from .sensors.pikvm_cpu_temp_sensor import PiKVMCpuTempSensor
from .sensors.pikvm_fan_speed_sensor import PiKVMFanSpeedSensor
from .sensors.pikvm_throttling_sensor import PiKVMThrottlingSensor
from .sensors.pikvm_msd_enabled_sensor import PiKVMSDEnabledSensor
from .sensors.pikvm_msd_drive_sensor import PiKVMSDDriveSensor
from .sensors.pikvm_msd_storage_sensor import PiKVMSDStorageSensor
from .sensors.pikvm_extra_sensor import PiKVMExtraSensor

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up PiKVM sensors from a config entry."""
    _LOGGER.debug("Setting up PiKVM sensors from config entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.data["hw"]["platform"]["serial"])},
        name="PiKVM",
        model=coordinator.data["hw"]["platform"]["base"],
        manufacturer="PiKVM",
        sw_version=coordinator.data["system"]["kvmd"]["version"],
    )

    sensors = [
        PiKVMCpuTempSensor(coordinator, device_info),
        PiKVMFanSpeedSensor(coordinator, device_info),
        PiKVMThrottlingSensor(coordinator, device_info),
        PiKVMSDEnabledSensor(coordinator, device_info),
        PiKVMSDDriveSensor(coordinator, device_info),
        PiKVMSDStorageSensor(coordinator, device_info),
    ]

    # Dynamically create sensors for extras
    for extra_name, extra_data in coordinator.data["extras"].items():
        sensors.append(PiKVMExtraSensor(coordinator, extra_name, extra_data, device_info))

    _LOGGER.debug("Created PiKVM sensors: %s", sensors)
    async_add_entities(sensors, True)
    _LOGGER.debug("PiKVM sensors added to Home Assistant")
