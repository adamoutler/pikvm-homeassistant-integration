"""Tests for the PiKVM integration initialization and lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha import (
    PLATFORMS,
    _async_cleanup_devices,
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
    update_listener,
)
from custom_components.pikvm_ha.const import (
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        # Title updated with device name and clean host
        assert entry.title == "pikvm.local (192.168.1.108)"


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
        name="PiKVM",
    )
    assert legacy_device.name == "PiKVM"

    from homeassistant.exceptions import ConfigEntryNotReady
    from pikvm_aio import PiKVMConnectionError

    with patch(
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
        side_effect=PiKVMConnectionError("Cannot connect"),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    # Pre-emptive migration should have renamed the device in dev_reg before the refresh failed
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "PiKVM (192.168.1.105)"


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
        title="PiKVM",
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
        "custom_components.pikvm_ha.parse_host_port",
        side_effect=ValueError("Invalid host format"),
    ), patch(
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=mock_device_info),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert f"({expected_clean_host})" in entry.title


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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=device_data),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert entry.title == "PiKVM V4 Plus (192.168.1.100)"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info["name"] == "PiKVM V4 Plus (192.168.1.100)"


@pytest.mark.asyncio
async def test_async_setup_entry_naming_fallback_generic(hass, pikvm_cert):
    """Test device_name fallback to PiKVM ({clean_host}) (lines 141-142)."""
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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
        new=AsyncMock(return_value=device_data),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True
        assert entry.title == "PiKVM (192.168.1.100)"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.device_info["name"] == "PiKVM (192.168.1.100)"


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
        "custom_components.pikvm_ha.coordinator.PiKVMClient.get_info",
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



