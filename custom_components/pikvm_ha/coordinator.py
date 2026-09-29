"""Manages fetching data from the PiKVM API."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMClient,
    PiKVMConnectionError,
    PiKVMDeviceError,
    PiKVMDeviceInfo,
    PiKVMError,
    PiKVMTimeoutError,
    format_url,
    parse_host_port,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.util.ssl import get_default_no_verify_context

    _DEFAULT_NO_VERIFY_SSL_CONTEXT = get_default_no_verify_context()
except Exception:  # noqa: BLE001
    _DEFAULT_NO_VERIFY_SSL_CONTEXT = None


class PiKVMDataUpdateCoordinator(DataUpdateCoordinator[PiKVMDeviceInfo]):
    """Class to manage fetching data from the PiKVM API asynchronously."""

    url: str = ""
    device_info: DeviceInfo | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        username: str,
        password: str,
        totp: str,
        cert: str,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.url = format_url(url)
        self.username = username
        self.password = password
        self.totp = totp
        self.cert = cert
        self.device_info = None

        try:
            self.clean_host = parse_host_port(self.url)[0]
        except Exception:
            self.clean_host = self.url.replace("https://", "").replace("http://", "").split("/")[0]

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
            config_entry=entry,
        )

        self.client = PiKVMClient(
            host=self.url,
            username=self.username,
            password=self.password,
            totp_secret=self.totp if self.totp else None,
            session=async_get_clientsession(hass),
            ssl_cert=self.cert if self.cert else None,
            verify_ssl=False,
            check_hostname=False,
            ssl_context=_DEFAULT_NO_VERIFY_SSL_CONTEXT,
        )

    async def async_setup(self) -> None:
        """Async setup method (retained for lifecycle compatibility)."""

    async def _async_update_data(self) -> PiKVMDeviceInfo:
        """Fetch data from PiKVM API."""
        try:
            _LOGGER.debug("Fetching PiKVM Info & MSD from %s", self.url)
            return await self.client.get_info()
        except PiKVMAuthenticationError as auth_err:
            _LOGGER.error("Authentication failed for PiKVM at %s: %s", self.url, auth_err)
            raise ConfigEntryAuthFailed("Invalid credentials or 2FA TOTP token required") from auth_err
        except PiKVMTimeoutError as err:
            _LOGGER.debug("Timeout connecting to PiKVM at %s: %s", self.url, err)
            raise UpdateFailed(f"Connection timed out reaching {self.clean_host}") from err
        except PiKVMConnectionError as err:
            _LOGGER.debug("Connection error to PiKVM at %s: %s", self.url, err)
            raise UpdateFailed(f"Cannot connect to {self.clean_host} (host offline or connection refused)") from err
        except (PiKVMDeviceError, PiKVMError) as err:
            _LOGGER.debug("Error communicating with PiKVM API at %s: %s", self.url, err)
            raise UpdateFailed(f"Error communicating with PiKVM at {self.clean_host}: {err}") from err
