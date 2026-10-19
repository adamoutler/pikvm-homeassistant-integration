"""Empirical adversarial challenger tests for Milestone 4 Iteration 2.

Agent: challenger_m4_it2_1
Focus areas:
1. Zeroconf discovery with ip_address=None, host="None", host="   none   ",
   or missing/invalid serial aborts with missing_serial_or_host without modifying existing config entries.
2. Menu dispatch to async_step_add_device and async_step_ignore works cleanly without raising UnknownStep.
3. async_step_zeroconf_confirm handles both string "ignore" and dict {"next_step_id": "ignore"} cleanly.
4. Reauth flow when unique_id is None on config entry:
   - Case/whitespace normalized serial matching data[CONF_SERIAL] succeeds.
   - Mismatched imposter serial is strictly aborted with unique_id_mismatched and leaves entry unmodified.
"""

from __future__ import annotations

from collections.abc import Generator
from ipaddress import IPv4Address
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry  # type: ignore[import-untyped]

from custom_components.pikvm.cert_handler import PiKVMResponse
from custom_components.pikvm.config_flow import PiKVMConfigFlow
from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def bypass_setup_entry() -> Generator[None, None, None]:
    """Bypass entry setup during config flow tests."""
    with patch(
        "custom_components.pikvm.async_setup_entry",
        return_value=True,
    ):
        yield


# =============================================================================
# Challenge 1: Zeroconf Discovery Guard Matrix & Entry Non-Corruption
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_host,raw_ip,raw_serial,description",
    [
        (None, None, "sn_legit_101", "ip_address=None and host=None"),
        ("None", IPv4Address("192.168.1.100"), "sn_legit_101", "literal host='None'"),
        ("   none   ", IPv4Address("192.168.1.100"), "sn_legit_101", "host='   none   ' with spaces"),
        ("NONE", IPv4Address("192.168.1.100"), "sn_legit_101", "uppercase host='NONE'"),
        ("  NoNe  \n", IPv4Address("192.168.1.100"), "sn_legit_101", "mixed case host with whitespace"),
        ("", IPv4Address("192.168.1.100"), "sn_legit_101", "empty host=''"),
        ("   ", IPv4Address("192.168.1.100"), "sn_legit_101", "whitespace-only host"),
        ("192.168.1.100", None, "sn_legit_101", "ip_address=None with valid IP host"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), None, "serial=None"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), "", "serial=''"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), "   ", "whitespace-only serial"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), "none", "serial='none'"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), "   none   ", "serial='   none   ' with spaces"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), "NONE", "uppercase serial='NONE'"),
        ("192.168.1.100", IPv4Address("192.168.1.100"), "  NoNe  \t", "mixed case serial with whitespace"),
    ],
)
async def test_zeroconf_invalid_host_or_serial_aborts_without_modifying_entry(
    hass: HomeAssistant,
    raw_host: str | None,
    raw_ip: IPv4Address | None,
    raw_serial: str | None,
    description: str,
) -> None:
    """Verify all variations of bad host or serial strictly abort with missing_serial_or_host

    and NEVER modify existing config entries even if serial or host matches.
    """
    initial_host = "https://192.168.1.50"
    existing_serial = "sn_legit_101"
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Existing PiKVM",
        unique_id=existing_serial,
        data={
            CONF_HOST: initial_host,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: existing_serial,
            CONF_CERTIFICATE: "test_cert",
            CONF_TOTP: "",
        },
    )
    existing_entry.add_to_hass(hass)

    properties: dict[str, str | bytes] = {}
    if raw_serial is not None:
        properties["serial"] = raw_serial

    service_info = ZeroconfServiceInfo(
        ip_address=raw_ip,  # type: ignore[arg-type]
        ip_addresses=[raw_ip] if raw_ip is not None else [],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties=properties,
    )

    with patch.object(ZeroconfServiceInfo, "host", new=raw_host):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=service_info,
        )

    assert result["type"] is FlowResultType.ABORT, f"Failed for {description}: {result}"
    assert result["reason"] == "missing_serial_or_host", f"Failed reason for {description}"
    # Security Invariant: The existing entry must NOT be modified or corrupted
    assert existing_entry.data[CONF_HOST] == initial_host, f"Host corrupted for {description}"
    assert existing_entry.data[CONF_SERIAL] == existing_serial


# =============================================================================
# Challenge 2: Menu Dispatch to async_step_add_device and async_step_ignore
# =============================================================================

@pytest.mark.asyncio
async def test_zeroconf_menu_dispatch_add_device_creates_entry(
    hass: HomeAssistant, pikvm_cert: str
) -> None:
    """Verify menu dispatch for 'add_device' flows into async_step_add_device without UnknownStep."""
    service_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.120"),
        ip_addresses=[IPv4Address("192.168.1.120")],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_menu_add_test", "model": "V4 Plus"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=service_info,
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
    assert "add_device" in result["menu_options"]
    assert "ignore" in result["menu_options"]
    flow_id = result["flow_id"]

    response = PiKVMResponse(True, "V4 Plus", "sn_menu_add_test", "PiKVM V4", None)
    with patch(
        "custom_components.pikvm.config_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=pikvm_cert),
    ), patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(return_value=response),
    ):
        result_add = await hass.config_entries.flow.async_configure(
            flow_id,
            user_input={"next_step_id": "add_device"},
        )

    assert result_add["type"] is FlowResultType.CREATE_ENTRY
    assert result_add["title"] == "PiKVM V4"
    assert result_add["data"][CONF_SERIAL] == "sn_menu_add_test"
    assert result_add["data"][CONF_HOST] == "192.168.1.120"


@pytest.mark.asyncio
async def test_zeroconf_menu_dispatch_ignore_aborts(hass: HomeAssistant) -> None:
    """Verify menu dispatch for 'ignore' flows into async_step_ignore without UnknownStep."""
    service_info = ZeroconfServiceInfo(
        ip_address=IPv4Address("192.168.1.121"),
        ip_addresses=[IPv4Address("192.168.1.121")],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_menu_ignore_test", "model": "V3"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=service_info,
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
    flow_id = result["flow_id"]

    result_ignore = await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={"next_step_id": "ignore"},
    )

    assert result_ignore["type"] is FlowResultType.ABORT
    assert result_ignore["reason"] == "ignored"


# =============================================================================
# Challenge 3: async_step_zeroconf_confirm Polymorphic Input Handling
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ignore_input,discovery_state",
    [
        ("ignore", {"serial": "sn_confirm_1"}),
        ("ignore", {}),
        ({"next_step_id": "ignore"}, {"serial": "sn_confirm_2"}),
        ({"next_step_id": "ignore"}, {}),
    ],
)
async def test_async_step_zeroconf_confirm_handles_string_and_dict_ignore(
    hass: HomeAssistant, ignore_input: str | dict[str, str], discovery_state: dict[str, str]
) -> None:
    """Verify async_step_zeroconf_confirm cleanly handles both string 'ignore'

    and dict {'next_step_id': 'ignore'}, even with empty discovery info.
    """
    flow = PiKVMConfigFlow()
    flow.hass = hass
    flow._discovery_info = dict(discovery_state)

    result = await flow.async_step_zeroconf_confirm(user_input=ignore_input)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "ignored"


# =============================================================================
# Challenge 4: Reauth Flow with unique_id=None Serial Fallback Stress
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config_serial,device_serial,should_succeed",
    [
        # Exact match
        ("sn_target_123", "sn_target_123", True),
        # Casing variations
        ("sn_target_123", "SN_TARGET_123", True),
        ("SN_TARGET_123", "sn_target_123", True),
        ("Sn_Target_123", "sN_tArGeT_123", True),
        # Whitespace variations
        ("sn_target_123", "   sn_target_123   ", True),
        ("   sn_target_123   ", "sn_target_123", True),
        ("  sn_target_123  ", "\t\n  SN_TARGET_123 \r\n", True),
        # Imposters and mismatches
        ("sn_target_123", "sn_imposter_999", False),
        ("sn_target_123", "sn_target_12", False),
        ("sn_target_123", "sn_target_123_extra", False),
        ("sn_target_123", "SN_TARGET_456", False),
        ("sn_target_123", "different", False),
    ],
)
async def test_reauth_unique_id_none_serial_fallback_adversarial_matrix(
    hass: HomeAssistant,
    pikvm_cert: str,
    config_serial: str,
    device_serial: str,
    should_succeed: bool,
) -> None:
    """Stress test reauth flow when entry unique_id is None:

    - Matching serials (accounting for case & whitespace) must succeed.
    - Non-matching / imposter serials must abort with unique_id_mismatched and never corrupt data.
    """
    original_password = "initial_uncompromised_password"
    original_username = "admin"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM No Unique ID",
        unique_id=None,
        data={
            CONF_HOST: "https://192.168.1.50",
            CONF_USERNAME: original_username,
            CONF_PASSWORD: original_password,
            CONF_SERIAL: config_serial,
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
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.pikvm.config_flow.is_pikvm_device",
        new=AsyncMock(
            return_value=PiKVMResponse(
                success=True,
                model="V3",
                serial=device_serial,
                name="PiKVM Device",
                error=None,
            )
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "new_admin",
                CONF_PASSWORD: "new_super_secret_password",
                CONF_TOTP: "",
            },
        )

    if should_succeed:
        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == "new_super_secret_password"
        assert entry.data[CONF_USERNAME] == "new_admin"
    else:
        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "unique_id_mismatched"
        # Security Invariant: Original credentials must remain unchanged
        assert entry.data[CONF_PASSWORD] == original_password
        assert entry.data[CONF_USERNAME] == original_username
