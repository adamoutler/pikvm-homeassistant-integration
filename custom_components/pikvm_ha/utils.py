"""Utility functions for the PiKVM integration."""

import re
import voluptuous as vol

from homeassistant.core import HomeAssistant
import logging
from homeassistant import config_entries
from homeassistant.helpers.translation import async_get_translations
from homeassistant.components.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)



def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip("/")


def create_data_schema(user_input):
    """Create the data schema for the form."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_USERNAME, default=user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            ): str,
            vol.Required(
                CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
            ): str,
        }
    )


def update_existing_entry(hass: HomeAssistant | None, existing_entry, user_input):
    """Update an existing config entry."""
    updated_data = existing_entry.data.copy()
    updated_data.update(user_input)
    # Ensure the serial number is included in the updated data
    if "serial" not in updated_data:
        updated_data["serial"] = existing_entry.data.get("serial")
    if hass is not None:
        hass.config_entries.async_update_entry(existing_entry, data=updated_data)


def find_existing_entry(flow_handler, serial) -> config_entries.ConfigEntry | None:
    """Find an existing entry with the same serial number."""
    existing_entries = flow_handler._async_current_entries()
    for entry in existing_entries:
        _LOGGER.debug("Checking existing %s against %s", entry.data.get("serial"), serial)
        if entry.data.get("serial").lower()  == serial.lower():
            return entry
    _LOGGER.debug("No existing entry found for %s, configuring", serial)
    return None


async def get_translations(hass: HomeAssistant, language, domain):
    """Get translations for the given language and domain."""
    if hass is None:
        raise ValueError("HomeAssistant instance cannot be None")
    translations = await async_get_translations(hass, language, "config")

    def translate(key, default):
        return translations.get(f"component.{domain}.{key}", default)

    return translate


def get_unique_id_base(config_entry, coordinator):
    """Generate the unique_id_base for the sensors."""
    return f"{config_entry.entry_id}_{coordinator.data['hw']['platform']['serial']}"


def get_nested_value(data, keys, default=None):
    """Safely get a nested value from a dictionary.

    :param data: The dictionary to search.
    :param keys: A list of keys to traverse the dictionary.
    :param default: The default value to return if the keys are not found.
    :return: The value found or the default value.
    """
    for key in keys:
        data = data.get(key, {})
    return data if data else default


def bytes_to_mb(bytes_value):
    """Convert bytes to megabytes.

    :param bytes_value: The value in bytes.
    :return: The value in megabytes.
    """
    return bytes_value / (1024 * 1024)


class PiKVMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiKVM."""
    ...
    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> config_entries.ConfigFlowResult:
        """Handle the ZeroConf discovery step."""
        serial = discovery_info.properties.get("serial")
        host = discovery_info.host
        if not serial or not host:
            _LOGGER.debug("Discovered device with ZeroConf but missing serial or host")
            return self.async_abort(reason="missing_serial_or_host")
        # Filter out IPv6 addresses
        if host.find(":") != -1:
            _LOGGER.debug("Discovered device with ZeroConf but IPv6 address")
            return self.async_abort(reason="ipv6_address")
        _LOGGER.debug(
            "Discovered device with ZeroConf: host=%s, serial=%s, model=%s",
            host,
            serial,
            discovery_info.properties.get("model"),
        )
        existing_entry = find_existing_entry(self, serial)
        if existing_entry:
            _LOGGER.debug(
                "Device with serial %s already configured, updating existing entry",
                serial,
            )
            existing_username = existing_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
            existing_password = existing_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)
            _LOGGER.debug(
                "Updating existing entry with host=%s, username=%s, password=%s",
                host,
                existing_username,
                re.sub(r'.', '*', existing_password),
            )
            update_existing_entry(
                self.hass,
                existing_entry,
                {
                    CONF_HOST: host,
                    CONF_USERNAME: existing_username,
                    CONF_PASSWORD: existing_password,
                    "serial": serial,  # Ensure serial is included
                },
            )
            return self.async_abort(reason="already_configured")
        # Offer options to add or ignore
        self._discovery_info = {
            CONF_HOST: host,
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD,
            "serial": serial,
        }
        return await self._show_zeroconf_menu()
