"""Config flow for PiKVM integration."""
from homeassistant import config_entries, exceptions
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
import requests
from requests.auth import HTTPBasicAuth
import functools
import logging

from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD

MAC_FILTER_PREFIXES = [
    "e4:5f:01",
    "dc:a6:32"
]

_LOGGER = logging.getLogger(__name__)

async def is_pikvm_device(hass, ip, username, password):
    """Check if the device is a PiKVM."""
    url = f"{ip}/api/info"
    try:
        _LOGGER.debug("Checking PiKVM device at %s with username %s", url, username)
        response = await hass.async_add_executor_job(
            functools.partial(
                requests.get, url, auth=HTTPBasicAuth(username, password), verify=False
            )
        )
        _LOGGER.debug("Received response: %s", response.text)
        response.raise_for_status()
        data = response.json()
        _LOGGER.debug("Parsed response JSON: %s", data)
        return data.get("ok", False)
    except requests.exceptions.RequestException as err:
        _LOGGER.error("RequestException while checking PiKVM device: %s", err)
        return False
    except ValueError as err:
        _LOGGER.error("ValueError while parsing response JSON: %s", err)
        return False

class PiKVMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiKVM."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({
                vol.Required(CONF_URL): str,
                vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
            }))

        url = user_input[CONF_URL]
        username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
        password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)

        if await is_pikvm_device(self.hass, url, username, password):
            return self.async_create_entry(title="PiKVM", data=user_input)
        else:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_URL): str,
                    vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
                }),
                errors={"base": "cannot_connect"}
            )

    async def async_step_dhcp(self, discovery_info):
        """Handle the DHCP discovery step."""
        mac_address = discovery_info.macaddress
        ip_address = discovery_info.ip

        if any(mac_address.startswith(prefix) for prefix in MAC_FILTER_PREFIXES):
            url = f"https://{ip_address}"
            if await is_pikvm_device(self.hass, url, DEFAULT_USERNAME, DEFAULT_PASSWORD):
                return self.async_create_entry(
                    title="PiKVM",
                    data={
                        CONF_URL: url,
                        CONF_USERNAME: DEFAULT_USERNAME,
                        CONF_PASSWORD: DEFAULT_PASSWORD
                    }
                )
            else:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({
                        vol.Required(CONF_URL, default=url): str,
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): str,
                    }),
                    errors={"base": "cannot_connect"}
                )
        else:
            raise exceptions.AbortFlow("not_pikvm")

    async def async_step_import(self, user_input=None):
        """Handle the import step."""
        return await self.async_step_user(user_input)
