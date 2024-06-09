import ssl
import socket
import OpenSSL
import logging
import tempfile
import requests

_LOGGER = logging.getLogger(__name__)

def fetch_and_serialize_cert(url):
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

        # Extract the issuer
        issuer = x509.get_issuer().get_components()
        issuer_dict = {x[0].decode(): x[1].decode() for x in issuer}
        issuer_str = ', '.join([f'{k}={v}' for k, v in issuer_dict.items()])

        # Extract subject
        subject = x509.get_subject().get_components()
        subject_dict = {x[0].decode(): x[1].decode() for x in subject}
        subject_str = ', '.join([f'{k}={v}' for k, v in subject_dict.items()])

        # Log the certificate details
        _LOGGER.debug("Fetched certificate from %s", url)
        _LOGGER.debug("Certificate issuer: %s", issuer_str)
        _LOGGER.debug("Certificate subject: %s", subject_str)

        # Serialize the certificate
        serialized_cert = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, x509).decode('utf-8')
        conn.close()
        return serialized_cert

    except Exception as e:
        _LOGGER.error("Error fetching or serializing certificate from %s: %s", url, e)
        return None

import requests
import ssl
import tempfile

def create_session_with_cert(serialized_cert):
    """
    Create a requests session using the provided certificate.

    Args:
        serialized_cert (str): The serialized certificate.

    Returns:
        tuple: A tuple containing the created session and the path to the certificate file.
               If an error occurs, returns None for both values.
    """
    try:
        session = requests.Session()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_file:
            cert_file.write(serialized_cert.encode('utf-8'))
            cert_file_path = cert_file.name

        class SSLContextAdapter(requests.adapters.HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.load_verify_locations(cert_file_path)
                kwargs['ssl_context'] = context
                return super().init_poolmanager(*args, **kwargs)

            def init_connection(self, *args, **kwargs):
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.load_verify_locations(cert_file_path)
                kwargs['ssl_context'] = context
                return super().init_connection(*args, **kwargs)

        session.mount('https://', SSLContextAdapter())
        _LOGGER.debug("Created session with custom SSL context using the certificate.")
        return session, cert_file_path
    except Exception as e:
        _LOGGER.error("Error creating session with certificate: %s", e)
        return None, None
