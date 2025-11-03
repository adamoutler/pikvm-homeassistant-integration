"""Tests for the PiKVM config flow."""

from ipaddress import IPv4Address, IPv6Address
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha import config_flow
from custom_components.pikvm_ha.cert_handler import PiKVMResponse
from custom_components.pikvm_ha.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
    MANUFACTURER,
)
from custom_components.pikvm_ha.options_flow import PiKVMOptionsFlowHandler


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
        "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ) as mock_fetch, patch(
        "custom_components.pikvm_ha.config_flow.is_pikvm_device",
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
        "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ), patch(
        "custom_components.pikvm_ha.config_flow.is_pikvm_device",
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
    """Ensure the initial user form is shown with translation fallbacks."""
    translator = lambda key, default: default

    with patch(
        "custom_components.pikvm_ha.config_flow.get_translations",
        new=AsyncMock(return_value=translator),
    ):
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

    with (
        patch(
            "custom_components.pikvm_ha.config_flow.perform_device_setup",
            new=AsyncMock(return_value=(None, {"base": "cannot_connect"})),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.get_translations",
            new=AsyncMock(return_value=lambda key, default: default),
        ),
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
        "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
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
            "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3", "pikvm-serial", "My PiKVM", None
                )
            ),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.find_existing_entry",
            return_value=existing_entry,
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.update_existing_entry",
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
        "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
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
            "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.is_pikvm_device",
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
            "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.is_pikvm_device",
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
            "custom_components.pikvm_ha.config_flow.find_existing_entry",
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


@pytest.mark.asyncio
async def test_async_step_import_creates_entry(hass, pikvm_cert):
    """Importing from configuration.yaml should reuse the user step."""
    response = PiKVMResponse(True, "V4PLUS", "pikvm-5555", None, None)

    with (
        patch(
            "custom_components.pikvm_ha.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.is_pikvm_device",
            new=AsyncMock(return_value=response),
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.find_existing_entry",
            return_value=None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                CONF_HOST: "https://pikvm.local",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "PiKVM"
    assert result["data"][CONF_MODEL] == "v4plus"


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
        "custom_components.pikvm_ha.config_flow.find_existing_entry",
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
        "custom_components.pikvm_ha.config_flow.find_existing_entry",
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
            "custom_components.pikvm_ha.config_flow.find_existing_entry",
            return_value=existing_entry,
        ),
        patch(
            "custom_components.pikvm_ha.config_flow.update_existing_entry",
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
        "custom_components.pikvm_ha.config_flow.find_existing_entry",
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
        "custom_components.pikvm_ha.config_flow.perform_device_setup",
        new=AsyncMock(return_value=({"type": FlowResultType.CREATE_ENTRY}, None)),
    ):
        entry = await flow.async_step_zeroconf_confirm("add_device")

    assert entry["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_async_step_user_with_translation_dict(hass):
    """Ensure dictionary-based translations flow through placeholders."""
    translations = {
        "step.user.data.url": "Translated URL",
        "step.user.data.username": "Translated Username",
        "step.user.data.password": "Translated Password",
    }

    with patch(
        "custom_components.pikvm_ha.config_flow.get_translations",
        new=AsyncMock(return_value=translations),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

    assert result["type"] == FlowResultType.FORM
    placeholders = result["description_placeholders"]
    assert placeholders["url"] == "Translated URL"
    assert placeholders["username"] == "Translated Username"
    assert placeholders["password"] == "Translated Password"


@pytest.mark.asyncio
async def test_async_step_user_without_translations_uses_defaults(hass):
    """Default placeholders should be provided when translations are unavailable."""

    with patch(
        "custom_components.pikvm_ha.config_flow.get_translations",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

    assert result["type"] == FlowResultType.FORM
    placeholders = result["description_placeholders"]
    assert placeholders["url"] == "URL or IP address of the PiKVM device"
    assert placeholders["username"] == "Username for PiKVM"
    assert placeholders["password"] == "Password for PiKVM"


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

    with patch(
        "custom_components.pikvm_ha.config_flow.get_translations",
        new=AsyncMock(return_value=lambda key, default: default),
    ):
        result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert flow._discovery_info[CONF_PASSWORD] == ""
