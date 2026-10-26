"""Legacy domain (pikvm_ha -> pikvm) and duplicate entry migration helpers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
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
from homeassistant.helpers.typing import UNDEFINED

from .const import CONF_SERIAL, DOMAIN, LEGACY_DOMAIN
from .utils import normalize_serial


def _extract_serial_from_entry_or_device(
    entry: ConfigEntry | None,
    dev_reg: dr.DeviceRegistry,
) -> str | None:
    """Extract normalized serial from a ConfigEntry or its associated devices."""
    if entry is not None:
        serial = normalize_serial(entry.data.get(CONF_SERIAL)) or normalize_serial(
            entry.unique_id
        )
        if serial:
            return serial
        for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            for domain, ident in dev.identifiers:
                if domain in (DOMAIN, LEGACY_DOMAIN) and (
                    norm_ident := normalize_serial(ident)
                ):
                    return norm_ident
    return None


def _migrate_entity_to_pikvm(
    hass: HomeAssistant,
    ent_reg: er.EntityRegistry,
    entity_entry: er.RegistryEntry,
    new_entry_id: str,
    new_unique_id: str,
) -> None:
    """Safely migrate a single entity registry entry from pikvm_ha to pikvm."""
    if (
        entity_entry.platform == DOMAIN
        and entity_entry.config_entry_id == new_entry_id
        and entity_entry.unique_id == new_unique_id
    ):
        return

    if (
        state := hass.states.get(entity_entry.entity_id)
    ) is not None and state.state != STATE_UNKNOWN:
        hass.states.async_remove(entity_entry.entity_id)

    uid_arg = new_unique_id if new_unique_id != entity_entry.unique_id else UNDEFINED
    try:
        ent_reg.async_update_entity_platform(
            entity_entry.entity_id,
            DOMAIN,
            new_config_entry_id=new_entry_id,
            new_unique_id=uid_arg,
        )
    except ValueError:
        ent_reg.async_update_entity(
            entity_entry.entity_id,
            new_unique_id=uid_arg,
            config_entry_id=new_entry_id,
        )


def _cleanup_legacy_issues(hass: HomeAssistant, entry_id: str | None = None) -> None:
    """Remove stale Repairs issues left behind by pikvm_ha."""
    ir.async_delete_issue(hass, "homeassistant", f"integration_not_found.{LEGACY_DOMAIN}")
    if entry_id:
        ir.async_delete_issue(
            hass, "homeassistant", f"config_entry_reauth_{LEGACY_DOMAIN}_{entry_id}"
        )
        for dom in (LEGACY_DOMAIN, DOMAIN):
            ir.async_delete_issue(hass, dom, f"undervoltage_{entry_id}")
            ir.async_delete_issue(hass, dom, f"throttling_{entry_id}")


async def _deduplicate_entry_into_primary(
    hass: HomeAssistant,
    dev_reg: dr.DeviceRegistry,
    ent_reg: er.EntityRegistry,
    primary_entry: ConfigEntry,
    dup_entry: ConfigEntry,
) -> None:
    """Merge devices and entities from dup_entry into primary_entry and remove dup_entry."""
    new_id = primary_entry.entry_id
    old_id = dup_entry.entry_id

    for dev in dr.async_entries_for_config_entry(dev_reg, old_id):
        new_identifiers = {
            (DOMAIN if dom == LEGACY_DOMAIN else dom, ident)
            for dom, ident in dev.identifiers
        }
        dev_reg.async_update_device(
            dev.id,
            add_config_entry_id=new_id,
            new_identifiers=new_identifiers,
        )

    for entity_entry in er.async_entries_for_config_entry(ent_reg, old_id):
        new_uid = entity_entry.unique_id
        if new_uid.startswith(f"{old_id}_"):
            new_uid = f"{new_id}_{new_uid[len(old_id) + 1:]}"
        _migrate_entity_to_pikvm(hass, ent_reg, entity_entry, new_id, new_uid)

    for dev in dr.async_entries_for_config_entry(dev_reg, old_id):
        dev_reg.async_update_device(dev.id, remove_config_entry_id=old_id)

    _cleanup_legacy_issues(hass, old_id)
    await hass.config_entries.async_remove(old_id)


async def async_migrate_legacy_domain(
    hass: HomeAssistant,
    target_entry: ConfigEntry | None = None,
) -> bool:
    """Seamlessly migrate legacy `pikvm_ha` config entries and deduplicate `pikvm` entries by serial."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    migrated_any = False

    legacy_entries = list(hass.config_entries.async_entries(LEGACY_DOMAIN))
    current_entries = list(hass.config_entries.async_entries(DOMAIN))
    if (
        target_entry is not None
        and target_entry not in current_entries
        and target_entry.domain == DOMAIN
    ):
        current_entries.append(target_entry)

    pikvm_by_serial: dict[str, ConfigEntry] = {}
    for entry in current_entries:
        serial = _extract_serial_from_entry_or_device(entry, dev_reg)
        if not serial:
            continue
        existing_primary = pikvm_by_serial.get(serial)
        if existing_primary is not None and existing_primary.entry_id != entry.entry_id:
            if target_entry is not None and entry.entry_id == target_entry.entry_id:
                primary_entry, dup_entry = entry, existing_primary
                pikvm_by_serial[serial] = primary_entry
            else:
                primary_entry, dup_entry = existing_primary, entry
            await _deduplicate_entry_into_primary(
                hass, dev_reg, ent_reg, primary_entry, dup_entry
            )
            migrated_any = True
        else:
            pikvm_by_serial[serial] = entry

    for legacy_entry in legacy_entries:
        serial = _extract_serial_from_entry_or_device(legacy_entry, dev_reg)
        matching_new_entry = pikvm_by_serial.get(serial) if serial else None

        if (
            matching_new_entry is not None
            and matching_new_entry.entry_id != legacy_entry.entry_id
        ):
            await _deduplicate_entry_into_primary(
                hass, dev_reg, ent_reg, matching_new_entry, legacy_entry
            )
            migrated_any = True
        else:
            entry_id = legacy_entry.entry_id

            for dev in dr.async_entries_for_config_entry(dev_reg, entry_id):
                new_identifiers = {
                    (DOMAIN if dom == LEGACY_DOMAIN else dom, ident)
                    for dom, ident in dev.identifiers
                }
                if new_identifiers != dev.identifiers:
                    dev_reg.async_update_device(dev.id, new_identifiers=new_identifiers)

            for entity_entry in er.async_entries_for_config_entry(ent_reg, entry_id):
                _migrate_entity_to_pikvm(
                    hass, ent_reg, entity_entry, entry_id, entity_entry.unique_id
                )

            entries_dict = getattr(hass.config_entries, "_entries", None)
            if entries_dict is not None and entry_id in entries_dict:
                del entries_dict[entry_id]
                object.__setattr__(legacy_entry, "domain", DOMAIN)
                object.__setattr__(legacy_entry, "_integration_for_domain", None)
                getattr(legacy_entry, "clear_state_cache", lambda: None)()
                getattr(legacy_entry, "clear_storage_cache", lambda: None)()
                entries_dict[entry_id] = legacy_entry
                getattr(hass.config_entries, "_async_schedule_save", lambda: None)()
                getattr(hass.config_entries, "async_update_issues", lambda: None)()

            _cleanup_legacy_issues(hass, entry_id)
            if serial:
                pikvm_by_serial[serial] = legacy_entry
            migrated_any = True

            if target_entry is None or target_entry.entry_id != entry_id:
                hass.async_create_task(hass.config_entries.async_setup(entry_id))

    for item in list(dev_reg.devices):
        device_entry = dev_reg.async_get(item) if isinstance(item, str) else item
        if device_entry is None:
            continue
        legacy_serials = [
            ident for dom, ident in device_entry.identifiers if dom == LEGACY_DOMAIN
        ]
        if not legacy_serials:
            continue
        serial = legacy_serials[0].strip().lower()
        matched_entry = pikvm_by_serial.get(serial) or target_entry
        new_identifiers = {
            (DOMAIN if dom == LEGACY_DOMAIN else dom, ident)
            for dom, ident in device_entry.identifiers
        }
        if matched_entry is not None:
            dev_reg.async_update_device(
                device_entry.id,
                add_config_entry_id=matched_entry.entry_id,
                new_identifiers=new_identifiers,
            )
            for entity_entry in er.async_entries_for_device(
                ent_reg, device_entry.id, include_disabled_entities=True
            ):
                if (
                    entity_entry.platform == LEGACY_DOMAIN
                    or entity_entry.config_entry_id != matched_entry.entry_id
                ):
                    old_cfg_id = entity_entry.config_entry_id or ""
                    new_uid = entity_entry.unique_id
                    if old_cfg_id and new_uid.startswith(f"{old_cfg_id}_"):
                        new_uid = (
                            f"{matched_entry.entry_id}_{new_uid[len(old_cfg_id) + 1:]}"
                        )
                    _migrate_entity_to_pikvm(
                        hass, ent_reg, entity_entry, matched_entry.entry_id, new_uid
                    )
        else:
            dev_reg.async_update_device(device_entry.id, new_identifiers=new_identifiers)
        migrated_any = True

    _cleanup_legacy_issues(hass)
    return migrated_any
