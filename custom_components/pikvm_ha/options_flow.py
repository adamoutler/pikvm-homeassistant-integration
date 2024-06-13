import logging
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD
from .utils import create_data_schema, get_translations  # Import from utils.py

_LOGGER = logging.getLogger(__name__)

class PiKVMOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle PiKVM options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the PiKVM options."""
        errors = {}
        self.translations = await get_translations(self.hass, self.hass.config.language, DOMAIN)
        _LOGGER.debug("Entered async_step_init with data: %s", user_input)

        if user_input is not None:
            # Update the config entry with new data
            self.hass.config_entries.async_update_entry(self.config_entry, options=user_input)
            return self.async_create_entry(title="", data={})

        # Load existing entry data for reconfiguration
        default_url = self.config_entry.options.get(CONF_URL, self.config_entry.data.get(CONF_URL, ""))
        default_username = self.config_entry.options.get(CONF_USERNAME, self.config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME))
        default_password = self.config_entry.options.get(CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD))

        data_schema = create_data_schema({
            CONF_URL: default_url,
            CONF_USERNAME: default_username,
            CONF_PASSWORD: default_password
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": self.translations("config.step.init.data.url", "URL or IP address of the PiKVM device"),
                "username": self.translations("config.step.init.data.username", "Username for PiKVM"),
                "password": self.translations("config.step.init.data.password", "Password for PiKVM")
            }
        )
