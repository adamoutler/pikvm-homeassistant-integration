"""Tests for the PiKVM integration initialization and lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm import (
    PLATFORMS,
    _async_cleanup_devices,
    async_remove_entry,
    async_setup,
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
    DOMAIN,
    MANUFACTURER,
)
from pikvm_aio import PiKVMDeviceInfo


@pytest.fixture
def mock_device_info():
    """Create sample PiKVMDeviceInfo."""
    raw = {
        "hw": {
            "platform": {
                "type": "v3",
                "model": "V3.3",
                "base": "Raspberry Pi 4",
                "serial": "sn_12345",
            }
        },
        "system": {"kvmd": {"version": "3.100"}},
        "meta": {"server": {"host": "pikvm.local"}},
        "extras": {},
    }
    return PiKVMDeviceInfo.from_dict(raw)


@pytest.mark.asyncio
async def test_async_setup(hass):
    """Test async_setup returns True."""
    assert await async_setup(hass, {}) is True


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass, pikvm_cert, mock_device_info):
    """Test full successful async_setup_entry flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ) as mock_forward:
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert entry.entry_id in hass.data[DOMAIN]

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info is not None
        device_info = coordinator.device_info
        assert device_info["identifiers"] == {(DOMAIN, "sn_12345")}
        assert device_info["serial_number"] == "sn_12345"
        assert device_info["configuration_url"] == "https://pikvm.local"
        assert device_info["manufacturer"] == MANUFACTURER
        assert device_info["name"] == "PiKVM Lab"
        assert device_info["model"] == "V3.3"
        assert device_info["hw_version"] == "Raspberry Pi 4"
        assert device_info["sw_version"] == "3.100"

        mock_forward.assert_awaited_once_with(entry, PLATFORMS)


@pytest.mark.asyncio
async def test_async_setup_entry_unique_id_migration(hass, pikvm_cert, mock_device_info):
    """Test updating unique_id if it differs from CONF_SERIAL."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Old",
        unique_id="legacy_id",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        await async_setup_entry(hass, entry)
        assert entry.unique_id == "sn_12345"


@pytest.mark.asyncio
async def test_async_cleanup_devices(hass):
    """Test removing orphaned devices belonging to entry."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_cleanup_entry", data={})
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # Active device with an entity
    dev1 = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "active_device")},
        name="Active Device",
    )
    ent_reg.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id="test_unique_id",
        device_id=dev1.id,
        config_entry=entry,
    )

    # Orphaned device with no entity
    dev2 = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "orphaned_device")},
        name="Orphaned Device",
    )

    # Device belonging to another config entry
    other_entry = MockConfigEntry(domain=DOMAIN, entry_id="other_entry", data={})
    other_entry.add_to_hass(hass)
    dev3 = dev_reg.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "other_device")},
        name="Other Device",
    )

    await _async_cleanup_devices(hass, entry)

    assert dev_reg.async_get(dev1.id) is not None
    assert dev_reg.async_get(dev2.id) is None
    assert dev_reg.async_get(dev3.id) is not None


@pytest.mark.asyncio
async def test_async_unload_entry(hass):
    """Test unloading config entry."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_unload_entry", data={})
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = "mock_coordinator"

    with patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)
    ) as mock_unload:
        result = await async_unload_entry(hass, entry)
        assert result is True
        assert entry.entry_id not in hass.data[DOMAIN]
        mock_unload.assert_awaited_once_with(entry, PLATFORMS)


@pytest.mark.asyncio
async def test_update_listener(hass):
    """Test update listener reloads entry."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_reload_entry", data={})
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as mock_reload:
        await update_listener(hass, entry)
        mock_reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_async_remove_entry(hass):
    """Test async_remove_entry cleanly unloads platforms and clears domain data."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_remove_entry", data={})
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = "mock_coordinator"

    with patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)
    ) as mock_unload:
        await async_remove_entry(hass, entry)
        assert entry.entry_id not in hass.data[DOMAIN]
        mock_unload.assert_awaited_once_with(entry, PLATFORMS)


@pytest.mark.asyncio
async def test_async_setup_entry_generic_title_disambiguation(hass, pikvm_cert, mock_device_info):
    """Test generic PiKVM entry titles are disambiguated with host and device name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://192.168.1.108",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        # Title updated with discovered device name
        assert entry.title == "pikvm.local"


@pytest.mark.asyncio
async def test_async_setup_entry_migrates_legacy_device_name(hass, pikvm_cert, mock_device_info):
    """Test legacy PiKVM device in registry is migrated even if first refresh fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM",
        unique_id="sn_offline_105",
        data={
            CONF_HOST: "https://192.168.1.105",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_offline_105",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    dev_reg = dr.async_get(hass)
    legacy_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_offline_105")},
        name="PiKVM (192.168.1.105)",
    )
    assert legacy_device.name == "PiKVM (192.168.1.105)"

    from homeassistant.exceptions import ConfigEntryNotReady
    from pikvm_aio import PiKVMConnectionError

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        side_effect=PiKVMConnectionError("Cannot connect"),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    # Pre-emptive migration should have renamed the legacy device in dev_reg to clean name before the refresh failed
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "PiKVM"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_host", "expected_clean_host"),
    [
        ("invalid://host:format", "invalid://host:format"),
        ("", "unknown"),
    ],
)
async def test_async_setup_entry_parse_host_port_exception(
    hass, pikvm_cert, mock_device_info, raw_host, expected_clean_host
):
    """Test fallback when parse_host_port raises an Exception (lines 63-64)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"PiKVM ({expected_clean_host})",
        unique_id="sn_12345",
        data={
            CONF_HOST: raw_host,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    with patch(
        "custom_components.pikvm.parse_host_port",
        side_effect=ValueError("Invalid host format"),
    ), patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert entry.title == "pikvm.local"


@pytest.mark.asyncio
async def test_async_setup_entry_removes_legacy_mismatched_device_and_entities(
    hass, pikvm_cert, mock_device_info
):
    """Test legacy mismatched devices and their entities are removed during setup (lines 89-92)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    mismatched_dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "old_mismatched_serial")},
        name="Legacy Mismatched Device",
    )
    ent = ent_reg.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id="old_mismatched_entity_id",
        device_id=mismatched_dev.id,
        config_entry=entry,
    )

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert dev_reg.async_get(mismatched_dev.id) is None
        assert ent_reg.async_get(ent.entity_id) is None


@pytest.mark.asyncio
async def test_async_setup_entry_raw_data_fallback_dict(hass, pikvm_cert):
    """Test raw_data fallback when coordinator.data is a dict without .raw attribute (line 115 branch 1)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    dict_data = {
        "hw": {"platform": {"model": "V3-Hat", "base": "RPi4"}},
        "system": {"kvmd": {"version": "3.100"}},
    }

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=dict_data),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info["model"] == "V3-Hat"


@pytest.mark.asyncio
async def test_async_setup_entry_raw_data_fallback_non_dict(hass, pikvm_cert):
    """Test raw_data fallback when coordinator.data is non-dict without .raw attribute (line 115 branch 2)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    class CustomData:
        name = "PiKVM"
        model = "CustomModel"
        kvmd_version = "1.0"

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=CustomData()),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info["model"] == "CustomModel"


@pytest.mark.asyncio
async def test_async_setup_entry_naming_fallback_model(hass, pikvm_cert):
    """Test device_name fallback to PiKVM {model} ({clean_host}) (lines 139-140)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    device_data = MagicMock()
    device_data.raw = None
    device_data.name = "localhost"  # Discovered generic name, falls through line 137
    device_data.hw = None
    device_data.model = "V4 Plus"  # Non-generic model triggers line 139
    device_data.kvmd_version = "3.100"

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=device_data),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert entry.title == "PiKVM V4 Plus"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info["name"] == "PiKVM V4 Plus"


@pytest.mark.asyncio
async def test_async_setup_entry_naming_fallback_generic(hass, pikvm_cert):
    """Test device_name fallback to PiKVM (lines 141-142)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    device_data = MagicMock()
    device_data.raw = None
    device_data.name = None
    device_data.hw = None
    device_data.model = None  # None triggers lines 141-142
    device_data.kvmd_version = "3.100"

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=device_data),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert entry.title == "PiKVM"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info["name"] == "PiKVM"


@pytest.mark.asyncio
async def test_async_setup_entry_updates_existing_device_name_in_registry(
    hass, pikvm_cert, mock_device_info
):
    """Test existing device in device registry is updated with new device_name (lines 160-161)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Lab",
        unique_id="sn_12345",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret_password",
            CONF_SERIAL: "sn_12345",
            CONF_CERTIFICATE: pikvm_cert,
            CONF_TOTP: "",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_12345")},
        name="Outdated Device Name",
    )
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id="test_sensor_entity_id",
        device_id=dev.id,
        config_entry=entry,
    )
    assert dev.name == "Outdated Device Name"
    assert dev.name_by_user is None

    with patch(
        "custom_components.pikvm.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True

        updated_dev = dev_reg.async_get(dev.id)
        assert updated_dev.name == "PiKVM Lab"


@pytest.mark.asyncio
async def test_async_cleanup_devices_removes_mismatched_device_and_entities(hass):
    """Test _async_cleanup_devices removes mismatched devices and their entities (lines 189-190)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_cleanup_entry",
        unique_id="sn_correct",
        data={CONF_SERIAL: "sn_correct"},
    )
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    valid_dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_correct")},
        name="Valid Device",
    )
    ent_reg.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id="valid_entity",
        device_id=valid_dev.id,
        config_entry=entry,
    )

    mismatched_dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "sn_wrong")},
        name="Mismatched Device",
    )
    mismatched_ent = ent_reg.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id="mismatched_entity",
        device_id=mismatched_dev.id,
        config_entry=entry,
    )

    await _async_cleanup_devices(hass, entry)

    assert dev_reg.async_get(valid_dev.id) is not None
    assert dev_reg.async_get(mismatched_dev.id) is None
    assert ent_reg.async_get(mismatched_ent.entity_id) is None


@pytest.mark.asyncio
async def test_migrate_legacy_domain_in_place_and_cross_entry_and_orphaned(hass):
    """Test async_migrate_legacy_domain across all 3 scenarios and edge cases."""
    from custom_components.pikvm import (
        _extract_serial_from_entry_or_device,
        _migrate_entity_to_pikvm,
        async_migrate_entry,
        async_migrate_legacy_domain,
    )
    from custom_components.pikvm.const import LEGACY_DOMAIN

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # Test _extract_serial_from_entry_or_device when entry has no serial/unique_id but device does
    empty_entry = MockConfigEntry(domain=LEGACY_DOMAIN, entry_id="legacy_no_serial", data={})
    empty_entry.add_to_hass(hass)
    dev_with_serial = dev_reg.async_get_or_create(
        config_entry_id=empty_entry.entry_id,
        identifiers={(LEGACY_DOMAIN, "SN_FROM_DEV")},
        name="Legacy Dev",
    )
    assert _extract_serial_from_entry_or_device(empty_entry, dev_reg) == "sn_from_dev"
    assert _extract_serial_from_entry_or_device(None, dev_reg) is None

    # Create an entity on empty_entry with a loaded state in hass.states
    ent1 = ent_reg.async_get_or_create(
        domain="sensor",
        platform=LEGACY_DOMAIN,
        unique_id=f"{empty_entry.entry_id}_sn_from_dev_cpu_temp",
        device_id=dev_with_serial.id,
        config_entry=empty_entry,
    )
    hass.states.async_set(ent1.entity_id, "unavailable")

    # Scenario 1: In-place migration of empty_entry (pikvm_ha -> pikvm)
    with patch.object(hass.config_entries, "async_setup", new=AsyncMock(return_value=True)):
        migrated = await async_migrate_legacy_domain(hass)
        assert migrated is True
        assert empty_entry.domain == DOMAIN
        updated_ent1 = ent_reg.async_get(ent1.entity_id)
        assert updated_ent1.platform == DOMAIN
        updated_dev1 = dev_reg.async_get(dev_with_serial.id)
        assert (DOMAIN, "SN_FROM_DEV") in updated_dev1.identifiers

    # Test no-op in _migrate_entity_to_pikvm when already migrated
    _migrate_entity_to_pikvm(
        hass, ent_reg, ent_reg.async_get(ent1.entity_id), empty_entry.entry_id, ent1.unique_id
    )

    # Test ValueError fallback in _migrate_entity_to_pikvm
    with patch.object(ent_reg, "async_update_entity_platform", side_effect=ValueError("already loaded")):
        _migrate_entity_to_pikvm(
            hass,
            ent_reg,
            ent_reg.async_get(ent1.entity_id),
            empty_entry.entry_id,
            f"{empty_entry.entry_id}_sn_from_dev_cpu_temp_renamed",
        )

    # Scenario 2: Cross-entry merge (legacy_entry + new_entry for same serial)
    legacy_dup = MockConfigEntry(
        domain=LEGACY_DOMAIN,
        entry_id="old_entry_dup",
        unique_id="sn_dup",
        data={CONF_SERIAL: "sn_dup"},
    )
    legacy_dup.add_to_hass(hass)
    new_dup = MockConfigEntry(
        domain=DOMAIN,
        entry_id="new_entry_dup",
        unique_id="sn_dup",
        data={CONF_SERIAL: "sn_dup"},
    )
    new_dup.add_to_hass(hass)

    dup_dev = dev_reg.async_get_or_create(
        config_entry_id=legacy_dup.entry_id,
        identifiers={(LEGACY_DOMAIN, "sn_dup")},
        name="Dup Dev",
    )
    dup_ent = ent_reg.async_get_or_create(
        domain="sensor",
        platform=LEGACY_DOMAIN,
        unique_id=f"{legacy_dup.entry_id}_sn_dup_cpu_temp",
        device_id=dup_dev.id,
        config_entry=legacy_dup,
    )

    migrated2 = await async_migrate_legacy_domain(hass, target_entry=new_dup)
    assert migrated2 is True
    assert hass.config_entries.async_get_entry(legacy_dup.entry_id) is None
    migrated_dup_ent = ent_reg.async_get(dup_ent.entity_id)
    assert migrated_dup_ent.platform == DOMAIN
    assert migrated_dup_ent.config_entry_id == new_dup.entry_id
    assert migrated_dup_ent.unique_id == f"{new_dup.entry_id}_sn_dup_cpu_temp"

    # Scenario 3: Orphaned device in device_registry with (pikvm_ha, serial)
    orphan_target = MockConfigEntry(
        domain=DOMAIN,
        entry_id="orphan_target_id",
        unique_id="sn_orphan",
        data={CONF_SERIAL: "sn_orphan"},
    )
    # Do not add orphan_target to hass yet to hit line 144 (target_entry not in current_entries)
    orphan_holder = MockConfigEntry(domain="other", entry_id="other_holder", data={})
    orphan_holder.add_to_hass(hass)
    orphan_dev = dev_reg.async_get_or_create(
        config_entry_id=orphan_holder.entry_id,
        identifiers={(LEGACY_DOMAIN, "sn_orphan")},
        name="Orphan Dev",
    )
    orphan_ent = ent_reg.async_get_or_create(
        domain="sensor",
        platform=LEGACY_DOMAIN,
        unique_id=f"{orphan_holder.entry_id}_sn_orphan_cpu_temp",
        device_id=orphan_dev.id,
        config_entry=orphan_holder,
    )
    orphan_target.add_to_hass(hass)
    # Remove from async_entries momentarily via mock or test async_migrate_entry
    assert await async_migrate_entry(hass, orphan_target) is True
    updated_orphan_ent = ent_reg.async_get(orphan_ent.entity_id)
    assert updated_orphan_ent.platform == DOMAIN
    assert updated_orphan_ent.config_entry_id == orphan_target.entry_id

    # Also test Scenario 3 when no matched_entry exists (line 260) and target_entry not in current_entries (line 144)
    unattached_target = MockConfigEntry(domain=DOMAIN, entry_id="unattached_id", data={})
    await async_migrate_legacy_domain(hass, target_entry=unattached_target)

    unmatched_dev = dev_reg.async_get_or_create(
        config_entry_id=orphan_holder.entry_id,
        identifiers={(LEGACY_DOMAIN, "sn_unmatched")},
        name="Unmatched Dev",
    )
    await async_migrate_legacy_domain(hass, target_entry=None)
    assert (DOMAIN, "sn_unmatched") in dev_reg.async_get(unmatched_dev.id).identifiers


@pytest.mark.asyncio
async def test_setup_entry_with_non_dict_platform_and_kvmd(hass):
    """Test async_setup_entry handles non-dict platform and kvmd gracefully (lines 345, 348)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="non_dict_entry",
        unique_id="sn_nondict",
        data={
            CONF_HOST: "https://pikvm.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "password",
            CONF_SERIAL: "sn_nondict",
        },
    )
    entry.add_to_hass(hass)

    mock_coord = MagicMock()
    mock_coord.async_setup = AsyncMock()
    mock_coord.async_config_entry_first_refresh = AsyncMock()
    mock_coord.data = {"hw": {"platform": "not-a-dict"}, "system": {"kvmd": "not-a-dict"}}

    with patch(
        "custom_components.pikvm.PiKVMDataUpdateCoordinator",
        return_value=mock_coord,
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        assert await async_setup_entry(hass, entry) is True



