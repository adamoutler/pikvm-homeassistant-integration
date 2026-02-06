"""The PiKVM integration."""

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .cert_handler import format_url
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
from .sensor import PiKVMEntity
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
    stored_serial = entry.data.get("serial", None)
    unique_id = entry.unique_id

    # Check if the unique ID matches the stored serial number
    if stored_serial and unique_id != stored_serial:
        _LOGGER.debug("Updating unique ID from %s to %s", unique_id, stored_serial)
        hass.config_entries.async_update_entry(entry, unique_id=stored_serial)

    coordinator = PiKVMDataUpdateCoordinator(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_TOTP, ""),
        entry.data[CONF_CERTIFICATE],  # Pass the serialized certificate
    )
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Retrieve hardware and system information safely
    platform = get_nested_value(coordinator.data, ["hw", "platform"], {})
    kvmd = get_nested_value(coordinator.data, ["system", "kvmd"], {})

    PiKVMEntity.DEVICE_INFO = DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_SERIAL])},
        configuration_url=format_url(entry.data[CONF_HOST]),
        serial_number=entry.data[CONF_SERIAL],
        manufacturer=MANUFACTURER,
        name=entry.title,
        model=platform.get("model") or platform.get("type"),
        hw_version=platform.get("base"),
        sw_version=kvmd.get("version"),
    )

    # Perform the platform setup outside the event loop to avoid blocking
    async def forward_platform():
        integration = await async_get_integration(hass, DOMAIN)
        # Run tasks concurrently if possible

        await asyncio.gather(
            hass.async_add_executor_job(integration.get_platform, "sensor"),
            hass.config_entries.async_forward_entry_setups(entry, ["sensor"]),
        )

    hass.async_create_task(forward_platform())

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    This function is responsible for unloading a configuration entry in Home Assistant.
    It forwards the entry unload signal to the 'sensor' component and removes the entry from the 'pikvm' domain data.

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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry.

    This function is responsible for cleaning up any resources associated with the device
    when a configuration entry is removed from Home Assistant.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The configuration entry to remove.
    """
    # Forward the entry removal signal to the 'sensor' component
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    # Remove the entry from the 'pikvm' domain data
    hass.data[DOMAIN].pop(entry.entry_id, None)

    # Perform any additional cleanup here if necessary
    # For example, remove any persistent notifications, stop background tasks, etc.
