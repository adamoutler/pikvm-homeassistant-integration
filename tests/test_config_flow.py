"""Tests for the PiKVM config flow."""

from ipaddress import IPv4Address, IPv6Address
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm import config_flow
from custom_components.pikvm.cert_handler import PiKVMResponse
from custom_components.pikvm.config_flow import (
    PiKVMConfigFlow,
    perform_device_setup,
)
from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
    MANUFACTURER,
)
from custom_components.pikvm.options_flow import PiKVMOptionsFlowHandler


@pytest.fixture(autouse=True)
def bypass_setup_entry():
    """Bypass entry setup during config flow tests."""
    with patch(
        "custom_components.pikvm.async_setup_entry",
        return_value=True,
    ):
        yield


@pytest.mark.asyncio
async def test_config_flow_user_success(hass, pikvm_cert):
    """Test a full successful user initiated config flow."""
    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }

    response = PiKVMResponse(True, "v3", "pikvm-1234", "My PiKVM", None)

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ) as mock_fetch, patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=response),
    ) as mock_is_pikvm:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=user_input,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "My PiKVM"
    assert result["data"][CONF_CERTIFICATE] == pikvm_cert
    assert result["data"][CONF_SERIAL] == "pikvm-1234"
    assert result["data"][CONF_MODEL] == "v3"
    mock_fetch.assert_awaited_once()
    mock_is_pikvm.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_flow_user_cannot_connect(hass, pikvm_cert):
    """Test the user step when the device cannot be reached."""
    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }

    failure = PiKVMResponse(False, None, None, None, "cannot_connect")

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=failure),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=user_input,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_config_flow_user_initial_form(hass):
    """Ensure the initial user form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_config_flow_user_discovery_retry_shows_form(hass, pikvm_cert):
    """Verify zeroconf discovery with retry surfaces the user form with errors."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: DEFAULT_USERNAME,
        CONF_PASSWORD: DEFAULT_PASSWORD,
        "serial": "SERIAL123",
    }

    with patch(
        "custom_components.pikvm.config_flow.perform_device_setup",
        new=AsyncMock(return_value=(None, {"base": "cannot_connect"})),
    ):
        result = await flow.async_step_zeroconf_confirm("add_device")

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_perform_device_setup_missing_certificate(hass):
    """Ensure we surface an error when no certificate can be retrieved."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass

    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=None),
    ):
        entry, errors = await config_flow.perform_device_setup(flow, user_input)

    assert entry is None
    assert errors["base"] == "cannot_fetch_cert"


@pytest.mark.asyncio
async def test_perform_device_setup_existing_entry_updates(hass, pikvm_cert):
    """Existing entries should be updated and abort the flow."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow.async_abort = MagicMock(return_value={"type": FlowResultType.ABORT})
    flow.async_set_unique_id = AsyncMock()
    flow.async_create_entry = MagicMock()

    existing_entry = MagicMock()
    existing_entry.data = {
        CONF_USERNAME: "saved",
        CONF_PASSWORD: "s3cret",
        "serial": "pikvm-serial",
    }

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3", "pikvm-serial", "My PiKVM", None
                )
            ),
        ),
        patch(
            "custom_components.pikvm.config_flow.find_existing_entry",
            return_value=existing_entry,
        ),
        patch(
            "custom_components.pikvm.config_flow.update_existing_entry",
            autospec=True,
        ) as update_mock,
    ):
        entry, errors = await config_flow.perform_device_setup(
            flow,
            {
                CONF_HOST: "https://pikvm.local",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    assert entry == {"type": FlowResultType.ABORT}
    assert errors is None
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_perform_device_setup_unknown_error(hass):
    """Connection failures bubble up as unknown errors."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(side_effect=ConnectionError),
    ):
        entry, errors = await config_flow.perform_device_setup(
            flow,
            {
                CONF_HOST: "https://pikvm.local",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    assert entry is None
    assert errors["base"] == "unknown_error"


@pytest.mark.asyncio
async def test_perform_device_setup_cannot_connect_without_error(hass, pikvm_cert):
    """Handle responses that fail without providing an explicit error code."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(False, None, None, None, None)
            ),
        ),
    ):
        entry, errors = await config_flow.perform_device_setup(
            flow,
            {
                CONF_HOST: "https://pikvm.local",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    assert entry is None
    assert errors["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_perform_device_setup_localhost_name(hass, pikvm_cert):
    """Ensure localhost device names fall back to the manufacturer label."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow.async_abort = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow.async_create_entry = MagicMock(
        return_value={"type": FlowResultType.CREATE_ENTRY}
    )

    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    success=True,
                    model="V4PLUS",
                    serial="pikvm-9999",
                    name="localhost.localdomain",
                    error=None,
                )
            ),
        ),
        patch(
            "custom_components.pikvm.config_flow.find_existing_entry",
            return_value=None,
        ),
    ):
        entry, errors = await config_flow.perform_device_setup(flow, user_input)

    assert entry == {"type": FlowResultType.CREATE_ENTRY}
    flow.async_create_entry.assert_called_once()
    kwargs = flow.async_create_entry.call_args.kwargs
    assert kwargs["title"] == MANUFACTURER
    assert kwargs["data"][CONF_MODEL] == "v4plus"
    assert kwargs["data"][CONF_SERIAL] == "pikvm-9999"
    assert errors is None


def test_async_get_options_flow_returns_handler():
    """Validate the options flow factory."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    handler = config_flow.PiKVMConfigFlow.async_get_options_flow(entry)
    assert isinstance(handler, PiKVMOptionsFlowHandler)


@pytest.mark.asyncio
async def test_async_step_zeroconf_missing_serial(hass):
    """Abort zeroconf discovery when required data is missing."""
    discovery = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.8"),
        ip_addresses=[IPv4Address("192.168.1.8")],
        port=443,
        hostname="pikvm.local",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "", "model": "v3"},
    )

    with patch(
        "custom_components.pikvm.config_flow.find_existing_entry",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "missing_serial_or_host"


@pytest.mark.asyncio
async def test_async_step_zeroconf_ipv6_address(hass):
    """Abort Zeroconf discovery for IPv6 addresses."""
    discovery = ZeroconfServiceInfo(
        ip_address=IPv6Address("fe80::1"),
        ip_addresses=[IPv6Address("fe80::1")],
        port=443,
        hostname="pikvm.local",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "SERIAL"},
    )

    with patch(
        "custom_components.pikvm.config_flow.find_existing_entry",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "ipv6_address"


@pytest.mark.asyncio
async def test_async_step_zeroconf_existing_entry(hass):
    """Existing entries found via Zeroconf are updated."""
    existing_entry = MagicMock()
    existing_entry.data = {
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        "serial": "serial",
    }

    discovery = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.9"),
        ip_addresses=[IPv4Address("192.168.1.9")],
        port=443,
        hostname="pikvm.local",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "SERIAL", "model": "v3"},
    )

    with (
        patch(
            "custom_components.pikvm.config_flow.find_existing_entry",
            return_value=existing_entry,
        ),
        patch(
            "custom_components.pikvm.config_flow.update_existing_entry",
            autospec=True,
        ) as update_mock,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_async_step_zeroconf_new_device_menu(hass):
    """New Zeroconf discoveries prompt a confirmation menu."""
    discovery = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.10"),
        ip_addresses=[IPv4Address("192.168.1.10")],
        port=443,
        hostname="pikvm.local",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "SERIAL", "model": "v3"},
    )

    with patch(
        "custom_components.pikvm.config_flow.find_existing_entry",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery,
        )

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.asyncio
async def test_async_step_zeroconf_confirm_ignore(hass):
    """Ignoring a discovered device aborts the flow."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: DEFAULT_USERNAME,
        CONF_PASSWORD: DEFAULT_PASSWORD,
        "serial": "SERIAL",
    }

    result = await flow.async_step_zeroconf_confirm("ignore")

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "ignored"


@pytest.mark.asyncio
async def test_async_step_zeroconf_confirm_success(hass, pikvm_cert):
    """Confirming a Zeroconf device proceeds with setup."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: DEFAULT_USERNAME,
        CONF_PASSWORD: DEFAULT_PASSWORD,
        "serial": "SERIAL",
    }

    with patch(
        "custom_components.pikvm.config_flow.perform_device_setup",
        new=AsyncMock(return_value=({"type": FlowResultType.CREATE_ENTRY}, None)),
    ):
        entry = await flow.async_step_zeroconf_confirm("add_device")

    assert entry["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_async_step_user_discovery_password_cleared(hass):
    """Discovery-sourced flows should blank passwords before showing the form."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: DEFAULT_USERNAME,
        CONF_PASSWORD: "secret",
    }

    result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert flow._discovery_info[CONF_PASSWORD] == ""


@pytest.mark.asyncio
async def test_reauth_flow_success(hass, pikvm_cert):
    """Test successful re-authentication updating credentials and TOTP."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_123",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_reauth_123",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    success_resp = PiKVMResponse(True, "v3", "sn_reauth_123", "pikvm-pfsense", None)

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=success_resp),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "JBSWY3DPEHPK3PXP",
            },
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new_password"
    assert entry.data[CONF_TOTP] == "JBSWY3DPEHPK3PXP"


@pytest.mark.asyncio
async def test_reauth_flow_invalid_totp(hass, pikvm_cert):
    """Test re-authentication with invalid base32 TOTP secret."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_invalid_totp",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_SERIAL: "sn_reauth_invalid_totp",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_TOTP: "INVALID_BASE32_!@#$",
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_totp"


@pytest.mark.asyncio
async def test_reauth_flow_auth_failure(hass, pikvm_cert):
    """Test re-authentication with invalid credentials (HTTP 403)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_fail",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "wrong_password",
            CONF_SERIAL: "sn_reauth_fail",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    fail_resp = PiKVMResponse(False, None, None, None, "Exception_HTTP403")

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=fail_resp),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "bad_password",
                CONF_TOTP: "",
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "Exception_HTTP403"


@pytest.mark.asyncio
async def test_reauth_flow_cannot_connect(hass, pikvm_cert):
    """Test re-authentication when host is unreachable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_unreach",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_SERIAL: "sn_reauth_unreach",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    fail_resp = PiKVMResponse(False, None, None, None, "cannot_connect")

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=fail_resp),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "password",
                CONF_TOTP: "",
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_reauth_flow_totp_repopulates_when_empty_and_fails(hass, pikvm_cert):
    """Reproduce issue where removing 2FA from device fails reauth because empty TOTP repopulates.

    User scenario:
    - Device at 192.168.1.2 had 2FA configured with an existing TOTP key.
    - User removed 2FA from the PiKVM device, so the device only accepts password (without TOTP).
    - When HA triggers reauth, the schema defaults CONF_TOTP to the existing key.
    - When the user clears the 2FA key field (omitted in form submission when empty),
      HA's FlowManager validates against the schema and repopulates CONF_TOTP with the old key.
    - The integration generates an OTP code and appends it to the password, which the device
      rejects because 2FA is no longer enabled on the device.
    - Reauth fails and the key is not cleared.
    """
    existing_totp_key = "JBSWY3DPEHPK3PXP"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_totp_clear_fail",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_reauth_totp_clear_fail",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: existing_totp_key,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Verify that the schema presented to the user has default=existing_totp_key
    schema = result["data_schema"]
    # Check that voluptuous repopulates the default when the field is omitted
    validated_empty = schema({CONF_USERNAME: "admin", CONF_PASSWORD: "new_password"})
    assert validated_empty[CONF_TOTP] == existing_totp_key

    # Mock device where 2FA was removed: only accepts plain password, rejects password + OTP
    async def mock_is_pikvm_device(hass_obj, host, username, password_attempt, cert):
        if password_attempt == "new_password":
            return PiKVMResponse(True, "v3", "sn_reauth_totp_clear_fail", "pikvm", None)
        # Device without 2FA rejects any password that has OTP code appended
        return PiKVMResponse(False, None, None, None, "Exception_HTTP403")

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        side_effect=mock_is_pikvm_device,
    ) as mock_device_auth:
        # User cleared the 2FA key in the UI, so CONF_TOTP is omitted in the submission
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
            },
        )

    # Reauth failed because the old key was repopulated, generating an OTP the device rejected
    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "Exception_HTTP403"
    # The config entry still retains the old TOTP key (was not cleared)
    assert entry.data[CONF_TOTP] == existing_totp_key
    # The device was called with password + OTP (length > len('new_password')), not plain password
    called_password = mock_device_auth.call_args[0][3]
    assert called_password != "new_password"
    assert called_password.startswith("new_password")
    assert len(called_password) == len("new_password") + 6


@pytest.mark.asyncio
async def test_reauth_flow_clear_totp_with_space_workaround(hass, pikvm_cert):
    """Reproduce the user's workaround: entering a space allows clearing the 2FA key.

    User scenario:
    - User puts a space in the 2FA field (" ") to prevent the frontend/schema from repopulating.
    - Since CONF_TOTP is present (" "), the schema default is not applied.
    - user_input.get(CONF_TOTP, "").strip() strips the space to an empty string.
    - No TOTP code is appended, so the device authentication succeeds.
    - Reauth succeeds and CONF_TOTP is updated to "" in the config entry.
    """
    existing_totp_key = "JBSWY3DPEHPK3PXP"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_totp_space_workaround",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_reauth_totp_space_workaround",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: existing_totp_key,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Mock device where 2FA was removed: only accepts plain password, rejects password + OTP
    async def mock_is_pikvm_device(hass_obj, host, username, password_attempt, cert):
        if password_attempt == "new_password":
            return PiKVMResponse(True, "v3", "sn_reauth_totp_space_workaround", "pikvm", None)
        return PiKVMResponse(False, None, None, None, "Exception_HTTP403")

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        side_effect=mock_is_pikvm_device,
    ) as mock_device_auth:
        # User entered a space " " to prevent repopulating the default
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: " ",
            },
        )

    # Reauth succeeds!
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    # The config entry has updated password and the TOTP key is successfully cleared to ""
    assert entry.data[CONF_PASSWORD] == "new_password"
    assert entry.data[CONF_TOTP] == ""
    # The device was called with exactly "new_password" without OTP
    mock_device_auth.assert_called_once_with(
        hass,
        "https://192.168.1.2",
        "admin",
        "new_password",
        pikvm_cert,
    )


@pytest.mark.asyncio
async def test_reauth_schema_totp_default_serialization(hass, pikvm_cert):
    """Test that reauth schema serializes CONF_TOTP with default value causing UI repopulation.

    Home Assistant frontend uses voluptuous_serialize to convert data_schema.
    When a schema field specifies 'default', the frontend treats empty inputs as
    defaulting to that value, repopulating the field unless a non-empty character (like space) is entered.
    """
    import voluptuous_serialize

    existing_totp_key = "JBSWY3DPEHPK3PXP"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_schema_check",
        data={
            CONF_HOST: "https://192.168.1.2",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_reauth_schema_check",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: existing_totp_key,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    schema = result["data_schema"]
    serialized = voluptuous_serialize.convert(schema)

    totp_field = next(f for f in serialized if f["name"] == CONF_TOTP)
    # The field contains 'default' set to the existing TOTP key
    assert totp_field["default"] == existing_totp_key
    assert totp_field["optional"] is True


@pytest.mark.asyncio
async def test_perform_device_setup_invalid_totp(hass):
    """Test perform_device_setup returns invalid_totp error on invalid base32 secret (covers lines 66-71)."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass

    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        CONF_TOTP: "INVALID_BASE32_!@#$",
    }

    entry, errors = await config_flow.perform_device_setup(flow, user_input)

    assert entry is None
    assert errors["base"] == "invalid_totp"


@pytest.mark.asyncio
async def test_perform_device_setup_parse_host_port_exception(hass, pikvm_cert):
    """Test perform_device_setup falls back to host when parse_host_port raises (covers lines 119-120)."""
    flow = config_flow.PiKVMConfigFlow()
    flow.hass = hass
    flow.async_set_unique_id = AsyncMock()
    flow.async_create_entry = MagicMock(return_value={"type": FlowResultType.CREATE_ENTRY})

    user_input = {
        CONF_HOST: "https://pikvm.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
    }
    response = PiKVMResponse(True, "V3", "serial-1234", "My PiKVM", None)

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(return_value=response),
        ),
        patch(
            "custom_components.pikvm.config_flow.find_existing_entry",
            return_value=None,
        ),
        patch(
            "custom_components.pikvm.config_flow.parse_host_port",
            side_effect=Exception("Failed parsing host"),
        ),
    ):
        entry, errors = await config_flow.perform_device_setup(flow, user_input)

    assert entry == {"type": FlowResultType.CREATE_ENTRY}
    assert errors is None


@pytest.mark.asyncio
async def test_reauth_confirm_parse_host_port_exception(hass, pikvm_cert):
    """Test async_step_reauth_confirm fallback when parse_host_port raises (covers lines 377-378)."""
    raw_host = "https://192.168.1.50:443"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_reauth_parse_fail",
        data={
            CONF_HOST: raw_host,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_reauth_parse_fail",
            CONF_CERTIFICATE: pikvm_cert,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pikvm.config_flow.parse_host_port",
        side_effect=Exception("Failed to parse host"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["host"] == raw_host


@pytest.mark.asyncio
async def test_async_step_zeroconf_bytes_serial(hass):
    """Test async_step_zeroconf handles bytes serial in discovery_info properties (line 166)."""
    discovery_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="PiKVM._http._tcp.local.",
        properties={"serial": b"sn_bytes_12345", "model": "V3"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.asyncio
async def test_async_step_zeroconf_updates_existing_entry_host(hass):
    """Test Zeroconf discovery updates existing entry host and aborts with already_configured."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sn_zeroconf_update",
        data={
            CONF_HOST: "https://old-host.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
            CONF_SERIAL: "sn_zeroconf_update",
        },
    )
    existing_entry.add_to_hass(hass)

    discovery_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.200"),
        ip_addresses=[IPv4Address("192.168.1.200")],
        port=443,
        hostname="pikvm-new.local.",
        type="_http._tcp.local.",
        name="PiKVM._http._tcp.local.",
        properties={"serial": "sn_zeroconf_update", "model": "V3"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing_entry.data[CONF_HOST] == "192.168.1.200"


@pytest.mark.asyncio
async def test_reauth_flow_unique_id_mismatch(hass, pikvm_cert):
    """Test reauth flow aborts with unique_id_mismatched when serial differs (line 354)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_original_123",
        data={
            CONF_HOST: "https://192.168.1.50",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_original_123",
            CONF_CERTIFICATE: pikvm_cert,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="v3",
                serial="sn_different_456",
                name="Other PiKVM",
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )
        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "unique_id_mismatched"


@pytest.mark.asyncio
async def test_perform_device_setup_totp_whitespace_clears(hass, pikvm_cert):
    """Test perform_device_setup strips whitespace-only TOTP secret to empty string."""
    flow = PiKVMConfigFlow()
    flow.hass = hass
    flow.context = {}

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="v3",
                serial="sn_totp_white",
                name="PiKVM",
                error=None,
            )
        ),
    ):
        result, errors = await perform_device_setup(flow, {
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_TOTP: "   ",
        })
        assert errors is None
        assert result is not None
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_TOTP] == ""


@pytest.mark.asyncio
async def test_reauth_confirm_no_reauth_entry(hass):
    """Test async_step_reauth_confirm when _get_reauth_entry returns None (line 373 branch)."""
    flow = PiKVMConfigFlow()
    flow.hass = hass

    with patch.object(flow, "_get_reauth_entry", return_value=None):
        result = await flow.async_step_reauth_confirm()
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert result["description_placeholders"]["host"] == ""


@pytest.mark.asyncio
async def test_flow_hass_none_branches():
    """Test perform_device_setup and async_step_zeroconf when hass is None (lines 104, 185, 244)."""
    flow = PiKVMConfigFlow()
    flow.context = {}
    flow._async_current_entries = MagicMock(return_value=[])  # type: ignore[method-assign]
    flow.async_set_unique_id = AsyncMock()  # type: ignore[method-assign]
    flow.async_create_entry = MagicMock(return_value={"type": FlowResultType.CREATE_ENTRY})  # type: ignore[method-assign]

    discovery_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="PiKVM._http._tcp.local.",
        properties={"serial": "sn_nohass_1", "model": "V3"},
    )
    with patch.object(flow, "_abort_if_unique_id_configured"):
        result = await flow.async_step_zeroconf(discovery_info)
        assert result["type"] is FlowResultType.MENU
        assert result["step_id"] == "zeroconf_confirm"

    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value="cert"),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="v3",
                serial="sn_nohass_2",
                name="PiKVM",
                error=None,
            )
        ),
    ):
        result2, errors = await perform_device_setup(flow, {
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_TOTP: "",
        })
        assert errors is None
        assert result2 is not None
        assert result2["type"] is FlowResultType.CREATE_ENTRY

    result3 = await flow.async_step_user()
    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "user"


@pytest.mark.asyncio
async def test_zeroconf_missing_ip_address_aborts_without_host_corruption(hass):
    """Test that zeroconf discovery with ip_address=None aborts and does not corrupt existing host."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Existing",
        unique_id="sn_existing_123",
        data={
            CONF_HOST: "https://192.168.1.50",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_existing_123",
            CONF_CERTIFICATE: "cert",
            CONF_TOTP: "",
        },
    )
    existing_entry.add_to_hass(hass)

    service_info = ZeroconfServiceInfo(
        ip_address=None,
        ip_addresses=[],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_existing_123", "model": "V3"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=service_info,
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "missing_serial_or_host"
    assert existing_entry.data[CONF_HOST] == "https://192.168.1.50"


@pytest.mark.asyncio
async def test_zeroconf_host_none_string_aborts(hass):
    """Test that zeroconf discovery where host is the literal string 'None' aborts."""
    service_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        port=443,
        hostname="None",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_valid_123", "model": "V3"},
    )

    with patch.object(ZeroconfServiceInfo, "host", new="None"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=service_info,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "missing_serial_or_host"


@pytest.mark.asyncio
async def test_zeroconf_async_step_add_device(hass, pikvm_cert):
    """Test async_step_add_device proceeds to create entry."""
    service_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.100"),
        ip_addresses=[IPv4Address("192.168.1.100")],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_step_add_1", "model": "V3"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=service_info,
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
    flow_id = result["flow_id"]

    response = PiKVMResponse(True, "V3", "sn_step_add_1", "PiKVM Test", None)
    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=response),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            flow_id,
            user_input={"next_step_id": "add_device"},
        )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "PiKVM Test"
    assert result2["data"][CONF_SERIAL] == "sn_step_add_1"


@pytest.mark.asyncio
async def test_zeroconf_async_step_ignore(hass):
    """Test async_step_ignore aborts the flow with 'ignored'."""
    service_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.101"),
        ip_addresses=[IPv4Address("192.168.1.101")],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_step_ignore_1", "model": "V3"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=service_info,
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
    flow_id = result["flow_id"]

    result2 = await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={"next_step_id": "ignore"},
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "ignored"


@pytest.mark.asyncio
async def test_zeroconf_confirm_direct_dict_ignore(hass):
    """Test async_step_zeroconf_confirm with dict user_input containing next_step_id='ignore'."""
    flow = PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = {"serial": "sn_direct_ignore"}

    result = await flow.async_step_zeroconf_confirm(user_input={"next_step_id": "ignore"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "ignored"

    # Also test when _discovery_info is empty
    flow._discovery_info = {}
    result_empty = await flow.async_step_zeroconf_confirm(user_input={"next_step_id": "ignore"})
    assert result_empty["type"] is FlowResultType.ABORT
    assert result_empty["reason"] == "ignored"


@pytest.mark.asyncio
async def test_reauth_flow_serial_fallback_from_config_entry_data(hass, pikvm_cert):
    """Test reauth flow verifies serial from config_entry.data when unique_id is None."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Legacy Entry",
        unique_id=None,
        data={
            CONF_HOST: "https://192.168.1.50",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "original_password",
            CONF_SERIAL: "sn_original_123",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    # 1. Imposter serial aborts with unique_id_mismatched
    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="V3",
                serial="sn_spoofed_999",
                name="PiKVM Imposter",
                error=None,
            )
        ),
    ):
        result_mismatch = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )
        assert result_mismatch["type"] is FlowResultType.ABORT
        assert result_mismatch["reason"] == "unique_id_mismatched"

    # 2. Matching serial (with whitespace and case difference) succeeds
    result_reauth2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="V3",
                serial="  SN_ORIGINAL_123  ",
                name="PiKVM Original",
                error=None,
            )
        ),
    ):
        result_success = await hass.config_entries.flow.async_configure(
            result_reauth2["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            },
        )
        assert result_success["type"] is FlowResultType.ABORT
        assert result_success["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == "new_password"


@pytest.mark.asyncio
async def test_zeroconf_dual_nic_preserves_existing_entry_host(hass):
    """Test dual-NIC Zeroconf discovery (Ethernet + Wi-Fi) preserves existing entry host without flip-flopping."""
    from custom_components.pikvm.config_flow import _is_entry_host_in_advertised_ips

    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="pikvm-office",
        unique_id="1000000067b50781",
        data={
            CONF_HOST: "https://192.168.1.105",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
            CONF_SERIAL: "1000000067b50781",
        },
    )
    existing_entry.add_to_hass(hass)

    # Test _is_entry_host_in_advertised_ips helper directly including parse_host_port exception fallback
    assert _is_entry_host_in_advertised_ips(
        existing_entry, {"192.168.1.34", "192.168.1.105"}
    ) is True
    with patch(
        "custom_components.pikvm.config_flow.parse_host_port",
        side_effect=ValueError("bad host"),
    ):
        raw_ip_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: "192.168.1.105"},
        )
        assert _is_entry_host_in_advertised_ips(
            raw_ip_entry, {"192.168.1.34", "192.168.1.105"}
        ) is True

    # Dual-NIC mDNS broadcast where primary ip_address is 192.168.1.34 (Ethernet)
    # and ip_addresses includes both 192.168.1.34 and 192.168.1.105 (Wi-Fi)
    discovery_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.34"),
        ip_addresses=[
            IPv4Address("192.168.1.34"),
            IPv4Address("192.168.1.105"),
            IPv6Address("fe80::e813:ddff:fe27:d6b3"),
        ],
        port=443,
        hostname="pikvm-1000000067b50781.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM on pikvm-office._pikvm._tcp.local.",
        properties={"serial": "1000000067b50781", "model": "v4plus"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Existing host https://192.168.1.105 must NOT be overwritten by 192.168.1.34
    assert existing_entry.data[CONF_HOST] == "https://192.168.1.105"

    # Also test fallback path (line 252->254 false branch when unique_id is not yet set on existing_entry)
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        title="pikvm-dual-fallback",
        unique_id=None,
        data={
            CONF_HOST: "https://192.168.1.105",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
            CONF_SERIAL: "sn_dual_fallback",
        },
    )
    await hass.config_entries.async_remove(existing_entry.entry_id)
    legacy_entry.add_to_hass(hass)

    discovery_fallback = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.34"),
        ip_addresses=[
            IPv4Address("192.168.1.34"),
            IPv4Address("192.168.1.105"),
        ],
        port=443,
        hostname="pikvm-fallback.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM._pikvm._tcp.local.",
        properties={"serial": "sn_dual_fallback", "model": "v4plus"},
    )
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_fallback,
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
    assert legacy_entry.data[CONF_HOST] == "https://192.168.1.105"
    assert legacy_entry.unique_id == "sn_dual_fallback"


@pytest.mark.asyncio
async def test_reconfigure_flow_complete_lifecycle(hass, pikvm_cert):
    """Test reconfigure flow init, port handling, errors, mismatch, and success."""
    from homeassistant.const import CONF_PORT

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM",
        unique_id="sn_reconf_123",
        data={
            CONF_HOST: "https://192.168.1.50",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old_password",
            CONF_SERIAL: "sn_reconf_123",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "JBSWY3DPEHPK3PXP",
        },
    )
    entry.add_to_hass(hass)

    flow = PiKVMConfigFlow()
    flow.hass = hass
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": entry.entry_id,
    }

    # 1. Initial form
    form_res = await flow.async_step_reconfigure()
    assert form_res["type"] is FlowResultType.FORM
    assert form_res["step_id"] == "reconfigure_confirm"

    # 2. Invalid TOTP
    res_totp = await flow.async_step_reconfigure_confirm(
        {
            CONF_HOST: "https://192.168.1.51",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "new_password",
            CONF_TOTP: "INVALID_TOTP_!",
        }
    )
    assert res_totp["errors"] == {"base": "invalid_totp"}

    # 3. Cannot fetch cert
    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=None),
    ):
        res_cert = await flow.async_step_reconfigure_confirm(
            {
                CONF_HOST: "https://192.168.1.51",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            }
        )
        assert res_cert["errors"] == {"base": "cannot_fetch_cert"}

    # 4. Cannot connect (response.success=False, error=None)
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(return_value=PiKVMResponse(False, None, None, None, None)),
        ),
    ):
        res_conn = await flow.async_step_reconfigure_confirm(
            {
                CONF_HOST: "https://192.168.1.51:8443",
                CONF_PORT: 8443,
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "",
            }
        )
        assert res_conn["errors"] == {"base": "cannot_connect"}

    # 5. Success with port append and model fallback to reconfigure_entry.data
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(True, None, "sn_reconf_123", "PiKVM", None)
            ),
        ),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
        ),
    ):
        res_ok = await flow.async_step_reconfigure_confirm(
            {
                CONF_HOST: "https://192.168.1.51/",
                CONF_PORT: 8443,
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_password",
                CONF_TOTP: "   ",
            }
        )
        assert res_ok["type"] is FlowResultType.ABORT
        assert res_ok["reason"] == "reconfigure_successful"
        assert entry.data[CONF_HOST] == "https://192.168.1.51:8443"
        assert entry.data[CONF_TOTP] == ""

    # 6. _get_reconfigure_entry returns None branch
    flow_no_entry = PiKVMConfigFlow()
    flow_no_entry.hass = hass
    with patch.object(flow_no_entry, "_get_reconfigure_entry", return_value=None):
        res_none = await flow_no_entry.async_step_reconfigure_confirm()
        assert res_none["type"] is FlowResultType.FORM







