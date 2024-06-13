import logging
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD
from .config_flow import create_data_schema, handle_user_input, get_translations

_LOGGER = logging.getLogger(__name__)

class PiKVMOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle PiKVM options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the PiKVM options."""
        return await self.async_step_reconfigure()

    async def async_step_reconfigure(self, user_input=None):
        """Handle the reconfiguration step."""
        errors = {}
        self.translations = await get_translations(self.hass, self.hass.config.language, DOMAIN)
        _LOGGER.debug("Entered async_step_reconfigure with data: %s", user_input)

        if user_input is not None:
            entry, errors = await handle_user_input(self, user_input)
            if entry:
                # Update the config entry with new data
                self.hass.config_entries.async_update_entry(self.config_entry, data=user_input)
                return self.async_create_entry(title="", data={})

            # Keep the previously filled values
            default_url = user_input.get(CONF_URL, "")
            default_username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            default_password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
        else:
            # Load existing entry data for reconfiguration
            default_url = self.config_entry.data.get(CONF_URL, "")
            default_username = self.config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
            default_password = self.config_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)

        data_schema = create_data_schema({
            CONF_URL: default_url,
            CONF_USERNAME: default_username,
            CONF_PASSWORD: default_password
        })

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": self.translations("config.step.reconfigure.data.url", "URL or IP address of the PiKVM device"),
                "username": self.translations("config.step.reconfigure.data.username", "Username for PiKVM"),
                "password": self.translations("config.step.reconfigure.data.password", "Password for PiKVM")
            }
        )
