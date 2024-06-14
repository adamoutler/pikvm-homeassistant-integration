"""The PiKVM integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant import config_entries

from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, CONF_CERTIFICATE
from .coordinator import PiKVMDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the PiKVM component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PiKVM from a config entry.

    This function is responsible for setting up the PiKVM integration in Home Assistant
    based on the provided config entry.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The config entry for the PiKVM integration.

    Returns:
        bool: True if the setup was successful, False otherwise.
    """
    hass.data.setdefault(DOMAIN, {})

    # Retrieve the unique ID and serial number from the config entry
    stored_serial = entry.data.get('serial', None)
    unique_id = entry.unique_id

    # Check if the unique ID matches the stored serial number
    if stored_serial and unique_id != stored_serial:
        _LOGGER.debug(f"Updating unique ID from {unique_id} to {stored_serial}.")
        hass.config_entries.async_update_entry(entry, unique_id=stored_serial)

    coordinator = PiKVMDataUpdateCoordinator(
        hass,
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_CERTIFICATE]  # Pass the serialized certificate
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    This function is responsible for unloading a configuration entry in Home Assistant.
    It forwards the entry unload signal to the 'sensor' component and removes the entry from the 'pikvm_ha' domain data.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The configuration entry to unload.

    Returns:
        bool: True if the entry was successfully unloaded, False otherwise.
    """
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    hass.data[DOMAIN].pop(entry.entry_id)

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
