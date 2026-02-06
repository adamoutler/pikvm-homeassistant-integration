"""Manages fetching data from the PiKVM API."""

import asyncio
from datetime import timedelta
import functools
import logging
import os
import pyotp

import requests
from requests.auth import HTTPBasicAuth

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cert_handler import create_session_with_cert  # Import the function
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip("/")


class AuthenticationFailed(Exception):
    """Custom exception for authentication failures."""


class PiKVMDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the PiKVM API."""

    url: str = ""

    def __init__(
        self, hass: HomeAssistant, url: str, username: str, password: str, totp: str, cert: str
    ) -> None:
        """Initialize."""
        self.hass = hass
        self.url = format_url(url)
        self.username = username
        self.password = password
        if len(totp) > 0:
            self.totp = pyotp.TOTP(totp)
        self.cert = cert
        self.session = None
        self.cert_file_path = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        # Create the session initially
        
    def get_auth(self):
        auth = HTTPBasicAuth(self.username, self.password)
        if self.totp:
            auth.password += self.totp.now()
        
        return auth

    async def async_setup(self) -> None:
        """Async setup method to create session and handle async code."""
        # Create the session asynchronously
        await self._create_session()

    async def _create_session(self):
        """Create the session with the certificate."""
        # self.auth is already defined in __init__
        self.auth = HTTPBasicAuth(self.username, self.password)
        session_with_cert = await create_session_with_cert(self.cert)
        self.session, self.cert_file_path = session_with_cert
        if not self.session:
            _LOGGER.debug("Failed to create session with certificate")
        else:
            _LOGGER.debug("Session created successfully")

    async def _async_update_data(self):
        """Fetch data from PiKVM API."""
        max_retries = 5
        backoff_time = 2  # Initial backoff time in seconds
        retries = 0

        while retries < max_retries:
            try:
                auth = self.get_auth()
                _LOGGER.debug("Fetching PiKVM Info & MSD at %s", self.url)

                if not self.session:
                    self._create_session()

                response = await self.hass.async_add_executor_job(
                    functools.partial(
                        self.session.get,
                        f"{self.url}/api/info",
                        auth=auth,
                        timeout=10,
                    )
                )

                if response.status_code == 401:
                    raise AuthenticationFailed("Invalid username or password")  # noqa: TRY301

                response.raise_for_status()
                data_info = response.json().get("result")

                response_msd = await self.hass.async_add_executor_job(
                    functools.partial(
                        self.session.get,
                        f"{self.url}/api/msd",
                        auth=auth,
                        timeout=10,
                    )
                )
                response_msd.raise_for_status()
                data_msd = response_msd.json().get("result")

                if data_info is None:
                    raise UpdateFailed("API response missing 'result' for info")

                data_info["msd"] = data_msd
                _LOGGER.debug("Received PiKVM Info & MSD from %s", self.url)

                return data_info  # noqa: TRY300
            except AuthenticationFailed as auth_err:
                _LOGGER.error("Authentication failed: %s", auth_err)
                raise UpdateFailed(f"Authentication failed: {auth_err}") from auth_err
            except requests.exceptions.RequestException as err:
                retries += 1
                if retries < max_retries:
                    _LOGGER.debug(
                        "Error communicating with API: %s. Retrying in %s seconds",
                        err,
                        backoff_time,
                    )
                    await asyncio.sleep(backoff_time)
                    backoff_time *= 2  # Exponential backoff
                else:
                    _LOGGER.debug(
                        "Max retries exceeded. Error communicating with API: %s", err
                    )
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
            except (ValueError, KeyError) as e:
                _LOGGER.error("Data processing error: %s", e)
                raise UpdateFailed(f"Data processing error: {e}") from e
            finally:
                if self.cert_file_path and os.path.exists(self.cert_file_path):
                    os.remove(self.cert_file_path)
        return None
