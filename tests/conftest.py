import pytest

# Pre-initialize pycares channel daemon thread so pytest_homeassistant_custom_component's
# verify_cleanup fixture doesn't flag the background thread as a leak during test execution.
try:
    import pycares
    _channel = pycares.Channel()
except Exception:
    pass

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations like this one for every test."""
    yield


@pytest.fixture
def pikvm_cert():
    """Return a synthetic PEM certificate used by the unit tests."""
    return (
        "-----BEGIN CERTIFICATE-----\n"
        "MIICuDCCAaCgAwIBAgIUIL17u2WG/dGmmsdQwDwsd7lJueswDQYJKoZIhvcNAQEL\n"
        "BQAwFjEUMBIGA1UEAwwLcGlrdm0ubG9jYWwwHhcNMjYwOTI4MTY1MjM1WhcNMjcw\n"
        "OTI4MTY1MjM1WjAWMRQwEgYDVQQDDAtwaWt2bS5sb2NhbDCCASIwDQYJKoZIhvcN\n"
        "AQEBBQADggEPADCCAQoCggEBANJHnc54/gVYq9d2wtbk1RDr1aHz5Fk5fT7IvjH/\n"
        "l64z3LtfbfhxTHAVY6rEkPb+R4l4hsrDXSOWCklX+BoSZ2XNuMKmq15IMebUKiNq\n"
        "ib7QXP/lPkExd8Jtu2x3d0K6hwXDc34Gtqyn2hOMpqqxyLKyjRkQClcN8vkNx3ky\n"
        "UllL87b/NWiVxeTM8XT8YgsaDiwd9qutnXgihy5U9zt+xVcowunVVgRQxxvKsGeI\n"
        "r9rNqjd8mhsvBshsFob69G7GyAic1f1WzqPkJgOYRMzZU8lNsBY7TtDxangcz36x\n"
        "r1A/hQwebB5vxG1bAfYxBhrtVM45FaRe4OP5tpLCrQdzO+UCAwEAATANBgkqhkiG\n"
        "9w0BAQsFAAOCAQEAdZz+nIk3di5fH1GqVW3Xo6Gg237RvapusxRKC1QM/i4C9sUo\n"
        "qOS3Bg+aAAJhzFAy6jUB8/YfBPuOXiAU5Wr9uC31EQtKgvcAxi1wHMEeyhNgPFOP\n"
        "evs7U18h/7iDGr+HGKV8TbYi5SBoE6tynD3BoJk8gHi4ewdCRyex6lQjwwvz4ele\n"
        "dpaQzZuVNMGjwA+CHaUJG8E65QYy9FTrXfPb+qQVi4LEvd5QAIiz4/hLNtBA9sR7\n"
        "lu5MKTmbsWq2aDtynlOfZAaWWwsWYXgv4nPCZOu2kTQ/S5ZkTEXJwIO1TteUVl1s\n"
        "f4Pl8vbKm9EBJKNGZJgUyE6AkfRlOHVGChlLzg==\n"
        "-----END CERTIFICATE-----"
    )
