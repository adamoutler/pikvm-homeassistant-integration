"""Platform for PiKVM binary sensor integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PiKVMDataUpdateCoordinator
from .entity import PiKVMEntity
from .utils import get_nested_value, get_unique_id_base

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

EXTRA_ICONS: dict[str, str] = {
    "ipmi": "mdi:network",
    "janus": "mdi:web",
    "janus_static": "mdi:web",
    "vnc": "mdi:monitor",
    "webterm": "mdi:console",
}


@dataclass(frozen=True, kw_only=True)
class PiKVMBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a PiKVM binary sensor entity."""

    is_on_fn: Callable[[Any], bool | None]
    attributes_fn: Callable[[Any], dict[str, Any]] | None = None
    available_fn: Callable[[Any], bool] | None = None


BINARY_SENSOR_DESCRIPTIONS: tuple[PiKVMBinarySensorEntityDescription, ...] = (
    PiKVMBinarySensorEntityDescription(
        key="throttling",
        translation_key="throttling",
        name="Throttling",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert",
        is_on_fn=lambda data: get_nested_value(data, ["hw", "health", "throttling", "raw_flags"], 0) > 0,
        attributes_fn=lambda data: get_nested_value(data, ["hw", "health", "throttling"], {}) or {},
        available_fn=lambda data: "throttling" in get_nested_value(data, ["hw", "health"], {})
        or "health" in get_nested_value(data, ["hw"], {}),
    ),
    PiKVMBinarySensorEntityDescription(
        key="msd_enabled",
        translation_key="msd_enabled",
        name="MSD Enabled",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:check-circle",
        is_on_fn=lambda data: bool(get_nested_value(data, ["msd", "is_enabled"], False)),
        available_fn=lambda data: get_nested_value(data, ["msd"]) is not None,
    ),
    PiKVMBinarySensorEntityDescription(
        key="msd_drive",
        translation_key="msd_drive",
        name="MSD Drive",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:usb",
        is_on_fn=lambda data: bool(get_nested_value(data, ["msd", "drive", "is_mounted"], False)),
        attributes_fn=lambda data: get_nested_value(data, ["msd", "drive"], {}) or {},
        available_fn=lambda data: get_nested_value(data, ["msd", "drive"]) is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PiKVM binary sensors from a config entry."""
    coordinator: PiKVMDataUpdateCoordinator = (
        getattr(config_entry, "runtime_data", None)
        or hass.data[DOMAIN][config_entry.entry_id]
    )
    unique_id_base = get_unique_id_base(config_entry, coordinator)

    # Clean up legacy sensor entities in registry to complete platform migration
    _async_cleanup_legacy_sensors(hass, unique_id_base, coordinator.data)

    entities: list[BinarySensorEntity] = [
        PiKVMBinarySensor(coordinator, unique_id_base, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]

    # Dynamically create binary sensors for extras (background services)
    extras = get_nested_value(coordinator.data, ["extras"], {})
    for extra_name, extra_data in extras.items():
        entities.append(
            PiKVMExtraBinarySensor(
                coordinator=coordinator,
                extra_name=extra_name,
                extra_data=extra_data,
                unique_id_base=unique_id_base,
            )
        )

    async_add_entities(entities)


def _async_cleanup_legacy_sensors(
    hass: HomeAssistant,
    unique_id_base: str,
    coordinator_data: Any,
) -> None:
    """Remove legacy sensor entities from entity registry during migration to binary_sensor."""
    ent_reg = er.async_get(hass)
    migrated_keys = ["throttling", "msd_enabled", "msd_drive"]
    extras = get_nested_value(coordinator_data, ["extras"], {})
    migrated_keys.extend([f"extra_{name}" for name in extras])

    for key in migrated_keys:
        old_unique_id = f"{unique_id_base}_{key}"
        old_entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if old_entity_id:
            _LOGGER.info(
                "Migrating legacy sensor %s to binary_sensor platform (unique_id: %s)",
                old_entity_id,
                old_unique_id,
            )
            ent_reg.async_remove(old_entity_id)


class PiKVMBinarySensor(PiKVMEntity, BinarySensorEntity):
    """Representation of a PiKVM binary sensor."""

    entity_description: PiKVMBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PiKVMDataUpdateCoordinator,
        unique_id_base: str,
        description: PiKVMBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, unique_id_base)
        self.entity_description = description
        self._attr_unique_id = f"{unique_id_base}_{description.key}"
        self._attr_name = description.name

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        if self.platform is None and self.entity_description is not None:
            return self.entity_description.name
        return super().name

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
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


class PiKVMExtraBinarySensor(PiKVMEntity, BinarySensorEntity):
    """Representation of a PiKVM extra service binary sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: PiKVMDataUpdateCoordinator,
        extra_name: str,
        extra_data: dict[str, Any],
        unique_id_base: str,
        device_name: str | None = None,
    ) -> None:
        """Initialize the extra service binary sensor."""
        super().__init__(coordinator, unique_id_base)
        self._extra_name = extra_name
        self._attr_unique_id = f"{unique_id_base}_extra_{extra_name}"
        self._attr_translation_key = f"extra_{extra_name}"
        self._attr_name = extra_name.replace("_", " ").title()
        self._attr_icon = EXTRA_ICONS.get(extra_name, "mdi:information")

    @property
    def is_on(self) -> bool:
        """Return true if the extra service is running."""
        extra_data = get_nested_value(
            self.coordinator.data, ["extras", self._extra_name], {}
        )
        return bool(extra_data.get("is_running", False))

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        if not super().available:
            return False
        extras = get_nested_value(self.coordinator.data, ["extras"], {})
        return self._extra_name in extras

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs: dict[str, Any] = {"ip": self.coordinator.url}
        extra_data = get_nested_value(
            self.coordinator.data, ["extras", self._extra_name], {}
        )
        if extra_data:
            attrs.update(extra_data)
        return attrs
