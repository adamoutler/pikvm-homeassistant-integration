"""Config flow for PiKVM integration."""
from homeassistant import config_entries, exceptions
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
import requests
from requests.auth import HTTPBasicAuth
import functools
import logging
import os
import asyncio
from .cert_handler import fetch_and_serialize_cert, create_session_with_cert
from homeassistant.helpers import device_registry as dr

from .const import DHCP_CONFIG_FLAG, DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD, CONF_CERTIFICATE

_LOGGER = logging.getLogger(__name__)

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')

async def is_pikvm_device(hass, url, username, password, cert):
    """Check if the device is a PiKVM and return its serial number."""
    try:
        url = format_url(url)
        _LOGGER.debug("Checking PiKVM device at %s with username %s", url, username)

        session, cert_file_path = await hass.async_add_executor_job(create_session_with_cert, cert)
        response = await hass.async_add_executor_job(
            functools.partial(
                session.get, f"{url}/api/info", auth=HTTPBasicAuth(username, password)
            )
        )

        _LOGGER.debug("Received response status code: %s", response.status_code)
        response.raise_for_status()
        data = response.json()
        _LOGGER.debug("Parsed response JSON: %s", data)

        if data.get("ok", False):
            serial = data.get("result", {}).get("hw", {}).get("platform", {}).get("serial")
            _LOGGER.debug("Extracted serial number: %s", serial)
            return True, serial
        return False, None
    except requests.exceptions.RequestException as err:
        _LOGGER.error("RequestException while checking PiKVM device at %s: %s", url, err)
        return False, None
    except ValueError as err:
        _LOGGER.error("ValueError while parsing response JSON from %s: %s", url, err)
        return False, None
    finally:
        if cert_file_path and os.path.exists(cert_file_path):
            os.remove(cert_file_path)

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

        if user_input is not None and DHCP_CONFIG_FLAG in user_input:
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

        if user_input is not None and DHCP_CONFIG_FLAG in user_input:
            data_schema = vol.Schema({
                vol.Required(CONF_URL, default=user_input[CONF_URL]): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
            })
        else:
            data_schema = vol.Schema({
                vol.Required(CONF_URL): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
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