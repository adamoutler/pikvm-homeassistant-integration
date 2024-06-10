"""Config flow for PiKVM integration."""
from homeassistant import config_entries
import voluptuous as vol
import logging
from .cert_handler import fetch_and_serialize_cert, is_pikvm_device
from .const import DHCP_CONFIG_FLAG, DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD, CONF_CERTIFICATE

_LOGGER = logging.getLogger(__name__)

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')


async def get_translations(hass, language, domain):
    """Get translations for the given language and domain."""
    translations = await hass.helpers.translation.async_get_translations(language, "config")
    def translate(key, default):
        return translations.get(f"component.{domain}.{key}", default)
    return translate

class PiKVMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiKVM."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        translations = await get_translations(self.hass, self.hass.config.language, DOMAIN)

        if user_input is not None:
            url = format_url(user_input[CONF_URL])
            user_input[CONF_URL] = url

            username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)

            _LOGGER.debug("Manual setup with URL %s, username %s", url, username)

            # Fetch and serialize the certificate
            serialized_cert = await self.hass.async_add_executor_job(fetch_and_serialize_cert, url)
            if not serialized_cert:
                errors["base"] = "cannot_fetch_cert"
            else:
                _LOGGER.debug("Serialized certificate: %s", serialized_cert)
                user_input[CONF_CERTIFICATE] = serialized_cert

                is_pikvm, serial = await is_pikvm_device(self.hass, url, username, password, serialized_cert)
                if is_pikvm:
                    _LOGGER.debug("PiKVM device successfully found at %s with serial %s", url, serial)

                    # Check if a device with the same serial number already exists
                    existing_entries = self._async_current_entries()
                    for entry in existing_entries:
                        if entry.data.get("serial") == serial:
                            _LOGGER.debug("Updating existing device with serial %s", serial)
                            updated_data = entry.data.copy()
                            updated_data.update(user_input)
                            self.hass.config_entries.async_update_entry(entry, data=updated_data)
                            return self.async_abort(reason=translations("config.step.abort.already_configured", "The device is already configured in Home Assistant, and the information is now updated."))

                    # Store the serial number in the config entry
                    user_input["serial"] = serial
                    return self.async_create_entry(title="PiKVM", data=user_input)
                else:
                    _LOGGER.error("Cannot connect to PiKVM device at %s", url)
                    errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required(CONF_URL, default=user_input.get(CONF_URL) if user_input else ""): str,
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, DEFAULT_USERNAME) if user_input else DEFAULT_USERNAME): str,
            vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD) if user_input else DEFAULT_PASSWORD): str,
        })
            
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": translations("config.step.user.data.url", "URL or IP address of the PiKVM device"),
                "username": translations("config.step.user.data.username", "Username for PiKVM"),
                "password": translations("config.step.user.data.password", "Password for PiKVM")
            }
        )

    async def async_step_dhcp(self, discovery_info):
        """Handle the DHCP discovery step."""
        ip_address = discovery_info.ip

        _LOGGER.debug("Discovered device with IP %s", ip_address)

        url = format_url(ip_address)
        data = {
            CONF_URL: url,
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD,
            DHCP_CONFIG_FLAG: True
        }

        return await self.async_step_user(user_input=data)
