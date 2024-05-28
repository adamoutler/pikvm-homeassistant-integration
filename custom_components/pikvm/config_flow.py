"""Config flow for PiKVM integration."""
from homeassistant import config_entries, exceptions
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
import requests
from requests.auth import HTTPBasicAuth
import functools
import logging
import re
import asyncio
from scapy.all import ARP, Ether, srp  # Import scapy for ARP requests

from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD, DEFAULT_USERNAME, DEFAULT_PASSWORD, DHCP_MAC_FILTER_PREFIXES

_LOGGER = logging.getLogger(__name__)

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not re.match(r'^https?://', input_url):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')

async def is_pikvm_device(hass, url, username, password):
    """Check if the device is a PiKVM."""
    try:
        url = format_url(url)
        _LOGGER.debug("Checking PiKVM device at %s with username %s", url, username)
        response = await hass.async_add_executor_job(
            functools.partial(
                requests.get, f"{url}/api/info", auth=HTTPBasicAuth(username, password), verify=False
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

def get_mac_address(ip_address):
    """Get the MAC address for a given IP address."""
    try:
        # Create an ARP request packet
        arp_request = ARP(pdst=ip_address)
        broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
        arp_request_broadcast = broadcast / arp_request

        # Send the ARP request and get the response
        answered_list = srp(arp_request_broadcast, timeout=1, verbose=False)[0]

        # Extract the MAC address from the response
        return answered_list[0][1].hwsrc if answered_list else None
    except Exception as e:
        _LOGGER.error("Error obtaining MAC address for IP %s: %s", ip_address, e)
        return None

class PiKVMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiKVM."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        self._discovered_mac = None
        self._discovered_ip = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            url = format_url(user_input[CONF_URL])
            user_input[CONF_URL] = url

            username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
            password = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)

            _LOGGER.debug("Manual setup with URL %s, username %s", url, username)

            if await is_pikvm_device(self.hass, url, username, password):
                _LOGGER.debug("PiKVM device successfully found at %s", url)

                # Obtain MAC address from IP address
                ip_address = re.sub(r'^https?://', '', url)
                mac_address = await self.hass.async_add_executor_job(get_mac_address, ip_address)
                if mac_address:
                    self._discovered_mac = mac_address.lower()
                    user_input["mac_address"] = self._discovered_mac

                # Check if device with the same MAC already exists
                existing_entry = await self._async_find_existing_entry(self._discovered_mac)
                if existing_entry:
                    self.hass.config_entries.async_update_entry(existing_entry, data=user_input)
                    return self.async_abort(reason="already_configured")

                return self.async_create_entry(title="PiKVM", data=user_input)
            else:
                _LOGGER.error("Cannot connect to PiKVM device at %s", url)
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required(CONF_URL): str,
            vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
            vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": "URL or IP address of the PiKVM device",
                "username": "Username for PiKVM",
                "password": "Password for PiKVM"
            }
        )

    async def async_step_dhcp(self, discovery_info):
        """Handle the DHCP discovery step."""
        mac_address = discovery_info.macaddress.lower()
        ip_address = discovery_info.ip

        _LOGGER.debug("Discovered device with MAC %s and IP %s", mac_address, ip_address)

        # Log each MAC address prefix check
        for prefix in DHCP_MAC_FILTER_PREFIXES:
            _LOGGER.debug("Checking if MAC address %s starts with %s", mac_address, prefix)

        if any(mac_address.startswith(prefix) for prefix in DHCP_MAC_FILTER_PREFIXES):
            self._discovered_mac = mac_address
            self._discovered_ip = ip_address

            # Adding a delay to allow the device to come online
            await asyncio.sleep(10)  # 10 second delay, adjust as needed

            url = format_url(ip_address)
            _LOGGER.debug("Device MAC matches filter, checking PiKVM at %s", url)

            if await is_pikvm_device(self.hass, url, DEFAULT_USERNAME, DEFAULT_PASSWORD):
                _LOGGER.debug("PiKVM device found at %s", url)
                data = {
                    CONF_URL: url,
                    CONF_USERNAME: DEFAULT_USERNAME,
                    CONF_PASSWORD: DEFAULT_PASSWORD,
                    "mac_address": mac_address
                }

                # Set unique ID to avoid conflicts
                await self.async_set_unique_id(mac_address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="PiKVM",
                    data=data
                )
            else:
                _LOGGER.debug("PiKVM device not found at %s, showing form to user", url)
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({
                        vol.Required(CONF_URL, default=url): str,
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): str,
                    }),
                    description_placeholders={
                        "url": "config.step.user.data.url",
                        "username": "config.step.user.data.username",
                        "password": "config.step.user.data.password"
                    },
                    errors={"base": "cannot_connect"}
                )
        else:
            _LOGGER.debug("Device MAC %s does not match filter", mac_address)
            raise exceptions.AbortFlow("not_pikvm")

    async def _async_find_existing_entry(self, mac_address):
        """Find existing entry with the same MAC address."""
        for entry in self._async_current_entries():
            if entry.data.get("mac_address") == mac_address:
                return entry
        return None

    async def async_step_import(self, user_input=None):
        """Handle the import step."""
        return await self.async_step_user(user_input)
