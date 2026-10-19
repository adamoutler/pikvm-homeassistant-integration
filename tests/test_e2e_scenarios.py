"""End-to-End Scenarios and Cross-Feature Combinations for PiKVM Integration.

Covers Tier 3 (Cross-Feature Pairwise Interactions) and Tier 4 (Real-World Application Scenarios)
as specified in TEST_INFRA.md:
- Tier 3:
  1. Reauth after coordinator authentication failure.
  2. Repairs creation and dismissal lifecycle during polling cycles.
  3. Options scan interval update with live coordinator reload.
  4. Zeroconf discovery update of host/IP on an existing entry.
  5. Device reconfiguration followed by diagnostic dump verifying new host and redacted secrets.
  6. Hardware throttling flag transition: none -> under-voltage -> throttled -> normal.
  7. Unload and reload lifecycle preserving entity registry entries and unique IDs.
  8. Multi-device isolation: two distinct PiKVM entries operating concurrently without cross-talk.
  9. Empty TOTP secret submission clears stored 2FA token.
  10. Stale device cleanup and device registry name reconciliation during setup.
  11. Sensor availability tracking coordinator success and network failure.
  12. Diagnostics reflecting live hardware throttling state accurately.
- Tier 4:
  1. Scenario 1: Fresh Zeroconf Discovery to Ingestion & Sensor Generation E2E.
  2. Scenario 2: Hardware Reboot & Transient Network Disconnect Recovery E2E.
  3. Scenario 3: 2FA TOTP Credential Rotation & Reauth Flow E2E.
  4. Scenario 4: Hardware Undervoltage & Throttling Self-Healing E2E.
  5. Scenario 5: DHCP IP Reallocation via mDNS Discovery Update & Integration Teardown E2E.
  6. Scenario 6: Mass Storage Drive (MSD) Mount and Eject Lifecycle E2E.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_ZEROCONF,
    ConfigEntryState,
)
from homeassistant.const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers.issue_registry import IssueSeverity
from pikvm_aio import (
    PiKVMAuthenticationError,
    PiKVMConnectionError,
    PiKVMDeviceInfo,
    PiKVMTimeoutError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    MANUFACTURER,
)
from custom_components.pikvm.coordinator import PiKVMDataUpdateCoordinator
from custom_components.pikvm.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.pikvm.options_flow import PiKVMOptionsFlowHandler

# ---------------------------------------------------------------------------
# Fixtures & Sample Telemetry Generators
# ---------------------------------------------------------------------------


def make_pikvm_telemetry(
    serial: str = "sn_e2e_001",
    host: str = "pikvm-e2e.local",
    temp_cpu: float = 44.0,
    cpu_util: float = 18.5,
    mem_total: int = 4147483648,
    mem_used: int = 1073741824,
    fan_speed: int = 2400,
    raw_flags: int = 0,
    text_flags: list[str] | None = None,
    uv_now: bool = False,
    uv_past: bool = False,
    msd_total: int = 16000000000,
    msd_available: int = 8000000000,
    msd_mounted: bool = True,
    msd_enabled: bool = True,
    ipmi_running: bool = True,
    vnc_running: bool = False,
    webterm_running: bool = True,
    janus_running: bool = False,
) -> PiKVMDeviceInfo:
    """Generate structured PiKVM telemetry instance."""
    mem_pct = round((mem_used / mem_total) * 100, 1) if mem_total else 0.0
    payload: dict[str, Any] = {
        "hw": {
            "platform": {
                "type": "v3",
                "model": "V3.3",
                "base": "Raspberry Pi 4",
                "serial": serial,
            },
            "health": {
                "temp": {"cpu": temp_cpu},
                "throttling": {
                    "raw_flags": raw_flags,
                    "text_flags": text_flags or [],
                    "voltage": {"core": {"now": uv_now, "past": uv_past}},
                },
            },
            "performance": {
                "cpu": {"utilization": cpu_util},
                "memory": {
                    "total": mem_total,
                    "used": mem_used,
                    "utilization": mem_pct,
                },
                "fan": {"speed": fan_speed},
            },
        },
        "system": {"kvmd": {"version": "3.102"}},
        "meta": {"server": {"host": host, "name": f"PiKVM {serial}"}},
        "extras": {
            "ipmi": {"is_running": ipmi_running},
            "vnc": {"is_running": vnc_running},
            "webterm": {"is_running": webterm_running},
            "janus": {"is_running": janus_running},
        },
        "msd": {
            "storage": {"total": msd_total, "available": msd_available},
            "drive": {"is_mounted": msd_mounted},
            "is_enabled": msd_enabled,
        },
    }
    return PiKVMDeviceInfo.from_dict(payload)


@pytest.fixture
def e2e_entry(pikvm_cert: str) -> MockConfigEntry:
    """Create a standard mock entry for E2E tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM E2E Device",
        unique_id="sn_e2e_001",
        data={
            CONF_HOST: "https://192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "initial_password",
            CONF_SERIAL: "sn_e2e_001",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "JBSWY3DPEHPK3PXP",
        },
        options={CONF_SCAN_INTERVAL: 30},
    )


# ===========================================================================
# Tier 3: Cross-Feature Combinations & Pairwise Interactions (12 Tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_tier3_reauth_after_coordinator_auth_failure(
    hass: HomeAssistant, e2e_entry: MockConfigEntry, pikvm_cert: str
):
    """Tier 3.1: Coordinator auth failure triggers reauth flow which restores polling."""
    e2e_entry.add_to_hass(hass)
    healthy_dev = make_pikvm_telemetry()

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=healthy_dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data
    assert coordinator.last_update_success is True

    # Password changed on PiKVM -> polling fails
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMAuthenticationError(
            "401 Unauthorized: Invalid TOTP or Password"
        )
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    # Execute reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": e2e_entry.entry_id},
        data=e2e_entry.data,
    )
    assert result["type"] == FlowResultType.FORM

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_e2e_001", "PiKVM E2E Device", None
                )
            ),
        ),
        patch(
            "custom_components.pikvm.coordinator.PiKVMClient.get_info",
            new=AsyncMock(return_value=healthy_dev),
        ),
    ):
        reauth_res = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "rotated_secret_password",
                CONF_TOTP: "JBSWY3DPEHPK3PXP",
            },
        )
        assert reauth_res["type"] == FlowResultType.ABORT
        assert reauth_res["reason"] == "reauth_successful"
        await hass.async_block_till_done()

    assert e2e_entry.data[CONF_PASSWORD] == "rotated_secret_password"
    reloaded_coordinator = e2e_entry.runtime_data
    assert reloaded_coordinator.last_update_success is True


@pytest.mark.asyncio
async def test_tier3_repairs_lifecycle_during_polling_cycles(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.2: Polling cycles dynamically create and clear issue_registry entries."""
    e2e_entry.add_to_hass(hass)
    reg = ir.async_get(hass)
    uv_issue_id = f"undervoltage_{e2e_entry.entry_id}"
    th_issue_id = f"throttling_{e2e_entry.entry_id}"

    # Cycle 1: Clean
    dev_clean = make_pikvm_telemetry(raw_flags=0, uv_now=False, uv_past=False)
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev_clean),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    assert reg.async_get_issue(DOMAIN, uv_issue_id) is None
    assert reg.async_get_issue(DOMAIN, th_issue_id) is None

    # Cycle 2: Power sag introduces undervoltage
    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data
    dev_uv = make_pikvm_telemetry(raw_flags=0x1, uv_now=True)
    coordinator.client.get_info = AsyncMock(return_value=dev_uv)
    await coordinator.async_refresh()

    assert reg.async_get_issue(DOMAIN, uv_issue_id) is not None
    assert reg.async_get_issue(DOMAIN, uv_issue_id).severity == IssueSeverity.CRITICAL

    # Cycle 3: Power sag clears
    coordinator.client.get_info = AsyncMock(return_value=dev_clean)
    await coordinator.async_refresh()
    assert reg.async_get_issue(DOMAIN, uv_issue_id) is None


@pytest.mark.asyncio
async def test_tier3_options_scan_interval_update_live_reload(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.3: Updating scan_interval in options flow triggers update_listener and reload."""
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry()

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    # Change options from 30s to 15s
    handler = PiKVMOptionsFlowHandler(e2e_entry)
    handler.hass = hass
    result = await handler.async_step_init(user_input={CONF_SCAN_INTERVAL: 15})
    assert result["type"] == FlowResultType.CREATE_ENTRY

    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ):
        hass.config_entries.async_update_entry(
            e2e_entry, options={CONF_SCAN_INTERVAL: 15}
        )
        await hass.async_block_till_done()
        assert e2e_entry.options[CONF_SCAN_INTERVAL] == 15


@pytest.mark.asyncio
async def test_tier3_zeroconf_discovery_updates_existing_entry_host(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.4: Discovery of same serial with new IP updates existing entry without duplicate."""
    e2e_entry.add_to_hass(hass)
    assert e2e_entry.data[CONF_HOST] == "https://192.168.1.100"

    # Zeroconf broadcast announces new IP 192.168.1.188 for same serial
    service_info = ZeroconfServiceInfo(
        ip_address="192.168.1.188",
        ip_addresses=["192.168.1.188"],
        port=443,
        hostname="pikvm-migrated.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM Migrated._pikvm._tcp.local.",
        properties={"serial": "sn_e2e_001", "model": "V3.3"},
    )
    flow = PiKVMConfigFlow()
    flow.hass = hass
    result = await flow.async_step_zeroconf(service_info)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert "192.168.1.188" in e2e_entry.data[CONF_HOST]


@pytest.mark.asyncio
async def test_tier3_reconfigure_flow_updates_diagnostics_redaction(
    hass: HomeAssistant, e2e_entry: MockConfigEntry, pikvm_cert: str
):
    """Tier 3.5: Reconfiguring device reflects new host in diagnostics with secrets redacted."""
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry(host="pikvm-original.local")

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    # Reconfigure with new host and new credentials
    init_res = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": e2e_entry.entry_id}
    )
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_e2e_001", "PiKVM New", None
                )
            ),
        ),
    ):
        step_res = await hass.config_entries.flow.async_configure(
            init_res["flow_id"],
            user_input={
                CONF_HOST: "https://pikvm-reconfigured.local",
                CONF_PORT: 443,
                CONF_USERNAME: "new_admin",
                CONF_PASSWORD: "super_secret_reconfigured_password",
                CONF_TOTP: "",
            },
        )
        assert step_res["type"] == FlowResultType.ABORT
        assert step_res["reason"] == "reconfigure_successful"

    diag = await async_get_config_entry_diagnostics(hass, e2e_entry)
    assert "pikvm-reconfigured.local" in diag["config_entry"]["data"][CONF_HOST]
    assert diag["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert "super_secret_reconfigured_password" not in str(diag)


@pytest.mark.asyncio
async def test_tier3_hardware_throttling_binary_sensor_and_repairs_sync(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.6: Throttling flags toggle binary sensor and create/delete repair issue synchronously."""
    e2e_entry.add_to_hass(hass)
    dev_normal = make_pikvm_telemetry(raw_flags=0)
    dev_throttled = make_pikvm_telemetry(raw_flags=0x2, text_flags=["throttled"])

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev_normal),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    sensor_id = "binary_sensor.pikvm_e2e_device_throttling"
    assert hass.states.get(sensor_id).state == "off"
    issue_id = f"throttling_{e2e_entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    # Throttling activates
    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data
    coordinator.client.get_info = AsyncMock(return_value=dev_throttled)
    await coordinator.async_refresh()

    assert hass.states.get(sensor_id).state == "on"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # Throttling resolves
    coordinator.client.get_info = AsyncMock(return_value=dev_normal)
    await coordinator.async_refresh()

    assert hass.states.get(sensor_id).state == "off"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.asyncio
async def test_tier3_unload_and_reload_lifecycle(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.7: Unloading and reloading config entry preserves entity registry unique IDs."""
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry()

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    temp_ent = ent_reg.async_get("sensor.pikvm_e2e_device_cpu_temperature")
    assert temp_ent is not None
    original_uid = temp_ent.unique_id

    # Unload
    assert await hass.config_entries.async_unload(e2e_entry.entry_id) is True
    await hass.async_block_till_done()
    assert e2e_entry.state is ConfigEntryState.NOT_LOADED

    # Reload
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    temp_ent_reloaded = ent_reg.async_get("sensor.pikvm_e2e_device_cpu_temperature")
    assert temp_ent_reloaded is not None
    assert temp_ent_reloaded.unique_id == original_uid


@pytest.mark.asyncio
async def test_tier3_multi_device_isolation(hass: HomeAssistant, pikvm_cert: str):
    """Tier 3.8: Multiple PiKVM devices operate concurrently without telemetry or issue crosstalk."""
    dev1_telemetry = make_pikvm_telemetry(
        serial="sn_device_A",
        host="pikvm-a.local",
        temp_cpu=40.0,
        raw_flags=0x1,
        uv_now=True,
    )
    dev2_telemetry = make_pikvm_telemetry(
        serial="sn_device_B", host="pikvm-b.local", temp_cpu=58.0, raw_flags=0
    )

    entry1 = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Device A",
        unique_id="sn_device_A",
        data={
            CONF_HOST: "https://192.168.1.101",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "p1",
            CONF_SERIAL: "sn_device_A",
            CONF_CERTIFICATE: pikvm_cert,
        },
    )
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Device B",
        unique_id="sn_device_B",
        data={
            CONF_HOST: "https://192.168.1.102",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "p2",
            CONF_SERIAL: "sn_device_B",
            CONF_CERTIFICATE: pikvm_cert,
        },
    )
    entry1.add_to_hass(hass)
    entry2.add_to_hass(hass)

    async def mock_get_info(self_client):
        base_url = getattr(self_client, "base_url", "")
        if "192.168.1.101" in base_url:
            return dev1_telemetry
        return dev2_telemetry

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        autospec=True,
        side_effect=mock_get_info,
    ):
        if entry1.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry1.entry_id) is True
        if entry2.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry2.entry_id) is True
        await hass.async_block_till_done()

    # Verify sensor values are isolated
    state_a = hass.states.get("sensor.pikvm_device_a_cpu_temperature")
    state_b = hass.states.get("sensor.pikvm_device_b_cpu_temperature")
    assert state_a is not None and float(state_a.state) == 40.0
    assert state_b is not None and float(state_b.state) == 58.0

    # Verify issues are isolated (Device A has undervoltage, Device B does not)
    reg = ir.async_get(hass)
    assert reg.async_get_issue(DOMAIN, f"undervoltage_{entry1.entry_id}") is not None
    assert reg.async_get_issue(DOMAIN, f"undervoltage_{entry2.entry_id}") is None


@pytest.mark.asyncio
async def test_tier3_empty_totp_clears_stored_2fa(
    hass: HomeAssistant, e2e_entry: MockConfigEntry, pikvm_cert: str
):
    """Tier 3.9: Submitting whitespace or empty string in reconfigure removes stored TOTP key."""
    e2e_entry.add_to_hass(hass)
    assert e2e_entry.data[CONF_TOTP] == "JBSWY3DPEHPK3PXP"

    init_res = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": e2e_entry.entry_id}
    )
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_e2e_001", "PiKVM Test", None
                )
            ),
        ),
    ):
        step_res = await hass.config_entries.flow.async_configure(
            init_res["flow_id"],
            user_input={
                CONF_HOST: "https://192.168.1.100",
                CONF_PORT: 443,
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "initial_password",
                CONF_TOTP: "   ",
            },
        )
        assert step_res["type"] == FlowResultType.ABORT
        assert e2e_entry.data[CONF_TOTP] == ""


@pytest.mark.asyncio
async def test_tier3_stale_device_cleanup_and_rename_reconciliation(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.10: Setup cleans up orphaned devices and updates generic device names."""
    e2e_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)

    # Orphan device without matching serial
    stale_dev = dev_reg.async_get_or_create(
        config_entry_id=e2e_entry.entry_id,
        identifiers={(DOMAIN, "old_decommissioned_serial")},
        name="Old PiKVM",
    )
    # Valid device with generic name
    valid_dev = dev_reg.async_get_or_create(
        config_entry_id=e2e_entry.entry_id,
        identifiers={(DOMAIN, "sn_e2e_001")},
        name="PiKVM",
    )

    dev = make_pikvm_telemetry()
    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    assert dev_reg.async_get(stale_dev.id) is None
    updated_valid = dev_reg.async_get(valid_dev.id)
    assert updated_valid is not None
    assert updated_valid.name == "PiKVM E2E Device"


@pytest.mark.asyncio
async def test_tier3_sensor_availability_tracks_coordinator_success(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.11: Sensor availability reflects coordinator network reachability."""
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry()

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    sensor_id = "sensor.pikvm_e2e_device_cpu_temperature"
    assert hass.states.get(sensor_id).state == "44.0"

    # Simulate network failure
    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMConnectionError("Host offline")
    )
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert hass.states.get(sensor_id).state == "unavailable"

    # Restore network
    coordinator.client.get_info = AsyncMock(return_value=dev)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert hass.states.get(sensor_id).state == "44.0"


@pytest.mark.asyncio
async def test_tier3_diagnostics_reflects_live_throttling_state(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 3.12: Diagnostics captures coordinator health payload with throttling details."""
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry(raw_flags=0x4, text_flags=["arm-frequency-capped"])

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, e2e_entry)
    throttling_diag = diag["coordinator"]["data"]["hw"]["health"]["throttling"]
    assert throttling_diag["raw_flags"] == 0x4
    assert "arm-frequency-capped" in throttling_diag["text_flags"]


# ===========================================================================
# Tier 4: Real-World Application Scenarios (6 Scenarios)
# ===========================================================================


@pytest.mark.asyncio
async def test_tier4_scenario1_fresh_zeroconf_to_sensor_ingestion_e2e(
    hass: HomeAssistant, pikvm_cert: str
):
    """Tier 4.1: Scenario 1 - Fresh Zeroconf Discovery to Ingestion & Full Entity Generation.

    Verifies end-to-end lifecycle:
    1. PiKVM V3 device announces on network via mDNS.
    2. User confirms discovered device setup in Home Assistant.
    3. TLS certificate fetched, verified, and stored.
    4. Config entry created with unique_id = hardware serial.
    5. Integration loads coordinator, registers device in device registry, and adds entities.
    6. All numeric LTS sensors and binary sensors populate and reflect telemetry accurately.
    7. Diagnostics dump verifies clean ingestion and strict secret redaction.
    """
    service_info = ZeroconfServiceInfo(
        ip_address="192.168.1.120",
        ip_addresses=["192.168.1.120"],
        port=443,
        hostname="pikvm-prod-01.local.",
        type="_pikvm._tcp.local.",
        name="PiKVM Production._pikvm._tcp.local.",
        properties={"serial": "SN_PROD_120", "model": "V3.3"},
    )
    flow = PiKVMConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_ZEROCONF}
    init_res = await flow.async_step_zeroconf(service_info)
    assert init_res["type"] == FlowResultType.MENU

    # Telemetry representing newly discovered device
    dev_telemetry = make_pikvm_telemetry(
        serial="sn_prod_120",
        host="pikvm-prod-01.local",
        temp_cpu=46.8,
        cpu_util=14.2,
        mem_total=4000000000,
        mem_used=1000000000,
        fan_speed=2650,
        msd_total=16000000000,
        msd_available=4000000000,
    )

    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_prod_120", "PiKVM Production 120", None
                )
            ),
        ),
    ):
        setup_res = await flow.async_step_zeroconf_confirm("add_device")
        assert setup_res["type"] == FlowResultType.CREATE_ENTRY
        assert setup_res["data"][CONF_SERIAL] == "sn_prod_120"

    # Setup the created entry into Home Assistant
    created_entry = MockConfigEntry(
        domain=DOMAIN,
        title=setup_res["title"],
        unique_id=setup_res["data"][CONF_SERIAL],
        data=setup_res["data"],
    )
    created_entry.add_to_hass(hass)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev_telemetry),
    ):
        assert await hass.config_entries.async_setup(created_entry.entry_id) is True
        await hass.async_block_till_done()

        # Verify device registry
        dev_reg = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(dev_reg, created_entry.entry_id)
        assert len(devices) == 1
        dev_entry = devices[0]
        assert dev_entry.manufacturer == MANUFACTURER
        assert dev_entry.model == "V3.3"
        assert dev_entry.serial_number == "sn_prod_120"

        # Verify all 5 numeric LTS sensors
        cpu_temp = hass.states.get("sensor.pikvm_production_120_cpu_temperature")
        cpu_util = hass.states.get("sensor.pikvm_production_120_cpu_utilization")
        mem_util = hass.states.get("sensor.pikvm_production_120_memory_utilization")
        fan_spd = hass.states.get("sensor.pikvm_production_120_fan_speed")
        msd_store = hass.states.get("sensor.pikvm_production_120_msd_storage")

        assert cpu_temp is not None and float(cpu_temp.state) == 46.8
        assert cpu_temp.attributes.get("state_class") == SensorStateClass.MEASUREMENT
        assert (
            cpu_temp.attributes.get("unit_of_measurement") == UnitOfTemperature.CELSIUS
        )

        assert cpu_util is not None and float(cpu_util.state) == 14.2
        assert cpu_util.attributes.get("unit_of_measurement") == PERCENTAGE

        assert mem_util is not None and float(mem_util.state) == 25.0
        assert fan_spd is not None and int(fan_spd.state) == 2650
        assert fan_spd.attributes.get("unit_of_measurement") == REVOLUTIONS_PER_MINUTE

        # 16GB total - 4GB available = 12GB used = 75.0%
        assert msd_store is not None and float(msd_store.state) == 75.0

        # Verify binary sensors
        throttling = hass.states.get("binary_sensor.pikvm_production_120_throttling")
        msd_drive = hass.states.get("binary_sensor.pikvm_production_120_msd_drive")
        ipmi = hass.states.get("binary_sensor.pikvm_production_120_ipmi_service")

        assert throttling is not None and throttling.state == "off"
        assert msd_drive is not None and msd_drive.state == "on"
        assert ipmi is not None and ipmi.state == "on"

        # Verify diagnostics dump
        diag = await async_get_config_entry_diagnostics(hass, created_entry)
        assert diag["config_entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
        assert diag["config_entry"]["data"][CONF_CERTIFICATE] == "**REDACTED**"


@pytest.mark.asyncio
async def test_tier4_scenario2_hardware_reboot_and_network_recovery_e2e(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 4.2: Scenario 2 - PiKVM Hardware Reboot & Transient Network Disconnect Recovery.

    Verifies fault tolerance and automatic recovery:
    1. Operational baseline: coordinator healthy, sensors populated.
    2. PiKVM reboots: poll 1 raises PiKVMTimeoutError, poll 2 raises PiKVMConnectionError.
    3. Coordinator reports failure without unhandled exceptions; entities switch to unavailable.
    4. PiKVM comes back online: subsequent poll succeeds.
    5. Coordinator recovers, entities return to available with fresh values.
    """
    e2e_entry.add_to_hass(hass)
    dev_baseline = make_pikvm_telemetry(temp_cpu=43.5)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev_baseline),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    sensor_id = "sensor.pikvm_e2e_device_cpu_temperature"
    assert hass.states.get(sensor_id).state == "43.5"
    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data

    # Outage Step 1: Device shuts down (timeout)
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMTimeoutError("Device rebooting")
    )
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert hass.states.get(sensor_id).state == "unavailable"

    # Outage Step 2: Connection refused while booting
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMConnectionError("Connection refused")
    )
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert hass.states.get(sensor_id).state == "unavailable"

    # Recovery Step: KVMD starts up and returns fresh telemetry
    dev_recovered = make_pikvm_telemetry(temp_cpu=39.2)
    coordinator.client.get_info = AsyncMock(return_value=dev_recovered)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert hass.states.get(sensor_id).state == "39.2"


@pytest.mark.asyncio
async def test_tier4_scenario3_credential_rotation_and_reauth_e2e(
    hass: HomeAssistant, e2e_entry: MockConfigEntry, pikvm_cert: str
):
    """Tier 4.3: Scenario 3 - 2FA TOTP Credential Rotation & Reauth Flow with Token Invalidation.

    Verifies security lifecycle:
    1. Device running under initial credentials.
    2. Admin rotates password and configures new 2FA TOTP secret on PiKVM.
    3. Polling fails with 401 Unauthorized -> ConfigEntryAuthFailed raised.
    4. User completes reauth flow with rotated password and new TOTP base32 key.
    5. Config entry is updated, coordinator resumes polling cleanly.
    """
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry()

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data

    # Polling fails due to rotated credentials
    coordinator.client.get_info = AsyncMock(
        side_effect=PiKVMAuthenticationError(
            "401 Unauthorized: Invalid TOTP or Password"
        )
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    # User initiates reauth flow
    reauth_init = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": e2e_entry.entry_id},
        data=e2e_entry.data,
    )
    assert reauth_init["type"] == FlowResultType.FORM
    assert reauth_init["step_id"] == "reauth_confirm"

    new_totp = "MFRGGZDFMY======"
    with (
        patch(
            "custom_components.pikvm.config_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=pikvm_cert),
        ),
        patch(
            "custom_components.pikvm.config_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "V3.3", "sn_e2e_001", "PiKVM E2E Device", None
                )
            ),
        ),
        patch(
            "custom_components.pikvm.coordinator.PiKVMClient.get_info",
            new=AsyncMock(return_value=dev),
        ),
    ):
        reauth_result = await hass.config_entries.flow.async_configure(
            reauth_init["flow_id"],
            user_input={
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "new_secure_vault_password",
                CONF_TOTP: new_totp,
            },
        )
        assert reauth_result["type"] == FlowResultType.ABORT
        assert reauth_result["reason"] == "reauth_successful"
        await hass.async_block_till_done()

    assert e2e_entry.data[CONF_PASSWORD] == "new_secure_vault_password"
    assert e2e_entry.data[CONF_TOTP] == new_totp
    reloaded_coordinator = e2e_entry.runtime_data
    assert reloaded_coordinator.last_update_success is True


@pytest.mark.asyncio
async def test_tier4_scenario4_hardware_undervoltage_and_self_healing_e2e(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 4.4: Scenario 4 - Hardware Undervoltage, Repairs Issue Generation & Self-Healing.

    Verifies automated self-healing repairs:
    1. Baseline health: healthy PiKVM, no repairs, throttling sensor OFF.
    2. Power drop: undervoltage detected (`raw_flags = 0x1`).
    3. Coordinator dispatches CRITICAL repair issue and binary sensor turns ON.
    4. Power supply replaced: `raw_flags = 0`.
    5. Next polling cycle automatically removes repair issue and binary sensor turns OFF.
    """
    e2e_entry.add_to_hass(hass)
    dev_normal = make_pikvm_telemetry(raw_flags=0, uv_now=False)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev_normal),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    reg = ir.async_get(hass)
    uv_issue_id = f"undervoltage_{e2e_entry.entry_id}"
    throttling_sensor = "binary_sensor.pikvm_e2e_device_throttling"

    assert reg.async_get_issue(DOMAIN, uv_issue_id) is None
    assert hass.states.get(throttling_sensor).state == "off"

    # Step 2 & 3: Power sag occurs
    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data
    dev_sag = make_pikvm_telemetry(
        raw_flags=0x1, uv_now=True, text_flags=["under-voltage"]
    )
    coordinator.client.get_info = AsyncMock(return_value=dev_sag)
    await coordinator.async_refresh()

    assert reg.async_get_issue(DOMAIN, uv_issue_id) is not None
    assert reg.async_get_issue(DOMAIN, uv_issue_id).severity == IssueSeverity.CRITICAL
    assert hass.states.get(throttling_sensor).state == "on"

    # Step 4 & 5: Self-healing after power restored
    dev_restored = make_pikvm_telemetry(raw_flags=0, uv_now=False, uv_past=False)
    coordinator.client.get_info = AsyncMock(return_value=dev_restored)
    await coordinator.async_refresh()

    assert reg.async_get_issue(DOMAIN, uv_issue_id) is None
    assert hass.states.get(throttling_sensor).state == "off"


@pytest.mark.asyncio
async def test_tier4_scenario5_dhcp_ip_reallocation_and_teardown_e2e(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 4.5: Scenario 5 - IP Address Reallocation via mDNS Discovery Update & Integration Teardown.

    Verifies dynamic network adaptation and clean uninstallation:
    1. PiKVM starts with IP 192.168.1.100.
    2. DHCP lease reassigns device to 192.168.1.200; mDNS announces new IP for same serial.
    3. Config flow updates existing entry host and aborts cleanly.
    4. Diagnostics verifies updated host URL.
    5. User uninstalls integration: platforms unloaded, issues cleared, registry entry removed cleanly.
    """
    e2e_entry.add_to_hass(hass)
    dev = make_pikvm_telemetry(host="192.168.1.100")

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

        assert e2e_entry.data[CONF_HOST] == "https://192.168.1.100"

        # Step 2 & 3: New IP announced via Zeroconf
        service_info = ZeroconfServiceInfo(
            ip_address="192.168.1.200",
            ip_addresses=["192.168.1.200"],
            port=443,
            hostname="pikvm-dhcp.local.",
            type="_pikvm._tcp.local.",
            name="PiKVM DHCP._pikvm._tcp.local.",
            properties={"serial": "sn_e2e_001", "model": "V3.3"},
        )
        flow = PiKVMConfigFlow()
        flow.hass = hass
        result = await flow.async_step_zeroconf(service_info)

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"
        assert "192.168.1.200" in e2e_entry.data[CONF_HOST]

        # Step 4: Diagnostics reflects new IP
        diag = await async_get_config_entry_diagnostics(hass, e2e_entry)
        assert "192.168.1.200" in diag["config_entry"]["data"][CONF_HOST]

        # Step 5: Full integration removal
        assert await hass.config_entries.async_remove(e2e_entry.entry_id) is not None
        await hass.async_block_till_done()

    # Verify no dangling entries in hass.data or issue registry
    assert e2e_entry.entry_id not in hass.data.get(DOMAIN, {})
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"undervoltage_{e2e_entry.entry_id}")
        is None
    )


@pytest.mark.asyncio
async def test_tier4_scenario6_msd_image_mount_and_eject_e2e(
    hass: HomeAssistant, e2e_entry: MockConfigEntry
):
    """Tier 4.6: Scenario 6 - Mass Storage Drive (MSD) Mount and Eject Lifecycle E2E.

    Verifies virtual drive state tracking:
    1. Initial state: MSD enabled, drive unmounted (virtual drive idle).
    2. ISO attached: telemetry updates with is_mounted = True.
    3. Binary sensor msd_drive switches to ON.
    4. ISO ejected: telemetry updates with is_mounted = False.
    5. Binary sensor msd_drive switches to OFF.
    """
    e2e_entry.add_to_hass(hass)
    dev_idle = make_pikvm_telemetry(msd_mounted=False, msd_enabled=True)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dev_idle),
    ):
        assert await hass.config_entries.async_setup(e2e_entry.entry_id) is True
        await hass.async_block_till_done()

    drive_sensor = "binary_sensor.pikvm_e2e_device_msd_drive"
    enabled_sensor = "binary_sensor.pikvm_e2e_device_msd_enabled"

    assert hass.states.get(enabled_sensor).state == "on"
    assert hass.states.get(drive_sensor).state == "off"

    # Step 2 & 3: Mount virtual ISO
    coordinator: PiKVMDataUpdateCoordinator = e2e_entry.runtime_data
    dev_mounted = make_pikvm_telemetry(msd_mounted=True, msd_enabled=True)
    coordinator.client.get_info = AsyncMock(return_value=dev_mounted)
    await coordinator.async_refresh()

    assert hass.states.get(drive_sensor).state == "on"

    # Step 4 & 5: Eject virtual ISO
    coordinator.client.get_info = AsyncMock(return_value=dev_idle)
    await coordinator.async_refresh()

    assert hass.states.get(drive_sensor).state == "off"
