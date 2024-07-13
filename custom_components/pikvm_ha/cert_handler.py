#192.168.1.105 = standard PiKVM self-signed cert
#192.168.1.2 = tls 1.3 compatible
#192.168.1.108 = self-signed Certificate authority
import socket
import ssl
import OpenSSL
import logging
import requests
import tempfile
import warnings
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
import functools
import os
from urllib3.poolmanager import PoolManager
from urllib3.exceptions import InsecureRequestWarning

warnings.simplefilter('ignore', InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)

class SSLContextAdapter(HTTPAdapter):
    def __init__(self, ssl_context, *args, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        super().init_poolmanager(*args, **kwargs)

    def cert_verify(self, conn, *args, **kwargs):
        conn.assert_hostname = False
        conn.cert_reqs = ssl.CERT_NONE

def create_session_with_cert(serialized_cert=None):
    try:
        session = requests.Session()

        # Create an SSL context that disables all verifications
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False  # Disable hostname verification
        context.verify_mode = ssl.CERT_NONE  # Disable certificate verification

        if serialized_cert:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_file:
                cert_file.write(serialized_cert.encode('utf-8'))
                cert_file_path = cert_file.name
            context.load_verify_locations(cert_file_path)

        adapter = SSLContextAdapter(context)
        session.mount('https://', adapter)

        _LOGGER.debug("Created session with custom SSL context using the certificate.")
        return session, cert_file_path if serialized_cert else None
    except Exception as e:
        _LOGGER.error("Error creating session with certificate: %s", e)
        return None, None

async def fetch_serialized_cert(hass, url):
    """Fetch and serialize the certificate."""
    return await hass.async_add_executor_job(_fetch_and_serialize_cert, url)

def _fetch_and_serialize_cert(url):
    """
    Fetches the certificate from the given URL and serializes it.

    Args:
        url (str): The URL from which to fetch the certificate.

    Returns:
        str: The serialized certificate in PEM format, or None if an error occurred.

    Raises:
        Exception: If there was an error fetching or serializing the certificate.
    """
    try:
        hostname = url.replace('https://', '').replace('http://', '').split('/')[0]
        port = 443

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        conn = context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=hostname)
        conn.connect((hostname, port))

        # Get the certificate
        cert = conn.getpeercert(True)
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_ASN1, cert)

        # Serialize the certificate
        serialized_cert = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, x509).decode('utf-8')
        conn.close()
        return serialized_cert

    except Exception as e:
        _LOGGER.error("Error fetching or serializing certificate from %s: %s", url, e)
        if 'conn' in locals() and conn:
            conn.close()
        return None

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
        if not session:
            return False, None

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
            name = data.get("result", {}).get("meta", {}).get("server", {}).get("host")
            _LOGGER.debug("Extracted serial number: %s", serial)
            return True, serial, name
        return False, None, "GenericException"
    except requests.exceptions.RequestException as err:
        _LOGGER.error("RequestException while checking PiKVM device at %s: %s", url, err)
        return False, None, "Exception_HTTP" + str(err.response.status_code)
    except ValueError as err:
        _LOGGER.error("ValueError while parsing response JSON from %s: %s", url, err)
        return False, None, "Exception_JSON"
    finally:
        if cert_file_path and os.path.exists(cert_file_path):
            os.remove(cert_file_path)
