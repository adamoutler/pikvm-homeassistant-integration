"""Global pytest fixtures for PiKVM integration tests."""

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations like this one for every test."""
    yield


@pytest.fixture(autouse=True, scope="session")
def mock_setup_entry_calls():
    """Avoid setting up the actual integration during config flow tests."""
    with (
        patch(
            "custom_components.pikvm_ha.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.pikvm_ha.async_unload_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        yield


@pytest.fixture
def pikvm_cert():
    """Return a synthetic PEM certificate used by the unit tests."""
    return (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBtjCCAVugAwIBAgIJAO2b2k93r7cKMAoGCCqGSM49BAMCMBUxEzARBgNVBAMM\n"
        "CnBpa3ZtLmxvY2FsMB4XDTIwMTAxMDEwMDAwMFoXDTMwMDkyNzEwMDAwMFowFTET\n"
        "MBEGA1UEAwwKcGlrdm0ubG9jYWwwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAATL\n"
        "7fUG9zO7g0ZmXGf1DsKpP+NBo7GdA51N2bYzu3n6PvJEa3TBUnIFVQGryuVKyXjH\n"
        "fS9Sz3gwxMZ2ymlkAkQHo1MwUTAdBgNVHQ4EFgQUYVtz1xuxMxDPZWS9Vyuk3F7S\n"
        "LCQwHwYDVR0jBBgwFoAUYVtz1xuxMxDPZWS9Vyuk3F7SLCQwDwYDVR0TAQH/BAUw\n"
        "AwEB/zAKBggqhkjOPQQDAgNJADBGAiEAi0eZZ+j9RnBbTK1ZBOqVakiobP6KyHRx\n"
        "0JVpaz6RtNkCIQCNux41DmvNmO6PsK0uFUxnCLzpSw0eVUsVTNff7kwhWA==\n"
        "-----END CERTIFICATE-----"
    )
