import logging
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD, CONF_CERTIFICATE
from .utils import create_data_schema, get_translations, format_url, update_existing_entry
from .cert_handler import fetch_serialized_cert, is_pikvm_device

_LOGGER = logging.getLogger(__name__)

class PiKVMOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle PiKVM options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the PiKVM options."""
        errors = {}
        self.translate = await get_translations(self.hass, self.hass.config.language, DOMAIN)
        _LOGGER.debug("Entered async_step_init with data: %s", user_input)

        if user_input is not None:
            # Validate the new credentials
            url = format_url(user_input[CONF_HOST])
            username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)

            _LOGGER.debug("Manual setup with URL %s, username %s", url, username)

            serialized_cert = await fetch_serialized_cert(self.hass, url)
            if not serialized_cert:
                errors["base"] = "cannot_fetch_cert"
                _LOGGER.error("Cannot fetch cert from URL: %s", url)
            else:
                _LOGGER.debug("Serialized certificate: %s", serialized_cert)
                user_input[CONF_CERTIFICATE] = serialized_cert

                is_pikvm, serial, name = await is_pikvm_device(self.hass, url, username, password, serialized_cert)
                if name is None or name == "localhost.localdomain":
                    name = "pikvm"
                elif name.startswith("Exception_"):
                    errors["base"] = name
                else:
                    if is_pikvm:
                        _LOGGER.debug("PiKVM device successfully found at %s with serial %s", url, serial)

                        existing_entry = None
                        for entry in self.hass.config_entries.async_entries(DOMAIN):
                            if entry.unique_id == serial:
                                existing_entry = entry
                                break

                        if existing_entry:
                            update_existing_entry(self.hass, existing_entry, user_input)
                            return self.async_create_entry(title="", data={})

                        user_input["serial"] = serial
                        new_data = {**self.config_entry.data, **user_input}
                        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                        return self.async_create_entry(title="", data={})

                    else:
                        errors["base"] = "cannot_connect"
                        _LOGGER.error("Cannot connect to PiKVM device at %s with provided credentials.", url)

        # Load existing entry data for reconfiguration
        default_url = self.config_entry.data.get(CONF_HOST, "")
        default_username = self.config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
        default_password = self.config_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)

        data_schema = create_data_schema({
            CONF_HOST: default_url,
            CONF_USERNAME: default_username,
            CONF_PASSWORD: default_password
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": self.translate("config.step.user.data.url", "URL or IP address of the PiKVM device"),
                "username": self.translate("config.step.user.data.username", "Username for PiKVM"),
                "password": self.translate("config.step.user.data.password", "Password for PiKVM")
            }
        )

async def handle_user_input(self, user_input):
    """Handle user input for the configuration."""
    errors = {}
    url = format_url(user_input[CONF_HOST])
    user_input[CONF_HOST] = url

    username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
    password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)

    _LOGGER.debug("Manual setup with URL %s, username %s", url, username)

    serialized_cert = await fetch_serialized_cert(self.hass, url)
    if not serialized_cert:
        errors["base"] = "cannot_fetch_cert"
        return None, errors
    else:
        _LOGGER.debug("Serialized certificate: %s", serialized_cert)
        user_input[CONF_CERTIFICATE] = serialized_cert

        is_pikvm, serial, name = await is_pikvm_device(self.hass, url, username, password, serialized_cert)
        if name is None or name == "localhost.localdomain":
            name = "pikvm"
        elif name.startswith("Exception_"):
            errors["base"] = name
            return None, errors

        if is_pikvm:
            _LOGGER.debug("PiKVM device successfully found at %s with serial %s", url, serial)

            existing_entry = None
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.unique_id == serial:
                    existing_entry = entry
                    break

            if existing_entry:
                update_existing_entry(self.hass, existing_entry, user_input)
                return self.async_create_entry(title="", data={})

            user_input["serial"] = serial
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()
            config_flow_result = self.async_create_entry(title=name if name else "PiKVM", data=user_input)

            return config_flow_result, None
        else:
            _LOGGER.error("Cannot connect to PiKVM device at %s", url)
            errors["base"] = "cannot_connect"
            return None, errors
