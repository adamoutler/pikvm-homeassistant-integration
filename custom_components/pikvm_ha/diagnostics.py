from types import MappingProxyType
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN].get(config_entry.entry_id)

    entry_data = {
        "config_entry": {
            "domain": config_entry.domain,
            "title": config_entry.title,
            "unique_id": config_entry.unique_id,
            "version": config_entry.version,
            "source": config_entry.source,
            "data": _mask_sensitive_data(_expand_mapping_proxy(config_entry.data)),
            "options": _mask_sensitive_data(_expand_mapping_proxy(config_entry.options)),
        },
        "data": _mask_sensitive_data(_expand_mapping_proxy(config_entry.data)),
        "options": _mask_sensitive_data(_expand_mapping_proxy(config_entry.options)),
        "extra_state_data": _mask_sensitive_data(_expand_mapping_proxy(coordinator.data) if coordinator else {}),
        "coordinator": {
            "last_update_success": coordinator.last_update_success if coordinator else None,
            "update_interval": str(coordinator.update_interval) if coordinator else None,
        } if coordinator else {},
    }

    diagnostics_data = {
        config_entry.entry_id: {
            "config_entry_data": entry_data,
            "hass_data": _mask_sensitive_data(_expand_mapping_proxy(hass.data[DOMAIN][config_entry.entry_id])),
        }
    }
    return diagnostics_data

def _mask_sensitive_data(data):
    """Mask sensitive data such as passwords."""
    if not data:
        return data

    def mask_item(item):
        """Helper function to mask sensitive data in a single item."""
        if isinstance(item, dict):
            return {k: "******" if "password" in k else v for k, v in item.items()}
        elif isinstance(item, list):
            return [mask_item(i) for i in item]
        elif isinstance(item, MappingProxyType):
            return mask_item(dict(item))
        else:
            return item

    return mask_item(data)

def _expand_mapping_proxy(data):
    """Expand a mapping proxy to a dictionary."""
    if isinstance(data, MappingProxyType):
        return dict(data)
    return data
