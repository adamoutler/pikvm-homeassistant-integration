"""Data update coordinator for the PiKVM integration."""
from datetime import timedelta
import logging
import requests
from requests.auth import HTTPBasicAuth
import functools

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD

_LOGGER = logging.getLogger(__name__)

def format_url(input_url):
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip('/')

class PiKVMDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the PiKVM API."""

    def __init__(self, hass: HomeAssistant, url: str, username: str, password: str):
        """Initialize."""
        self.hass = hass
        self.url = format_url(url)
        self.auth = HTTPBasicAuth(username, password)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self):
        """Fetch data from PiKVM API."""
        try:
            _LOGGER.debug("Fetching data from PiKVM API at %s", self.url)
            response = await self.hass.async_add_executor_job(
                functools.partial(
                    requests.get,
                    f"{self.url}/api/info",
                    auth=self.auth,
                    verify=False
                )
            )
            response.raise_for_status()
            data_info = response.json()["result"]

            _LOGGER.debug("Fetching data from PiKVM MSD API at %s", self.url)
            response_msd = await self.hass.async_add_executor_job(
                functools.partial(
                    requests.get,
                    f"{self.url}/api/msd",
                    auth=self.auth,
                    verify=False
                )
            )
            response_msd.raise_for_status()
            data_msd = response_msd.json()["result"]

            data_info["msd"] = data_msd
            _LOGGER.debug("Received data from PiKVM API: %s", data_info)
            return data_info
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Error communicating with API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}")
