"""The PiKVM integration."""

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from pikvm_aio import format_url, parse_host_port
from .const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    CONF_TOTP,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import PiKVMDataUpdateCoordinator
from .entity import PiKVMEntity
from .utils import get_nested_value

_LOGGER = logging.getLogger(__name__)

# Define a minimal CONFIG_SCHEMA
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.url,
                vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
                vol.Optional(CONF_TOTP, default=""): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the PiKVM component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PiKVM from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Clean host for title disambiguation
    raw_host = entry.data.get(CONF_HOST, "")
    try:
        clean_host = parse_host_port(raw_host)[0]
    except Exception:
        clean_host = raw_host or "unknown"

    # Pre-emptively disambiguate generic entry titles before network I/O
    if entry.title in ("PiKVM", "pikvm", "localhost.localdomain", "", None):
        hass.config_entries.async_update_entry(entry, title=f"PiKVM ({clean_host})")

    # Retrieve the unique ID and serial number safely from the config entry
    stored_serial = entry.data.get(CONF_SERIAL)
    unique_id = entry.unique_id
    effective_serial = stored_serial or unique_id or "unknown"

    # Check if the unique ID matches the stored serial number
    if stored_serial and unique_id != stored_serial:
        _LOGGER.debug("Updating unique ID from %s to %s", unique_id, stored_serial)
        hass.config_entries.async_update_entry(entry, unique_id=stored_serial)

    # Pre-emptively remove legacy mismatched devices and update device registry names
    # so offline and re-auth cards immediately display clean, disambiguated device names
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    expected_ident = (DOMAIN, effective_serial) if effective_serial != "unknown" else None

    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        is_mismatched = expected_ident is not None and expected_ident not in dev.identifiers
        if is_mismatched:
            _LOGGER.info("Removing legacy mismatched PiKVM device: %s (%s)", dev.name, dev.id)
            for ent in er.async_entries_for_device(ent_reg, dev.id, include_disabled_entities=True):
                ent_reg.async_remove(ent.entity_id)
            dev_reg.async_remove_device(dev.id)
        elif dev.name_by_user is None and dev.name in ("PiKVM", "pikvm", "localhost.localdomain", "", None):
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
    
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Retrieve hardware and system information safely
    raw_data = getattr(coordinator.data, "raw", None)
    if raw_data is None:
        raw_data = coordinator.data if isinstance(coordinator.data, dict) else {}

    platform = get_nested_value(raw_data, ["hw", "platform"], {})
    kvmd = get_nested_value(raw_data, ["system", "kvmd"], {})

    hw_info = getattr(coordinator.data, "hw", None)
    platform_info = getattr(hw_info, "platform", None)

    model = (
        getattr(platform_info, "model", None)
        or getattr(platform_info, "type", None)
        or platform.get("model")
        or platform.get("type")
        or getattr(coordinator.data, "model", None)
    )
    hw_version = getattr(platform_info, "base", None) or platform.get("base")
    sw_version = getattr(coordinator.data, "kvmd_version", None) or kvmd.get("version")

    # If the entry has a custom title, honor it; otherwise disambiguate with discovered name or model
    discovered_name = getattr(coordinator.data, "name", None)
    if entry.title and not (entry.title.startswith("PiKVM (") or entry.title in ("PiKVM", "pikvm")):
        device_name = entry.title
    elif discovered_name and discovered_name not in ("PiKVM", "pikvm", "localhost", "localhost.localdomain"):
        device_name = f"{discovered_name} ({clean_host})"
    elif model and model not in ("PiKVM", "pikvm"):
        device_name = f"PiKVM {model} ({clean_host})"
    else:
        device_name = f"PiKVM ({clean_host})"

    if entry.title != device_name and (entry.title.startswith("PiKVM (") or entry.title in ("PiKVM", "pikvm")):
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

    # Ensure device registry entry is in sync with latest device_name without deprecated async_get_device
    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if dev.name_by_user is None and dev.name != device_name:
            dev_reg.async_update_device(dev.id, name=device_name)

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Clean up orphaned devices that were created by previous versions
    await _async_cleanup_devices(hass, entry)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def _async_cleanup_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices that do not belong to this config entry or have no entities."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    
    stored_serial = entry.data.get(CONF_SERIAL) or entry.unique_id
    expected_ident = (DOMAIN, stored_serial) if stored_serial else None

    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    for device in devices:
        entities = er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True)
        is_mismatched = expected_ident is not None and expected_ident not in device.identifiers
        if not entities or is_mismatched:
            _LOGGER.info("Removing stale or orphaned PiKVM device: %s (%s)", device.name, device.id)
            if is_mismatched:
                for ent in entities:
                    ent_reg.async_remove(ent.entity_id)
            dev_reg.async_remove_device(device.id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    hass.data[DOMAIN].pop(entry.entry_id, None)

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry."""
    # Forward the entry removal signal to the 'sensor' component
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    # Remove the entry from the 'pikvm' domain data
    hass.data[DOMAIN].pop(entry.entry_id, None)