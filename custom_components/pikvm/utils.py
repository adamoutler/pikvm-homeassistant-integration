"""Utility functions for the PiKVM integration."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_TOTP,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)
_SENTINEL = object()


def normalize_url(input_url: str) -> str:
    """Ensure the URL is properly formatted."""
    url = input_url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


format_url = normalize_url


def create_data_schema(user_input: Mapping[str, Any] | None = None) -> vol.Schema:
    """Create the data schema for the form."""
    input_data = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=input_data.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_USERNAME, default=input_data.get(CONF_USERNAME, DEFAULT_USERNAME)
            ): str,
            vol.Required(
                CONF_PASSWORD, default=input_data.get(CONF_PASSWORD, DEFAULT_PASSWORD)
            ): str,
            vol.Optional(CONF_TOTP, default=input_data.get(CONF_TOTP, "")): str,
        }
    )


def update_existing_entry(
    hass: HomeAssistant | None,
    existing_entry: config_entries.ConfigEntry,
    user_input: Mapping[str, Any],
) -> None:
    """Update an existing config entry."""
    updated_data = dict(existing_entry.data)
    updated_data.update(user_input)
    # Ensure the serial number is included in the updated data
    if "serial" not in updated_data:
        updated_data["serial"] = existing_entry.data.get("serial")
    if hass is not None:
        hass.config_entries.async_update_entry(existing_entry, data=updated_data)


def find_existing_entry(
    flow_handler: Any, serial: str | None
) -> config_entries.ConfigEntry | None:
    """Find an existing entry with the same serial number."""
    if not serial:
        return None

    existing_entries: list[config_entries.ConfigEntry] = (
        flow_handler._async_current_entries()
    )
    for entry in existing_entries:
        entry_serial = entry.data.get("serial")
        _LOGGER.debug("Checking existing %s against %s", entry_serial, serial)
        if entry_serial and entry_serial.lower() == serial.lower():
            return entry
    _LOGGER.debug("No existing entry found for %s, configuring", serial)
    return None


async def get_translations(
    hass: HomeAssistant, language: str, domain: str
) -> Callable[[str, Any], Any]:
    """Get translations for the given language and domain."""
    if hass is None:
        raise ValueError("HomeAssistant instance cannot be None")
    translations = await async_get_translations(hass, language, "config")

    def translate(key: str, default: Any) -> Any:
        return translations.get(f"component.{domain}.{key}", default)

    return translate


def get_unique_id_base(
    entry_or_host: config_entries.ConfigEntry | str,
    coordinator_or_port: Any,
) -> str:
    """Generate the unique_id_base for sensors or device tracking.

    Supports both (config_entry, coordinator) and (host, port) signatures.
    """
    if isinstance(entry_or_host, str):
        host = entry_or_host.strip()
        for prefix in ("https://", "http://"):
            host = host.removeprefix(prefix)
        clean_host = host.rstrip("/").replace("/", "_").replace(":", "_")
        return f"{clean_host}_{coordinator_or_port}"

    config_entry = entry_or_host
    coordinator = coordinator_or_port

    serial: str | None = None
    if coordinator is not None:
        coord_serial = get_nested_value(
            getattr(coordinator, "data", None), ["hw", "platform", "serial"]
        )
        if (
            isinstance(coord_serial, (str, int))
            and not isinstance(coord_serial, bool)
            and str(coord_serial).strip()
            and str(coord_serial).strip().lower() != "none"
        ):
            serial = str(coord_serial).strip()

    if (
        not serial
        and hasattr(config_entry, "data")
        and isinstance(config_entry.data, Mapping)
    ):
        entry_serial = config_entry.data.get("serial")
        if (
            isinstance(entry_serial, (str, int))
            and not isinstance(entry_serial, bool)
            and str(entry_serial).strip()
            and str(entry_serial).strip().lower() != "none"
        ):
            serial = str(entry_serial).strip()

    if not serial:
        unique_id = getattr(config_entry, "unique_id", None)
        if (
            isinstance(unique_id, (str, int))
            and not isinstance(unique_id, bool)
            and str(unique_id).strip()
            and str(unique_id).strip().lower() != "none"
        ):
            serial = str(unique_id).strip()

    if not serial or serial.lower() == "none":
        serial = "unknown"

    return f"{config_entry.entry_id}_{serial}"


def get_nested_value(
    data: Any,
    keys: Sequence[str] | str,
    default: Any = None,
) -> Any:
    """Safely get a nested value from a dictionary or mapping.

    :param data: The dictionary/mapping to search.
    :param keys: A sequence of keys to traverse the dictionary (or single key string).
    :param default: The default value to return if the keys are not found.
    :return: The value found or the default value.
    """
    if data is None or keys is None:
        return default
    if isinstance(keys, str):
        key_list: Sequence[Any] = [keys]
    elif isinstance(keys, Sequence):
        key_list = keys
    else:
        return default

    for key in key_list:
        if isinstance(data, Mapping) or hasattr(data, "get"):
            try:
                data = data.get(key, _SENTINEL)
                if data is _SENTINEL:
                    return default
            except (
                ArithmeticError,
                AttributeError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                return default
        else:
            return default
    return data


def bytes_to_mb(bytes_value: Any) -> float | None:
    """Convert bytes to megabytes.

    :param bytes_value: The value in bytes.
    :return: The value in megabytes, or None if bytes_value is None or invalid.
    """
    if bytes_value is None:
        return None
    try:
        val = float(bytes_value)
        if not math.isfinite(val):
            return None
        return val / (1024 * 1024)
    except (ValueError, TypeError, OverflowError):
        return None
