"""Manages fetching data from the PiKVM API."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
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
from .utils import get_nested_value

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = 30

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

        scan_interval = DEFAULT_SCAN_INTERVAL
        if entry is not None:
            scan_interval = entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
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

    def _async_check_hardware_health(self, data: Any) -> None:
        """Monitor hardware undervoltage and throttling issues."""
        entry_id = self.config_entry.entry_id if self.config_entry else self.clean_host
        if not entry_id:
            return

        raw_data = getattr(data, "raw", None)
        if raw_data is None:
            raw_data = data if isinstance(data, dict) else {}

        throttling = get_nested_value(raw_data, ["hw", "health", "throttling"], {}) or {}
        raw_flags = get_nested_value(throttling, ["raw_flags"], 0) or 0
        text_flags = get_nested_value(throttling, ["text_flags"], []) or []
        voltage_core = get_nested_value(throttling, ["voltage", "core"], {}) or {}

        is_under_voltage_now = bool(
            voltage_core.get("now")
            or (isinstance(raw_flags, int) and (raw_flags & 0x1))
            or ("under-voltage" in text_flags)
        )
        is_under_voltage_past = bool(
            voltage_core.get("past")
            or (isinstance(raw_flags, int) and (raw_flags & 0x10000))
        )
        has_under_voltage = is_under_voltage_now or is_under_voltage_past

        is_throttled_now = bool(
            (isinstance(raw_flags, int) and (raw_flags & 0x6))
            or ("throttled" in text_flags)
            or ("arm-frequency-capped" in text_flags)
        )
        is_throttled_past = bool(
            isinstance(raw_flags, int) and (raw_flags & 0x60000)
        )
        has_throttling = is_throttled_now or is_throttled_past

        # Undervoltage Issue Management
        uv_issue_id = f"undervoltage_{entry_id}"
        if has_under_voltage:
            async_create_issue(
                self.hass,
                DOMAIN,
                uv_issue_id,
                is_fixable=False,
                is_persistent=False,
                severity=IssueSeverity.CRITICAL if is_under_voltage_now else IssueSeverity.WARNING,
                translation_key="undervoltage",
                translation_placeholders={"device_name": self.clean_host},
                learn_more_url="https://docs.pikvm.org/power/",
            )
        else:
            async_delete_issue(self.hass, DOMAIN, uv_issue_id)

        # Throttling Issue Management
        th_issue_id = f"throttling_{entry_id}"
        if has_throttling:
            async_create_issue(
                self.hass,
                DOMAIN,
                th_issue_id,
                is_fixable=False,
                is_persistent=False,
                severity=IssueSeverity.WARNING,
                translation_key="throttling",
                translation_placeholders={"device_name": self.clean_host},
                learn_more_url="https://docs.pikvm.org/",
            )
        else:
            async_delete_issue(self.hass, DOMAIN, th_issue_id)

    async def _async_update_data(self) -> PiKVMDeviceInfo:
        """Fetch data from PiKVM API."""
        try:
            _LOGGER.debug("Fetching PiKVM Info & MSD from %s", self.url)
            data = await self.client.get_info()
            self._async_check_hardware_health(data)
            return data
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
