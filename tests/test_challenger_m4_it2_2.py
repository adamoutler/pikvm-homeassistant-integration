"""Adversarial challenger tests for Milestone 4 Iteration 2 (challenger_m4_it2_2).

Focus:
1. Adversarially fuzz device_entry.identifiers in async_remove_config_entry_device:
   - None
   - Empty collections (set, list, tuple)
   - Non-iterable objects (int, float, bool, NoneType, arbitrary object)
   - Malformed tuples (1-tuple, 3-tuple, 4-tuple, None items, empty strings, whitespace strings)
   - Verify NO unhandled exceptions and returns True for stale/corrupted devices.
2. Adversarially test active device preservation across casing and whitespace variations:
   - Uppercase/padded active serial vs lowercase device identifiers -> returns False.
   - Lowercase active serial vs uppercase/padded device identifiers -> returns False.
   - Tabs and newlines in serials -> returns False.
   - Domain casing variations (PIKVM, PIKVM_HA) -> returns False.
   - Devices with multiple identifiers -> returns False.
   - Unique_id fallback vs data[CONF_SERIAL] -> returns False.
   - Coordinator device_info identifiers -> returns False.
   - Ensure stale devices are allowed to be removed (returns True).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.pikvm import (
    async_remove_config_entry_device,
)
from custom_components.pikvm.const import (
    CONF_SERIAL,
    DOMAIN,
    LEGACY_DOMAIN,
)


@pytest.mark.asyncio
async def test_remove_device_fuzz_identifiers_none_and_empty(hass: HomeAssistant) -> None:
    """Challenge 1.1: Fuzz device_entry.identifiers with None and empty collections."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Active Device",
        unique_id="sn_fuzz_active",
        data={CONF_SERIAL: "sn_fuzz_active"},
    )
    entry.add_to_hass(hass)

    # 1. identifiers = None
    dev_none = MagicMock(spec=dr.DeviceEntry)
    dev_none.id = "dev_none"
    dev_none.name = "Device with None Identifiers"
    dev_none.identifiers = None
    assert await async_remove_config_entry_device(hass, entry, dev_none) is True

    # 2. identifiers = empty set
    dev_empty_set = MagicMock(spec=dr.DeviceEntry)
    dev_empty_set.id = "dev_empty_set"
    dev_empty_set.name = "Device with Empty Set Identifiers"
    dev_empty_set.identifiers = set()
    assert await async_remove_config_entry_device(hass, entry, dev_empty_set) is True

    # 3. identifiers = empty list
    dev_empty_list = MagicMock(spec=dr.DeviceEntry)
    dev_empty_list.id = "dev_empty_list"
    dev_empty_list.name = "Device with Empty List Identifiers"
    dev_empty_list.identifiers = []
    assert await async_remove_config_entry_device(hass, entry, dev_empty_list) is True

    # 4. identifiers = empty tuple
    dev_empty_tuple = MagicMock(spec=dr.DeviceEntry)
    dev_empty_tuple.id = "dev_empty_tuple"
    dev_empty_tuple.name = "Device with Empty Tuple Identifiers"
    dev_empty_tuple.identifiers = ()
    assert await async_remove_config_entry_device(hass, entry, dev_empty_tuple) is True


@pytest.mark.asyncio
async def test_remove_device_fuzz_non_iterable_objects(hass: HomeAssistant) -> None:
    """Challenge 1.2: Fuzz device_entry.identifiers with non-iterable objects."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Active Device",
        unique_id="sn_fuzz_active_non_iterable",
        data={CONF_SERIAL: "sn_fuzz_active_non_iterable"},
    )
    entry.add_to_hass(hass)

    fuzzed_non_iterables = [
        ("integer_positive", 12345),
        ("integer_zero", 0),
        ("integer_negative", -9999),
        ("float", 3.14159),
        ("boolean_true", True),
        ("boolean_false", False),
        ("none_type_class", type(None)),
        ("generic_object", object()),
    ]

    for label, bad_val in fuzzed_non_iterables:
        mock_dev = MagicMock(spec=dr.DeviceEntry)
        mock_dev.id = f"dev_{label}"
        mock_dev.name = f"Device {label}"
        mock_dev.identifiers = bad_val
        result = await async_remove_config_entry_device(hass, entry, mock_dev)
        assert result is True, f"Failed for non-iterable type {label}: {bad_val!r}"


@pytest.mark.asyncio
async def test_remove_device_fuzz_malformed_and_abnormal_tuples(hass: HomeAssistant) -> None:
    """Challenge 1.3: Fuzz device_entry.identifiers with malformed tuples and abnormal sequences."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Active Device",
        unique_id="sn_fuzz_active_tuples",
        data={CONF_SERIAL: "sn_fuzz_active_tuples"},
    )
    entry.add_to_hass(hass)

    malformed_elements = [
        ("single_item_tuple", (DOMAIN,)),
        ("3_tuple", (DOMAIN, "sn_fuzz_active_tuples", "extra_dimension")),
        ("4_tuple", (DOMAIN, "sn_fuzz_active_tuples", "dim3", "dim4")),
        ("none_both_tuple", (None, None)),
        ("none_domain_tuple", (None, "sn_fuzz_active_tuples")),
        ("none_serial_tuple", (DOMAIN, None)),
        ("empty_string_both", ("", "")),
        ("empty_string_domain", ("", "sn_fuzz_active_tuples")),
        ("empty_string_serial", (DOMAIN, "")),
        ("whitespace_both", ("   ", "   ")),
        ("whitespace_serial", (DOMAIN, "   ")),
        ("integer_elements", (123, 456)),
        ("boolean_elements", (True, False)),
        ("string_not_tuple", "just_a_string"),
    ]

    # Test each malformed item in a set
    for label, item in malformed_elements:
        mock_dev = MagicMock(spec=dr.DeviceEntry)
        mock_dev.id = f"dev_{label}"
        mock_dev.name = f"Device {label}"
        mock_dev.identifiers = {item}
        result = await async_remove_config_entry_device(hass, entry, mock_dev)
        assert result is True, f"Expected True for malformed item {label}: {item!r}"

    # Test all malformed items combined in a list
    mock_dev_combined = MagicMock(spec=dr.DeviceEntry)
    mock_dev_combined.id = "dev_combined_malformed"
    mock_dev_combined.name = "Combined Malformed Identifiers"
    mock_dev_combined.identifiers = [item for _, item in malformed_elements]
    assert await async_remove_config_entry_device(hass, entry, mock_dev_combined) is True


@pytest.mark.asyncio
async def test_remove_device_fuzz_missing_entry_attributes(hass: HomeAssistant) -> None:
    """Challenge 1.4: Verify device removal when device_entry is missing id or name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Active Device",
        unique_id="sn_active_test",
        data={CONF_SERIAL: "sn_active_test"},
    )
    entry.add_to_hass(hass)

    # 1. Device with name=None, id=None
    mock_dev_no_attrs = MagicMock(spec=dr.DeviceEntry)
    mock_dev_no_attrs.id = None
    mock_dev_no_attrs.name = None
    mock_dev_no_attrs.identifiers = {(DOMAIN, "stale_serial")}
    assert await async_remove_config_entry_device(hass, entry, mock_dev_no_attrs) is True

    # 2. Object with no attributes (falls back to getattr defaults)
    class BareDevice:
        def __init__(self) -> None:
            self.identifiers = {(DOMAIN, "stale_serial")}

    bare_dev = BareDevice()
    # Cast to dr.DeviceEntry for type safety
    assert await async_remove_config_entry_device(hass, entry, bare_dev) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_active_device_preservation_casing_and_whitespace_variations(
    hass: HomeAssistant,
) -> None:
    """Challenge 2.1: Stress test active device preservation across casing and whitespace variations."""
    # Active serial has uppercase, tabs, and spaces
    active_serial_variants = [
        "  SN_UPPER_PADDED_123  ",
        "\t\nSN_TABS_NEWLINES_456\n ",
        "sN_mIxEd_CaSe_789",
        "UPPERCASE_SERIAL",
        "lowercase_serial",
    ]

    for active_raw in active_serial_variants:
        norm_serial = active_raw.strip().lower()

        # Test with CONF_SERIAL in entry.data
        entry_data = MockConfigEntry(
            domain=DOMAIN,
            title="PiKVM Entry",
            unique_id=f"uid_{norm_serial}",
            data={CONF_SERIAL: active_raw},
        )
        entry_data.add_to_hass(hass)

        # Device identifiers in different variations
        device_ident_variants = [
            {(DOMAIN, norm_serial)},
            {(DOMAIN, active_raw)},
            {(DOMAIN, active_raw.upper())},
            {(DOMAIN, f"  {norm_serial}  ")},
            {(LEGACY_DOMAIN, norm_serial)},
            {(LEGACY_DOMAIN, f"  {norm_serial.upper()}  ")},
            {("PIKVM", norm_serial)},
            {("PIKVM_HA", norm_serial.upper())},
            {("unrelated_vendor", "other_id"), (DOMAIN, norm_serial)},
            [(DOMAIN, norm_serial)],  # list of tuples
            ((DOMAIN, norm_serial),),  # tuple of tuples
        ]

        for dev_ids in device_ident_variants:
            mock_dev = MagicMock(spec=dr.DeviceEntry)
            mock_dev.id = f"dev_{norm_serial}"
            mock_dev.name = "Active PiKVM Device"
            mock_dev.identifiers = dev_ids

            can_remove = await async_remove_config_entry_device(hass, entry_data, mock_dev)
            assert (
                can_remove is False
            ), f"Active device was mistakenly allowed to be purged! Active={active_raw!r}, Device={dev_ids!r}"

        # Test with unique_id fallback (when CONF_SERIAL is missing or None)
        entry_uid = MockConfigEntry(
            domain=DOMAIN,
            title="PiKVM UID Fallback Entry",
            unique_id=active_raw,
            data={},
        )
        entry_uid.add_to_hass(hass)

        mock_dev_uid = MagicMock(spec=dr.DeviceEntry)
        mock_dev_uid.id = f"dev_uid_{norm_serial}"
        mock_dev_uid.name = "Active PiKVM Device via UID"
        mock_dev_uid.identifiers = {(DOMAIN, norm_serial)}

        can_remove_uid = await async_remove_config_entry_device(hass, entry_uid, mock_dev_uid)
        assert (
            can_remove_uid is False
        ), f"Active device via unique_id fallback was mistakenly purged! UID={active_raw!r}"


@pytest.mark.asyncio
async def test_active_device_preservation_coordinator_device_info(
    hass: HomeAssistant,
) -> None:
    """Challenge 2.2: Test active device preservation when active serial is provided via coordinator device_info."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Coord Entry",
        unique_id="uid_coord_test",
        data={},
    )
    entry.add_to_hass(hass)

    mock_coord = MagicMock()
    mock_coord.device_info = {
        "identifiers": {(DOMAIN, "  COORD_SERIAL_XYZ  ")},
    }
    entry.runtime_data = mock_coord

    mock_dev = MagicMock(spec=dr.DeviceEntry)
    mock_dev.id = "dev_coord_active"
    mock_dev.name = "Active Coordinator Device"
    mock_dev.identifiers = {(DOMAIN, "coord_serial_xyz")}

    assert await async_remove_config_entry_device(hass, entry, mock_dev) is False


@pytest.mark.asyncio
async def test_stale_device_removal_allowed_unrelated_and_whitespace(
    hass: HomeAssistant,
) -> None:
    """Challenge 2.3: Verify that stale or truly unrelated devices are properly allowed to be removed (returns True)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiKVM Entry",
        unique_id="sn_real_active",
        data={CONF_SERIAL: "sn_real_active"},
    )
    entry.add_to_hass(hass)

    stale_scenarios = [
        ("different_serial_current_domain", {(DOMAIN, "sn_different_stale")}),
        ("different_serial_legacy_domain", {(LEGACY_DOMAIN, "sn_different_stale")}),
        ("different_domain_matching_serial", {("completely_unrelated_system", "sn_real_active")}),
        ("unrelated_everything", {("other_domain", "other_serial")}),
    ]

    for label, stale_identifiers in stale_scenarios:
        mock_dev = MagicMock(spec=dr.DeviceEntry)
        mock_dev.id = f"dev_{label}"
        mock_dev.name = f"Stale Device {label}"
        mock_dev.identifiers = stale_identifiers

        can_remove = await async_remove_config_entry_device(hass, entry, mock_dev)
        assert can_remove is True, f"Expected stale device {label} to return True, got {can_remove}"
