"""Platform for PiKVM sensor integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .coordinator import PiKVMDataUpdateCoordinator
from .entity import PiKVMEntity
from .utils import bytes_to_mb, get_nested_value, get_unique_id_base

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PiKVMSensorEntityDescription(SensorEntityDescription):
    """Describes a PiKVM sensor entity."""

    value_fn: Callable[[Any], StateType]
    attributes_fn: Callable[[Any], dict[str, Any]] | None = None
    available_fn: Callable[[Any], bool] | None = None


def _get_cpu_temp(data: Any) -> float | None:
    val = get_nested_value(data, ["hw", "health", "temp", "cpu"])
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _get_cpu_utilization(data: Any) -> float | None:
    val = get_nested_value(data, ["hw", "performance", "cpu", "utilization"])
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _get_memory_utilization(data: Any) -> float | None:
    val = get_nested_value(data, ["hw", "performance", "memory", "utilization"])
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _get_memory_attributes(data: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    available_bytes = get_nested_value(data, ["hw", "performance", "memory", "available"])
    total_bytes = get_nested_value(data, ["hw", "performance", "memory", "total"])
    if available_bytes is not None:
        attrs["available MB"] = bytes_to_mb(available_bytes)
    if total_bytes is not None:
        attrs["total MB"] = bytes_to_mb(total_bytes)
    return attrs


def _get_fan_speed(data: Any) -> int | None:
    val = get_nested_value(data, ["hw", "performance", "fan", "speed"])
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _get_fan_attributes(data: Any) -> dict[str, Any]:
    return get_nested_value(data, ["hw", "performance", "fan"], {}) or {}


def _get_msd_storage(data: Any) -> float | None:
    storage = get_nested_value(data, ["msd", "storage"], {})
    total = storage.get("total")
    available = storage.get("available")
    if total is None or available is None or total <= 0:
        return None
    used = total - available
    return round((used / total) * 100, 2)


def _get_msd_storage_attributes(data: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    storage_data = get_nested_value(data, ["msd", "storage"], {})
    total = storage_data.get("total")
    available = storage_data.get("available")

    if total is not None:
        attrs["total_size_mb"] = round(bytes_to_mb(total), 2)
    if available is not None:
        attrs["free_size_mb"] = round(bytes_to_mb(available), 2)
    if total is not None and available is not None:
        used = total - available
        attrs["used_size_mb"] = round(bytes_to_mb(used), 2)

    val = _get_msd_storage(data)
    if val is not None:
        attrs["percent_used"] = val

    images = storage_data.get("images", {}) or {}
    if images:
        if len(images) < 20:
            for image, details in images.items():
                size = details.get("size")
                if size is not None:
                    attrs[image] = size
        else:
            attrs["file count"] = len(images)
    return attrs


CPU_TEMP_SENSOR_DESCRIPTION = PiKVMSensorEntityDescription(
    key="cpu_temp",
    translation_key="cpu_temp",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    suggested_display_precision=1,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:thermometer",
    value_fn=_get_cpu_temp,
    available_fn=lambda data: _get_cpu_temp(data) is not None,
)

CPU_UTILIZATION_SENSOR_DESCRIPTION = PiKVMSensorEntityDescription(
    key="cpu_utilization",
    translation_key="cpu_utilization",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
    suggested_display_precision=1,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:cpu-64-bit",
    value_fn=_get_cpu_utilization,
    available_fn=lambda data: "performance" in get_nested_value(data, ["hw"], {}),
)

MEMORY_UTILIZATION_SENSOR_DESCRIPTION = PiKVMSensorEntityDescription(
    key="memory_utilization",
    translation_key="memory_utilization",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
    suggested_display_precision=1,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:memory",
    value_fn=_get_memory_utilization,
    attributes_fn=_get_memory_attributes,
    available_fn=lambda data: "performance" in get_nested_value(data, ["hw"], {}),
)

FAN_SPEED_SENSOR_DESCRIPTION = PiKVMSensorEntityDescription(
    key="fan_speed",
    translation_key="fan_speed",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:fan",
    value_fn=_get_fan_speed,
    attributes_fn=_get_fan_attributes,
    available_fn=lambda data: "fan" in get_nested_value(data, ["hw", "performance"], {}),
)

MSD_STORAGE_SENSOR_DESCRIPTION = PiKVMSensorEntityDescription(
    key="msd_storage",
    translation_key="msd_storage",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
    suggested_display_precision=2,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:database",
    value_fn=_get_msd_storage,
    attributes_fn=_get_msd_storage_attributes,
    available_fn=lambda data: get_nested_value(data, ["msd", "storage"]) is not None,
)

SENSOR_DESCRIPTIONS: tuple[PiKVMSensorEntityDescription, ...] = (
    CPU_TEMP_SENSOR_DESCRIPTION,
    CPU_UTILIZATION_SENSOR_DESCRIPTION,
    MEMORY_UTILIZATION_SENSOR_DESCRIPTION,
    FAN_SPEED_SENSOR_DESCRIPTION,
    MSD_STORAGE_SENSOR_DESCRIPTION,
)


class PiKVMSensor(PiKVMEntity, SensorEntity):
    """Representation of a PiKVM sensor."""

    entity_description: PiKVMSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PiKVMDataUpdateCoordinator,
        unique_id_base: str,
        description: PiKVMSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, unique_id_base)
        self.entity_description = description
        self._attr_unique_id = f"{unique_id_base}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return True if the sensor data is available."""
        if not super().available:
            return False
        if self.entity_description.available_fn is not None:
            return self.entity_description.available_fn(self.coordinator.data)
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs: dict[str, Any] = {"ip": self.coordinator.url}
        if self.entity_description.attributes_fn is not None:
            extra = self.entity_description.attributes_fn(self.coordinator.data)
            if extra:
                attrs.update(extra)
        return attrs


class PiKVMBaseSensor(PiKVMSensor):
    """Base class for a PiKVM sensor (backward-compatible subclass)."""

    def __init__(
        self,
        coordinator: PiKVMDataUpdateCoordinator,
        unique_id_base: str,
        sensor_type: str,
        name: str | None = None,
        unit: str | None = None,
        icon: str | None = None,
        description: PiKVMSensorEntityDescription | None = None,
    ) -> None:
        """Initialize base sensor with fallback description."""
        if description is None:
            description = PiKVMSensorEntityDescription(
                key=sensor_type,
                name=name or sensor_type.replace("_", " ").title(),
                translation_key=sensor_type,
                native_unit_of_measurement=unit,
                icon=icon,
                value_fn=lambda _: None,
            )
        super().__init__(coordinator, unique_id_base, description)
        self._attr_unique_id = f"{unique_id_base}_{sensor_type}"
        self._attr_name = name
        self._attr_unit_of_measurement = unit
        self._attr_icon = icon
        self._sensor_type = sensor_type
        self._unique_id_base = unique_id_base

    @property
    def unit_of_measurement(self) -> str | None:
        """Return the preferred units of measure."""
        if getattr(self, "_attr_unit_of_measurement", None) is not None:
            return self._attr_unit_of_measurement
        if getattr(self, "_attr_native_unit_of_measurement", None) is not None:
            return self._attr_native_unit_of_measurement
        if getattr(self, "entity_description", None) is not None:
            return getattr(self.entity_description, "native_unit_of_measurement", None)
        return None

    @property
    def state(self) -> str | int | float | bool | None:
        """Return the state of the sensor."""
        if type(self) is PiKVMBaseSensor:
            raise NotImplementedError(
                "The state method must be implemented by the subclass."
            )
        return self.native_value


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PiKVM sensors from a config entry."""
    _LOGGER.debug("Setting up PiKVM sensors from config entry")
    coordinator: PiKVMDataUpdateCoordinator = (
        getattr(config_entry, "runtime_data", None)
        or hass.data[DOMAIN][config_entry.entry_id]
    )
    unique_id_base = get_unique_id_base(config_entry, coordinator)

    sensors = [
        PiKVMSensor(coordinator, unique_id_base, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(sensors, True)
    _LOGGER.debug("PiKVM sensors added to Home Assistant")


# pylint: disable=import-outside-toplevel
def lazy_import_sensors():
    """Lazy load the sensor classes."""
    from .sensors.pikvm_cpu_temp_sensor import PiKVMCpuTempSensor
    from .sensors.pikvm_cpu_utilization_sensor import PiKVMCpuUtilizationSensor
    from .sensors.pikvm_extra_sensor import PiKVMExtraSensor
    from .sensors.pikvm_fan_speed_sensor import PiKVMFanSpeedSensor
    from .sensors.pikvm_memory_utilization_sensor import PiKVMMemoryUtilizationSensor
    from .sensors.pikvm_msd_drive_sensor import PiKVMSDDriveSensor
    from .sensors.pikvm_msd_enabled_sensor import PiKVMSDEnabledSensor
    from .sensors.pikvm_msd_storage_sensor import PiKVMSDStorageSensor
    from .sensors.pikvm_throttling_sensor import PiKVMThrottlingSensor

    return {
        "cpu_temp": PiKVMCpuTempSensor,
        "cpu_utilization": PiKVMCpuUtilizationSensor,
        "extra": PiKVMExtraSensor,
        "fan_speed": PiKVMFanSpeedSensor,
        "memory_utilization": PiKVMMemoryUtilizationSensor,
        "msd_drive": PiKVMSDDriveSensor,
        "msd_enabled": PiKVMSDEnabledSensor,
        "msd_storage": PiKVMSDStorageSensor,
        "throttling": PiKVMThrottlingSensor,
    }
