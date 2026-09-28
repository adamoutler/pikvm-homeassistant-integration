"""Diagnostics for PiKVM integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CERTIFICATE, CONF_PASSWORD, CONF_TOTP, DOMAIN

TO_REDACT = {
    CONF_PASSWORD,
    CONF_TOTP,
    CONF_CERTIFICATE,
    "password",
    "totp",
    "totp_secret",
    "tls-certificate",
    "certificate",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)

    coordinator_data: dict[str, Any] | None = None
    if coordinator and coordinator.data is not None:
        if hasattr(coordinator.data, "raw"):
            coordinator_data = coordinator.data.raw
        elif isinstance(coordinator.data, dict):
            coordinator_data = coordinator.data

    return {
        "config_entry": async_redact_data(config_entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success if coordinator else None,
            "update_interval": str(coordinator.update_interval) if coordinator else None,
            "data": async_redact_data(coordinator_data, TO_REDACT) if coordinator_data else None,
        }
        if coordinator
        else {},
    }
