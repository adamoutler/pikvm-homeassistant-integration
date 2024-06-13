from datetime import timedelta
import logging
import requests
from requests.auth import HTTPBasicAuth
import functools
import os
import asyncio

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .cert_handler import create_session_with_cert  # Import the function

_LOGGER = logging.getLogger(__name__)

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')

class PiKVMDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the PiKVM API."""

    def __init__(self, hass: HomeAssistant, url: str, username: str, password: str, cert: str):
        """Initialize."""
        self.hass = hass
        self.url = format_url(url)
        self.auth = HTTPBasicAuth(username, password)
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
        self._create_session()

    def _create_session(self):
        """Create the session with the certificate."""
        self.session, self.cert_file_path = create_session_with_cert(self.cert)
        if not self.session:
            _LOGGER.error("Failed to create session with certificate")
        else:
            _LOGGER.debug("Session created successfully")

    async def _async_update_data(self):
        """Fetch data from PiKVM API."""
        max_retries = 5
        backoff_time = 2  # Initial backoff time in seconds
        retries = 0

        while retries < max_retries:
            try:
                _LOGGER.debug("Fetching PiKVM Info & MSD at %s", self.url)

                if not self.session:
                    self._create_session()

                response = await self.hass.async_add_executor_job(
                    functools.partial(
                        self.session.get,
                        f"{self.url}/api/info",
                        auth=self.auth,
                        timeout=10
                    )
                )

                response.raise_for_status()
                data_info = response.json()["result"]

                response_msd = await self.hass.async_add_executor_job(
                    functools.partial(
                        self.session.get,
                        f"{self.url}/api/msd",
                        auth=self.auth,
                        timeout=10
                    )
                )
                response_msd.raise_for_status()
                data_msd = response_msd.json()["result"]

                data_info["msd"] = data_msd
                _LOGGER.debug("Received PiKVM Info & MSD from %s",  self.url)

                return data_info
            except requests.exceptions.RequestException as err:
                retries += 1
                if retries < max_retries:
                    _LOGGER.warning("Error communicating with API: %s. Retrying in %s seconds...", err, backoff_time)
                    await asyncio.sleep(backoff_time)
                    backoff_time *= 2  # Exponential backoff
                else:
                    _LOGGER.error("Max retries exceeded. Error communicating with API: %s", err)
                    raise UpdateFailed(f"Error communicating with API: {err}")
            except Exception as e:
                _LOGGER.error("Unexpected error: %s", e)
                raise UpdateFailed(f"Unexpected error: {e}")
            finally:
                if self.cert_file_path and os.path.exists(self.cert_file_path):
                    os.remove(self.cert_file_path)

