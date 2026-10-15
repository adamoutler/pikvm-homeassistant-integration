"""Tests for the PiKVM options flow."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm.config_flow import PiKVMConfigFlow
from custom_components.pikvm.const import DOMAIN
from custom_components.pikvm.options_flow import (
    DEFAULT_SCAN_INTERVAL,
    PiKVMOptionsFlowHandler,
)


@pytest.mark.asyncio
async def test_options_flow_init_shows_form(hass):
    """Test options flow initial step shows form with default scan interval."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100"},
        options={},
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_flow_init_with_existing_options(hass):
    """Test options flow pre-populates existing options scan interval."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100"},
        options={CONF_SCAN_INTERVAL: 45},
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_flow_init_with_data_scan_interval(hass):
    """Test options flow falls back to data scan interval if options is empty."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100", CONF_SCAN_INTERVAL: 60},
        options={},
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_flow_submits_valid_data(hass):
    """Test submitting valid scan interval creates options entry."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100"},
        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SCAN_INTERVAL: 120},
    )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {CONF_SCAN_INTERVAL: 120}


@pytest.mark.asyncio
async def test_get_options_flow(hass):
    """Test PiKVMConfigFlow.async_get_options_flow returns handler."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100"},
    )
    config_entry.add_to_hass(hass)

    flow = PiKVMConfigFlow.async_get_options_flow(config_entry)
    assert isinstance(flow, PiKVMOptionsFlowHandler)
    assert flow.config_entry == config_entry
