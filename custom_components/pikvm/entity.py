"""PiKVM entity base class."""

from __future__ import annotations

import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PiKVMDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class PiKVMEntity(CoordinatorEntity[PiKVMDataUpdateCoordinator]):
    """Base class for a PiKVM entity."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PiKVMDataUpdateCoordinator, unique_id_base: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id_base = unique_id_base
