"""Config flow for PiKVM integration."""
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr
import voluptuous as vol
import logging
from .cert_handler import fetch_serialized_cert, is_pikvm_device
from .const import DHCP_CONFIG_FLAG, DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD, CONF_CERTIFICATE

_LOGGER = logging.getLogger(__name__)

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')

def update_existing_entry(self, existing_entry, user_input):
    """Update an existing config entry."""
    updated_data = existing_entry.data.copy()
    updated_data.update(user_input)
    self.hass.config_entries.async_update_entry(existing_entry, data=updated_data)

def find_existing_entry(self, serial):
    """Find an existing entry with the same serial number."""
    existing_entries = self._async_current_entries()
    for entry in existing_entries:
        if entry.data.get("serial") == serial:
            return entry
    return None

def create_data_schema(user_input):
    """Create the data schema for the form."""
    return vol.Schema({
        vol.Required(CONF_URL, default=user_input.get(CONF_URL, "")): str,
        vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
        vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)): str,
    })

async def handle_user_input(self, user_input):
    """Handle user input for the configuration."""
    errors = {}
    url = format_url(user_input[CONF_URL])
    user_input[CONF_URL] = url

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

            existing_entry = find_existing_entry(self, serial)
            if existing_entry:
                update_existing_entry(self, existing_entry, user_input)
                return self.async_abort(reason=self.translations("config.step.abort.already_configured", "The device is already configured in Home Assistant, and the information is now updated.")), None

            user_input["serial"] = serial
            entry = self.async_create_entry(title=name if name else "PiKVM", data=user_input)
            self.hass.async_create_task(self._register_device(entry, name, serial))

            return entry, None
        else:
            _LOGGER.error("Cannot connect to PiKVM device at %s", url)
            errors["base"] = "cannot_connect"
            return None, errors

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


    async def _register_device(self, entry, name, serial):
        """Register the device with the device registry."""
        device_registry = await dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=entry["entry_id"],
            identifiers={(DOMAIN, serial)},
            name=name if name else "PiKVM",
            manufacturer="PiKVM",
            model="PiKVM Model",
            sw_version="1.0",
            serial_number=serial
        )
        
    async def async_step_dhcp(self, discovery_info):
        """Handle the DHCP discovery step.  In this deivce, it is possible the PiKVM is not 
        ready for API requests when detected as KVMD takes a little while to come up. this DHCP
        config flow could be called on cable-reconnect or DHCP renewal which would be successful detection, or on reboot which may cause the device to be unrecognized due to 
        not yet being ready for API connection."""
        ip_address = discovery_info.ip

        _LOGGER.debug("Discovered device with IP %s", ip_address)

        url = format_url(ip_address)
        data = {
            CONF_URL: url,
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD,
            DHCP_CONFIG_FLAG: True
        }

        # Store the discovered URL in context to reuse it
        self.context['discovered_url'] = url

        # Attempt to handle the user input directly
        user_input = {
            CONF_URL: url,
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD
        }

        entry, errors = await handle_user_input(self, user_input)
        if entry:
            return entry

        # If the device is not operational yet, pass the data to the user step
        return await self.async_step_user(user_input=user_input)


    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        self.translations = await get_translations(self.hass, self.hass.config.language, DOMAIN)
        _LOGGER.debug("Entered async_step_user with data: %s", user_input)

        if user_input is not None:
            entry, errors = await handle_user_input(self, user_input)
            if entry:
                return entry

            # Keep the previously filled values
            default_url = user_input.get(CONF_URL, "")
            default_username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            default_password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
        else:
            # Initially, use the values passed from the DHCP step if present
            default_url = self.context.get('discovered_url', "")
            default_username = DEFAULT_USERNAME
            default_password = DEFAULT_PASSWORD

        data_schema = create_data_schema({
            CONF_URL: default_url,
            CONF_USERNAME: default_username,
            CONF_PASSWORD: default_password
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": self.translations("config.step.user.data.url", "URL or IP address of the PiKVM device"),
                "username": self.translations("config.step.user.data.username", "Username for PiKVM"),
                "password": self.translations("config.step.user.data.password", "Password for PiKVM")
            }
        )

