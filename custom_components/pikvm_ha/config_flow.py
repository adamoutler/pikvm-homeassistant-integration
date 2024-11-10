"""Config flow for PiKVM integration."""

import logging

from homeassistant import config_entries
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.core import callback

from .cert_handler import fetch_serialized_cert, is_pikvm_device
from .const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
    MANUFACTURER,
)
from .options_flow import PiKVMOptionsFlowHandler
from .utils import (
    create_data_schema,
    find_existing_entry,
    get_translations,
    update_existing_entry,
)

_LOGGER = logging.getLogger(__name__)


async def perform_device_setup(flow_handler, user_input):
    """Handle initial configuration setup for the configuration."""
    errors = {}
    host = user_input[CONF_HOST]
    username = user_input[CONF_USERNAME]
    password = user_input[CONF_PASSWORD]

    _LOGGER.debug(
        "Entered perform_device_setup with URL %s, username %s", host, username
    )

    try:
        # Fetch the certificate
        serialized_cert = await fetch_serialized_cert(flow_handler.hass, host)
        if not serialized_cert:
            errors["base"] = "cannot_fetch_cert"
            return None, errors

        # Store the certificate
        user_input[CONF_CERTIFICATE] = serialized_cert

        # Connect and obtain unique data from the device
        response = await is_pikvm_device(
            flow_handler.hass, host, username, password, serialized_cert
        )

        if response.error:
            errors["base"] = response.error
            return None, errors

        if not response.success:
            _LOGGER.error(
                "Error detected while connecting to PiKVM device. Error: %s",
                response.error,
            )
            # Handle the error based on response.name_or_error
            errors["base"] = "cannot_connect"
            return None, errors

        _LOGGER.debug(
            "PiKVM device detected: Model=%s, Serial=%s, Name=%s",
            response.model,
            response.serial,
            response.name,
        )

        # If an HTTP/other error occurred, then we receive a special message in the name.
        # If the user has named the device we will use it, otherwise the default will be "pikvm"
        if response.name == "localhost.localdomain":
            response.name = MANUFACTURER

        # Check if the device is already configured now that we obtained serial number
        existing_entry = find_existing_entry(flow_handler, response.serial)
        if existing_entry:
            update_existing_entry(
                flow_handler.hass,
                existing_entry,
                {CONF_HOST: host, CONF_USERNAME: username, CONF_PASSWORD: password},
            )
            return flow_handler.async_abort(reason="already_configured"), None

        # Set the unique ID based on the serial number
        user_input["serial"] = response.serial
        user_input["model"] = response.model
        await flow_handler.async_set_unique_id(response.serial)

        # Finish config
        config_flow_result = flow_handler.async_create_entry(
            title=response.name if response.name else "PiKVM", data=user_input
        )
        return config_flow_result, None  # noqa: TRY300

    except (ConnectionError, TimeoutError, ValueError) as e:
        _LOGGER.error("Unexpected error during device setup: %s", e)
        errors["base"] = "unknown_error"

    return None, errors


class PiKVMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiKVM."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """Initialize the PiKVMConfigFlow."""
        self._errors: dict[str, str] = {}
        self.translations = None
        self._discovery_info: dict[str, str] = {}

    async def async_step_import(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle import."""
        return await self.async_step_user(user_input=user_input)

    # lets filter out the zeroconf discovery of ipv6 addresses
    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> config_entries.ConfigFlowResult:
        """Handle the ZeroConf discovery step."""
        serial = discovery_info.properties.get("serial")
        host = discovery_info.host
        if not serial or not host:
            _LOGGER.debug("Discovered device with ZeroConf but missing serial or host")
            return self.async_abort(reason="missing_serial_or_host")
        # Filter out IPv6 addresses
        if host.find(":") != -1:
            _LOGGER.debug("Discovered device with ZeroConf but IPv6 address")
            return self.async_abort(reason="ipv6_address")
        _LOGGER.debug(
            "Discovered device with ZeroConf: host=%s, serial=%s, model=%s",
            host,
            serial,
            discovery_info.properties.get("model"),
        )
        existing_entry = find_existing_entry(self, serial)
        if existing_entry:
            _LOGGER.debug(
                "Device with serial %s already configured, updating existing entry",
                serial,
            )
            existing_username = existing_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
            existing_password = existing_entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)
            _LOGGER.debug(
                "Updating existing entry with host=%s, username=%s, password=%s",
                host,
                existing_username,
                existing_password,
            )
            update_existing_entry(
                self.hass,
                existing_entry,
                {
                    CONF_HOST: host,
                    CONF_USERNAME: existing_username,
                    CONF_PASSWORD: existing_password,
                    "serial": serial,  # Ensure serial is included
                },
            )
            return self.async_abort(reason="already_configured")
        # Offer options to add or ignore
        self._discovery_info = {
            CONF_HOST: host,
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD,
            "serial": serial,
        }
        return await self._show_zeroconf_menu()

    async def _show_zeroconf_menu(self):
        """Show menu for ZeroConf discovered device."""
        return self.async_show_menu(
            step_id="zeroconf_confirm", menu_options=["add_device", "ignore"]
        )

    async def async_step_zeroconf_confirm(
        self, user_input
    ) -> config_entries.ConfigFlowResult:
        """Handle confirmation to add or ignore the ZeroConf device."""
        if user_input == "ignore":
            _LOGGER.debug(
                "Ignoring discovered device with serial %s",
                self._discovery_info["serial"],
            )
            return self.async_abort(reason="ignored")

        # Proceed with adding the device
        entry, errors = await perform_device_setup(self, self._discovery_info)
        if entry:
            return entry

        self._errors = errors
        return await self.async_step_user(user_input=self._discovery_info)

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors = self._errors
        self._errors = {}  # Reset errors after using them

        self.translations = (
            await get_translations(self.hass, self.hass.config.language, DOMAIN) or {}
        )

        if user_input is not None:
            _LOGGER.debug(
                "Entered async_step_user with data: host=%s, username=%s, password=%s",
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD].replace("*", "*"),
            )
            entry, setup_errors = await perform_device_setup(self, user_input)
            if setup_errors:
                errors.update(setup_errors)
            if entry:
                return entry

        if user_input is None:
            _LOGGER.debug("Entered async_step_user with data: None")
            user_input = self._discovery_info or {
                CONF_HOST: "",
                CONF_USERNAME: DEFAULT_USERNAME,
                CONF_PASSWORD: DEFAULT_PASSWORD,
            }
            if self._discovery_info:
                user_input[CONF_PASSWORD] = ""

        data_schema = create_data_schema(user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "url": self.translations(
                    "step.user.data.url", "URL or IP address of the PiKVM device"
                )
                if self.translations
                else "URL or IP address of the PiKVM device",
                "username": self.translations(
                    "step.user.data.username", "Username for PiKVM"
                ),
                "password": self.translations(
                    "step.user.data.password", "Password for PiKVM"
                ),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return PiKVMOptionsFlowHandler(config_entry)
