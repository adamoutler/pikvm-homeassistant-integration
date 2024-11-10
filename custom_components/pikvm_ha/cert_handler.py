"""Handle certificate-related operations for PiKVM integration."""

import functools
import logging
import os
import socket
import ssl
import tempfile
from typing import NamedTuple
import warnings

import OpenSSL
import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning

from homeassistant.core import HomeAssistant

warnings.simplefilter("ignore", InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)


class SSLContextAdapter(HTTPAdapter):
    """An HTTP adapter that uses a custom SSL context."""

    def __init__(self, ssl_context, *args, **kwargs) -> None:
        """Initialize the adapter with the custom SSL context. This method is called by the session."""
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs) -> None:
        """Initialize the pool manager with the custom SSL context. This method is called by the session."""
        kwargs["ssl_context"] = self.ssl_context
        super().init_poolmanager(*args, **kwargs)

    def cert_verify(self, conn, *args, **kwargs) -> None:
        """Disable certificate verification. This method is called by the pool manager."""
        conn.assert_hostname = False
        conn.cert_reqs = ssl.CERT_NONE


async def create_session_with_cert(
    hass: HomeAssistant | None, serialized_cert=None
) -> tuple:
    """Create a session with a custom SSL context using the provided certificate.

    Args:
        hass (HomeAssistant | None): The HomeAssistant instance.
        serialized_cert (str, optional): The serialized certificate in PEM format.

    Returns:
        tuple: A tuple containing the session and the certificate file path.

    """
    cert_file_path = None
    try:
        session = requests.Session()

        # Create an SSL context that disables all verifications
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False  # Disable hostname verification
        context.verify_mode = ssl.CERT_NONE  # Disable certificate verification

        if serialized_cert:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_file:
                cert_file.write(serialized_cert.encode("utf-8"))
                cert_file_path = cert_file.name
            if hass is not None:
                await hass.async_add_executor_job(
                    context.load_verify_locations, cert_file_path
                )
            else:
                context.load_verify_locations(cert_file_path)

        adapter = SSLContextAdapter(context)
        session.mount("https://", adapter)

        _LOGGER.debug("Created session with custom SSL context using the certificate")
        if serialized_cert:
            return session, cert_file_path
        return session, None  # noqa: TRY300
    except (OSError, ssl.SSLError, OpenSSL.crypto.Error) as e:
        _LOGGER.error("Error creating session with certificate: %s", e)
        return None, None


async def fetch_serialized_cert(hass: HomeAssistant, url: str) -> str:
    """Fetch and serialize the certificate."""
    return await hass.async_add_executor_job(_fetch_and_serialize_cert, url)


def _fetch_and_serialize_cert(url) -> str:
    """Fetch the certificate from the given URL and serializes it.

    Args:
        url (str): The URL from which to fetch the certificate.

    Returns:
        str: The serialized certificate in PEM format, or None if an error occurred.

    Raises:
        Exception: If there was an error fetching or serializing the certificate.

    """
    try:
        hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
        port = 443

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        conn = context.wrap_socket(
            socket.socket(socket.AF_INET), server_hostname=hostname
        )
        conn.connect((hostname, port))

        # Get the certificate
        cert = conn.getpeercert(True)
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_ASN1, cert)

        # Serialize the certificate
        serialized_cert = OpenSSL.crypto.dump_certificate(
            OpenSSL.crypto.FILETYPE_PEM, x509
        ).decode("utf-8")
        conn.close()
        return serialized_cert  # noqa: TRY300

    except (OSError, ssl.SSLError, OpenSSL.crypto.Error) as e:
        _LOGGER.error("Error fetching or serializing certificate from %s: %s", url, e)
        if "conn" in locals() and conn:
            conn.close()
        return None


def format_url(input_url) -> str:
    """Ensure the URL is properly formatted."""
    if not input_url.startswith("http"):
        input_url = f"https://{input_url}"
    return input_url.rstrip("/")


class PiKVMResponse(NamedTuple):
    """A named tuple to store the response from a PiKVM device check."""

    success: bool
    model: str | None
    serial: str | None
    name: str | None
    error: str | None


async def is_pikvm_device(
    hass: HomeAssistant | None, url: str, username: str, password: str, cert: str
) -> PiKVMResponse:
    """Check if the device is a PiKVM and return its serial number."""
    url = format_url(url)
    _LOGGER.debug("Checking PiKVM device at %s with username %s", url, username)

    try:
        session, cert_file_path = await hass.async_add_executor_job(
            create_session_with_cert, cert
        )
        if not session:
            _LOGGER.error("Failed to create session")
            return PiKVMResponse(False, None, None, None)

        response = await hass.async_add_executor_job(
            functools.partial(
                session.get, f"{url}/api/info", auth=HTTPBasicAuth(username, password)
            )
        )

        # Log the status code immediately after getting the response
        _LOGGER.debug("Received response status code: %s", response.status_code)

        # Store the status code before raise_for_status potentially raises an exception
        status_code = response.status_code

        # Raise an exception for HTTP error codes (like 403)
        response.raise_for_status()

        data = response.json()
        _LOGGER.debug("Parsed response JSON: %s", data)

        if data.get("ok", False):
            serial = (
                data.get("result", {})
                .get("hw", {})
                .get("platform", {})
                .get("serial", None)
            )
            model = (
                data.get("result", {})
                .get("hw", {})
                .get("platform", {})
                .get("model", None)
            )
            name = (
                data.get("result", {})
                .get("meta", {})
                .get("server", {})
                .get("host", None)
            )

            _LOGGER.debug("Extracted serial number: %s", serial)
            return PiKVMResponse(True, model, serial, name, None)

        _LOGGER.error("Device check failed: 'ok' key not present or false")
        return PiKVMResponse(False, None, None, None, "GenericException")

    except requests.exceptions.HTTPError as err:
        # Use the previously stored status_code
        error_code = f"Exception_HTTP{status_code}"
        _LOGGER.error("HTTPError while checking PiKVM device at %s: %s", url, err)
        return PiKVMResponse(False, None, None, None, error_code)

    except requests.exceptions.RequestException as err:
        _LOGGER.error(
            "RequestException while checking PiKVM device at %s: %s", url, err
        )
        return PiKVMResponse(False, None, None, None, "Exception_Request")

    except ValueError as err:
        _LOGGER.error("ValueError while parsing response JSON from %s: %s", url, err)
        return PiKVMResponse(False, None, None, None, "Exception_JSON")

    finally:
        if cert_file_path and os.path.exists(cert_file_path):
            try:
                os.remove(cert_file_path)
                _LOGGER.debug("Temporary certificate file removed: %s", cert_file_path)
            except OSError as e:
                _LOGGER.warning("Failed to remove temporary certificate file: %s", e)
