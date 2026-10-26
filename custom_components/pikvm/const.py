"""Constants for the PiKVM integration."""

from typing import Final

DOMAIN: Final = "pikvm"
LEGACY_DOMAIN: Final = "pikvm_ha"
CONF_MODEL: Final = "model"
CONF_HOST: Final = "url"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_TOTP: Final = "totp"
CONF_CERTIFICATE: Final = "tls-certificate"
CONF_SERIAL: Final = "serial"
DEFAULT_USERNAME: Final = "admin"
DEFAULT_PASSWORD: Final = "admin"
MANUFACTURER: Final = "PiKVM"

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

