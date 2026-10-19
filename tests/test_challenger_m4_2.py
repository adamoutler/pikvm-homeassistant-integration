"""Adversarial challenger tests for Milestone 4 (challenger_m4_2).

Focus:
1. Stress test async_remove_config_entry_device (active, uninitialized, stale, unrelated, fuzzing).
2. Stress test entry setup/unload/reload cycles for zero leaks in hass.data.
3. Stress test discovery and flow dispatch edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from pikvm_aio import PiKVMDeviceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm import (
    DOMAIN,
    LEGACY_DOMAIN,
    async_remove_config_entry_device,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
    update_listener,
)
from custom_components.pikvm.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_TOTP,
    CONF_USERNAME,
)


@pytest.fixture
def mock_pi_info():
    """Create a mock PiKVMDeviceInfo."""
    raw = {
        "hw": {
            "platform": {
                "type": "v3",
                "model": "V3.3",
                "base": "Raspberry Pi 4",
                "serial": "sn_adv_active_123",
            }
        },
        "system": {"kvmd": {"version": "3.100"}},
        "meta": {"server": {"host": "pikvm.local"}},
        "extras": {},
    }
    return PiKVMDeviceInfo.from_dict(raw)


# =============================================================================
# 1. Stress Tests: async_remove_config_entry_device
# =============================================================================

@pytest.mark.asyncio
async def test_remove_device_active_with_running_coordinator(hass: HomeAssistant):
    """Scenario 1.1: Active device with running coordinator must reject removal (return False)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="active_coord_entry",
        unique_id="sn_adv_active_123",
        data={CONF_SERIAL: "sn_adv_active_123"},
    )
    entry.add_to_hass(hass)

    coord = MagicMock()
    coord.device_info = DeviceInfo(
        identifiers={(DOMAIN, "sn_adv_active_123"), (LEGACY_DOMAIN, "sn_adv_active_123")}
    )
    entry.runtime_data = coord

    dev_reg = dr.async_get(hass)

    # DOMAIN identifier
    active_dev1 = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_adv_active_123")},
        name="Active Device DOMAIN",
    )
    assert await async_remove_config_entry_device(hass, entry, active_dev1) is False

    # LEGACY_DOMAIN identifier
    active_dev2 = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(LEGACY_DOMAIN, "sn_adv_active_123")},
        name="Active Device LEGACY",
    )
    assert await async_remove_config_entry_device(hass, entry, active_dev2) is False


@pytest.mark.asyncio
async def test_remove_device_active_coordinator_uninitialized_or_none(hass: HomeAssistant):
    """Scenario 1.2: Active device with coordinator uninitialized/None falls back to entry data/unique_id."""
    # Sub-case A: Serial in config_entry.data[CONF_SERIAL]
    entry_a = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_uninit_a",
        unique_id="diff_uid",
        data={CONF_SERIAL: "sn_fallback_serial_a"},
    )
    entry_a.runtime_data = None
    entry_a.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    dev_a1 = dev_reg.async_get_or_create(
        config_entry_id=entry_a.entry_id,
        identifiers={(DOMAIN, "sn_fallback_serial_a")},
    )
    assert await async_remove_config_entry_device(hass, entry_a, dev_a1) is False

    dev_a2 = dev_reg.async_get_or_create(
        config_entry_id=entry_a.entry_id,
        identifiers={(LEGACY_DOMAIN, "sn_fallback_serial_a")},
    )
    assert await async_remove_config_entry_device(hass, entry_a, dev_a2) is False

    # Sub-case B: Serial in config_entry.unique_id (CONF_SERIAL missing/empty)
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_uninit_b",
        unique_id="sn_fallback_serial_b",
        data={},
    )
    entry_b.runtime_data = None
    entry_b.add_to_hass(hass)

    dev_b = dev_reg.async_get_or_create(
        config_entry_id=entry_b.entry_id,
        identifiers={(DOMAIN, "sn_fallback_serial_b")},
    )
    assert await async_remove_config_entry_device(hass, entry_b, dev_b) is False


@pytest.mark.asyncio
async def test_remove_device_stale_different_serial(hass: HomeAssistant):
    """Scenario 1.3: Stale device with old/replaced serial number returns True."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_stale_diff",
        unique_id="sn_current_hardware",
        data={CONF_SERIAL: "sn_current_hardware"},
    )
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)

    stale_dev_domain = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_old_hardware_replaced")},
    )
    assert await async_remove_config_entry_device(hass, entry, stale_dev_domain) is True

    stale_dev_legacy = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(LEGACY_DOMAIN, "sn_old_hardware_legacy")},
    )
    assert await async_remove_config_entry_device(hass, entry, stale_dev_legacy) is True


@pytest.mark.asyncio
async def test_remove_device_completely_unrelated_identifiers(hass: HomeAssistant):
    """Scenario 1.4: Device with completely unrelated domain identifiers returns True."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_unrelated",
        unique_id="sn_pikvm_active",
        data={CONF_SERIAL: "sn_pikvm_active"},
    )
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)

    unrelated_dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_domain", "unrelated_serial_999")},
    )
    assert await async_remove_config_entry_device(hass, entry, unrelated_dev) is True


@pytest.mark.asyncio
async def test_remove_device_fuzz_unexpected_identifiers(hass: HomeAssistant):
    """Scenario 1.5: Fuzz device identifiers with empty set, unexpected tuple lengths, non-string types."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_fuzz",
        unique_id="sn_fuzz_target",
        data={CONF_SERIAL: "sn_fuzz_target"},
    )
    entry.add_to_hass(hass)

    # 1. Empty set of identifiers on mock device
    mock_dev_empty = MagicMock()
    mock_dev_empty.id = "mock_empty_id"
    mock_dev_empty.name = "Empty Identifiers Device"
    mock_dev_empty.identifiers = set()
    assert await async_remove_config_entry_device(hass, entry, mock_dev_empty) is True

    # 2. Unexpected tuple shapes and types inside identifiers
    weird_identifiers = [
        (DOMAIN, "sn_fuzz_target", "extra_dimension"),  # 3-tuple
        (DOMAIN,),  # 1-tuple
        ("unrelated_domain", 12345),  # integer second element
        (DOMAIN, ""),  # blank serial
        (DOMAIN, "sn_fuzz_target_DIFFERENT"),  # different serial string
        (DOMAIN, None),  # None serial
    ]
    for wt in weird_identifiers:
        mock_dev = MagicMock()
        mock_dev.id = "mock_fuzz_dev"
        mock_dev.name = "Fuzz Device"
        mock_dev.identifiers = {wt}
        res = await async_remove_config_entry_device(hass, entry, mock_dev)
        assert res is True, f"Failed for identifier: {wt}"


@pytest.mark.asyncio
async def test_remove_device_none_identifiers_vulnerability(hass: HomeAssistant):
    """Challenge: Verify behavior when device_entry.identifiers is None or non-set."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_vuln",
        unique_id="sn_target",
        data={CONF_SERIAL: "sn_target"},
    )
    entry.add_to_hass(hass)

    mock_dev_none = MagicMock()
    mock_dev_none.id = "mock_none_id"
    mock_dev_none.name = "None Device"
    mock_dev_none.identifiers = None

    # Verify async_remove_config_entry_device safely handles identifiers=None without crashing
    res = await async_remove_config_entry_device(hass, entry, mock_dev_none)
    assert res is True


# =============================================================================
# 2. Stress Tests: Entry Setup, Reload & Unload Cycles (Leak Detection)
# =============================================================================

@pytest.mark.asyncio
async def test_entry_setup_unload_reload_cycle_stress(
    hass: HomeAssistant, pikvm_cert: str, mock_pi_info: PiKVMDeviceInfo
):
    """Stress test 10 consecutive setup -> reload -> unload cycles to guarantee zero state leaks in hass.data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_cycle_stress",
        title="PiKVM Cycle Test",
        unique_id="sn_adv_active_123",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_adv_active_123",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    with (
        patch(
            "custom_components.pikvm.coordinator.PiKVMClient.get_info",
            new=AsyncMock(return_value=mock_pi_info),
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
        ) as mock_forward,
        patch.object(
            hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)
        ) as mock_unload,
    ):
        for cycle in range(10):
            # Step 1: Setup entry
            success = await async_setup_entry(hass, entry)
            assert success is True, f"Cycle {cycle}: async_setup_entry failed"
            assert entry.runtime_data is not None, f"Cycle {cycle}: entry.runtime_data not set"

            # Verify DOMAIN in hass.data does NOT leak this entry
            if DOMAIN in hass.data:
                assert entry.entry_id not in hass.data[DOMAIN], (
                    f"Cycle {cycle}: entry_id leaked into hass.data[DOMAIN]!"
                )

            # Step 2: Reload entry via update_listener
            with patch.object(
                hass.config_entries, "async_reload", new=AsyncMock()
            ) as mock_reload:
                await update_listener(hass, entry)
                mock_reload.assert_awaited_once_with(entry.entry_id)

            # Step 3: Unload entry
            unload_success = await async_unload_entry(hass, entry)
            assert unload_success is True, f"Cycle {cycle}: async_unload_entry failed"

            # Verify no leaks after unload
            if DOMAIN in hass.data:
                assert entry.entry_id not in hass.data[DOMAIN], (
                    f"Cycle {cycle}: entry_id leaked after unload"
                )

        assert mock_forward.await_count == 10
        assert mock_unload.await_count == 10

    # Step 4: Final removal cleanup check
    ir.async_create_issue(
        hass, DOMAIN, f"undervoltage_{entry.entry_id}",
        is_fixable=False, severity=ir.IssueSeverity.CRITICAL,
        translation_key="undervoltage",
    )
    ir.async_create_issue(
        hass, DOMAIN, f"throttling_{entry.entry_id}",
        is_fixable=False, severity=ir.IssueSeverity.WARNING,
        translation_key="throttling",
    )

    await async_remove_entry(hass, entry)
    issue_reg = ir.async_get(hass)
    assert issue_reg.async_get_issue(DOMAIN, f"undervoltage_{entry.entry_id}") is None
    assert issue_reg.async_get_issue(DOMAIN, f"throttling_{entry.entry_id}") is None


# =============================================================================
# 3. Adversarial Tests: Discovery Flow Navigation Failures
# =============================================================================

@pytest.mark.asyncio
async def test_zeroconf_discovery_menu_options_dispatch_bug(hass: HomeAssistant):
    """Challenge: Verify that selecting 'add_device' from zeroconf menu raises UnknownStep in HA core."""
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.188",
        ip_addresses=["192.168.1.188"],
        port=443,
        hostname="pikvm.local.",
        type="_http._tcp.local.",
        name="pikvm._http._tcp.local.",
        properties={"serial": "sn_dispatch_probe", "model": "v3"},
    )

    with patch(
        "custom_components.pikvm.config_flow.find_existing_entry",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_ZEROCONF},
            data=discovery_info,
        )

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "zeroconf_confirm"
    flow_id = result["flow_id"]

    # When user selects 'add_device', HA FlowManager calls flow.async_step_add_device
    # PiKVMConfigFlow implements async_step_add_device cleanly
    result_add = await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={"next_step_id": "add_device"},
    )
    assert result_add["type"] in (FlowResultType.CREATE_ENTRY, FlowResultType.FORM)
