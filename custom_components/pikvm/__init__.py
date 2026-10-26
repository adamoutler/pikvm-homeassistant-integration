"""The PiKVM integration."""

import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from pikvm_aio import format_url, parse_host_port

from .const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
    LEGACY_DOMAIN,
    MANUFACTURER,
)
from .coordinator import PiKVMDataUpdateCoordinator
from .migration import (
    _cleanup_legacy_issues,
    _deduplicate_entry_into_primary,
    _extract_serial_from_entry_or_device,
    _migrate_entity_to_pikvm,
    async_migrate_legacy_domain,
)
from .utils import extract_raw_dict, get_nested_value, normalize_serial

__all__ = [
    "PLATFORMS",
    "PiKVMConfigEntry",
    "_cleanup_legacy_issues",
    "_deduplicate_entry_into_primary",
    "_extract_serial_from_entry_or_device",
    "_migrate_entity_to_pikvm",
    "async_migrate_entry",
    "async_migrate_legacy_domain",
    "async_remove_config_entry_device",
    "async_remove_entry",
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
    "update_listener",
]

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type PiKVMConfigEntry = ConfigEntry[PiKVMDataUpdateCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)

_GENERIC_TITLES = ("PiKVM", "pikvm", "localhost", "localhost.localdomain", "", None)


async def async_migrate_entry(hass: HomeAssistant, config_entry: PiKVMConfigEntry) -> bool:
    """Migrate old config entry versions or legacy domain."""
    await async_migrate_legacy_domain(hass, target_entry=config_entry)
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the PiKVM component."""
    await async_migrate_legacy_domain(hass)
    return True



def _extract_device_metadata(
    data: object,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract normalized (live_serial, model, hw_version, sw_version) from coordinator data."""
    raw_data = extract_raw_dict(data)
    platform = get_nested_value(raw_data, ["hw", "platform"], {})
    if not isinstance(platform, dict):
        platform = {}
    kvmd = get_nested_value(raw_data, ["system", "kvmd"], {})
    if not isinstance(kvmd, dict):
        kvmd = {}

    platform_info = getattr(getattr(data, "hw", None), "platform", None)

    live_serial = normalize_serial(
        getattr(platform_info, "serial", None)
        or platform.get("serial")
        or getattr(data, "serial", None)
    )
    model = (
        getattr(platform_info, "model", None)
        or getattr(platform_info, "type", None)
        or platform.get("model")
        or platform.get("type")
        or getattr(data, "model", None)
    )
    hw_version = getattr(platform_info, "base", None) or platform.get("base")
    sw_version = getattr(data, "kvmd_version", None) or kvmd.get("version")
    return live_serial, model, hw_version, sw_version


def _resolve_device_name(
    entry_title: str | None,
    discovered_name: str | None,
    model: str | None,
    clean_host: str,
) -> tuple[str, bool]:
    """Determine (device_name, has_legacy_host) for entry title and DeviceInfo."""
    host_suffix = f" ({clean_host})"
    has_legacy_host = bool(
        entry_title
        and (
            (clean_host and entry_title.endswith(host_suffix))
            or entry_title.startswith("PiKVM (")
            or (
                discovered_name
                and entry_title.startswith(f"{discovered_name} (")
                and entry_title.endswith(")")
            )
        )
    )

    if entry_title and not (has_legacy_host or entry_title in _GENERIC_TITLES):
        device_name = entry_title
    elif discovered_name and discovered_name not in _GENERIC_TITLES:
        device_name = discovered_name
    elif model and model not in ("PiKVM", "pikvm"):
        device_name = f"PiKVM {model}"
    else:
        device_name = "PiKVM"
    return device_name, has_legacy_host


async def async_setup_entry(hass: HomeAssistant, entry: PiKVMConfigEntry) -> bool:
    """Set up PiKVM from a config entry."""
    await async_migrate_legacy_domain(hass, target_entry=entry)

    raw_host = entry.data.get(CONF_HOST, "")
    try:
        clean_host = parse_host_port(raw_host)[0]
    except Exception:  # noqa: BLE001
        clean_host = raw_host or "unknown"

    if entry.title in ("PiKVM", "pikvm", "localhost.localdomain", "", None):
        hass.config_entries.async_update_entry(entry, title="PiKVM")

    stored_serial = entry.data.get(CONF_SERIAL)
    unique_id = entry.unique_id
    effective_serial = stored_serial or unique_id or "unknown"

    if stored_serial and unique_id != stored_serial:
        _LOGGER.debug("Updating unique ID from %s to %s", unique_id, stored_serial)
        hass.config_entries.async_update_entry(entry, unique_id=stored_serial)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    expected_ident = (DOMAIN, effective_serial) if effective_serial != "unknown" else None

    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if expected_ident is not None and expected_ident not in dev.identifiers:
            _LOGGER.info("Removing legacy mismatched PiKVM device: %s (%s)", dev.name, dev.id)
            for ent in er.async_entries_for_device(ent_reg, dev.id, include_disabled_entities=True):
                ent_reg.async_remove(ent.entity_id)
            dev_reg.async_remove_device(dev.id)
        elif dev.name_by_user is None and (
            dev.name in ("PiKVM", "pikvm", "localhost.localdomain", "", None)
            or (clean_host and dev.name and dev.name.endswith(f" ({clean_host})"))
            or (dev.name and dev.name.startswith("PiKVM ("))
        ):
            _LOGGER.info("Updating legacy device name for %s to %s", dev.id, entry.title)
            dev_reg.async_update_device(dev.id, name=entry.title)

    coordinator = PiKVMDataUpdateCoordinator(
        hass,
        raw_host,
        entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
        entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        entry.data.get(CONF_TOTP, ""),
        entry.data.get(CONF_CERTIFICATE, ""),
        entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    live_serial, model, hw_version, sw_version = _extract_device_metadata(coordinator.data)
    if live_serial and effective_serial == "unknown":
        effective_serial = live_serial
        hass.config_entries.async_update_entry(
            entry,
            unique_id=effective_serial,
            data={**entry.data, CONF_SERIAL: effective_serial},
        )
        await async_migrate_legacy_domain(hass, target_entry=entry)

    discovered_name = getattr(coordinator.data, "name", None)
    device_name, has_legacy_host = _resolve_device_name(
        entry.title, discovered_name, model, clean_host
    )

    if entry.title != device_name and (has_legacy_host or entry.title in _GENERIC_TITLES):
        hass.config_entries.async_update_entry(entry, title=device_name)

    coordinator.device_info = DeviceInfo(
        identifiers={(DOMAIN, effective_serial)},
        configuration_url=format_url(raw_host),
        serial_number=effective_serial,
        manufacturer=MANUFACTURER,
        name=device_name,
        model=model,
        hw_version=hw_version,
        sw_version=sw_version,
    )

    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if dev.name_by_user is None and (
            dev.name != device_name
            or (clean_host and dev.name and dev.name.endswith(f" ({clean_host})"))
            or (dev.name and dev.name.startswith("PiKVM ("))
        ):
            dev_reg.async_update_device(dev.id, name=device_name)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_cleanup_devices(hass, entry)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def _async_cleanup_devices(hass: HomeAssistant, entry: PiKVMConfigEntry) -> None:
    """Remove devices that do not belong to this config entry or have no entities."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    stored_serial = entry.data.get(CONF_SERIAL) or entry.unique_id
    expected_ident = (DOMAIN, stored_serial) if stored_serial else None

    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        entities = er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True)
        is_mismatched = expected_ident is not None and expected_ident not in device.identifiers
        if not entities or is_mismatched:
            _LOGGER.info("Removing stale or orphaned PiKVM device: %s (%s)", device.name, device.id)
            if is_mismatched:
                for ent in entities:
                    ent_reg.async_remove(ent.entity_id)
            dev_reg.async_remove_device(device.id)


async def async_unload_entry(hass: HomeAssistant, entry: PiKVMConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: PiKVMConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: PiKVMConfigEntry) -> None:
    """Handle removal of a config entry."""
    ir.async_delete_issue(hass, DOMAIN, f"undervoltage_{entry.entry_id}")
    ir.async_delete_issue(hass, DOMAIN, f"throttling_{entry.entry_id}")
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)


def _normalize_identifier_set(identifiers: object) -> set[tuple[str, str]]:
    """Return a set of lowercase (domain, serial) pairs from an identifier collection."""
    if not isinstance(identifiers, (set, list, tuple)):
        return set()
    return {
        (str(item[0]).strip().lower(), str(item[1]).strip().lower())
        for item in identifiers
        if isinstance(item, tuple)
        and len(item) == 2
        and str(item[0]).strip()
        and str(item[1]).strip()
    }


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: PiKVMConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Remove a config entry from a device if the device is stale."""
    dev_name = getattr(device_entry, "name", None) or "Unknown"
    dev_id = getattr(device_entry, "id", None) or "Unknown"
    device_identifiers = getattr(device_entry, "identifiers", None)
    if not device_identifiers:
        _LOGGER.info("Allowing removal of PiKVM device %s (%s) with missing identifiers", dev_name, dev_id)
        return True

    raw_active: list[tuple[str, str]] = []
    active_serial = config_entry.data.get(CONF_SERIAL) or config_entry.unique_id
    if active_serial and (norm_serial := str(active_serial).strip().lower()):
        raw_active.extend([(DOMAIN, norm_serial), (LEGACY_DOMAIN, norm_serial)])

    coordinator = getattr(config_entry, "runtime_data", None)
    if (
        coordinator
        and getattr(coordinator, "device_info", None)
        and "identifiers" in coordinator.device_info
    ):
        raw_active.extend(coordinator.device_info["identifiers"])

    if _normalize_identifier_set(device_identifiers) & _normalize_identifier_set(raw_active):
        _LOGGER.warning("Cannot remove active PiKVM device %s (%s)", dev_name, dev_id)
        return False

    _LOGGER.info("Allowing removal of stale PiKVM device %s (%s)", dev_name, dev_id)
    return True