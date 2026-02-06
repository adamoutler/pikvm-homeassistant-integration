"""Tests for the PiKVM options flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pikvm_ha.cert_handler import (
    PiKVMResponse,
    fetch_serialized_cert,
    is_pikvm_device,
)
from custom_components.pikvm_ha.const import (
    CONF_CERTIFICATE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    CONF_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
)
from custom_components.pikvm_ha.options_flow import (
    PiKVMOptionsFlowHandler,
    handle_user_input,
)


@pytest.mark.asyncio
async def test_options_flow_updates_entry(hass):
    """Ensure that options flow updates credentials and certificate."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "https://old-host",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: DEFAULT_PASSWORD,
            CONF_SERIAL: "old-serial",
            CONF_CERTIFICATE: "old-cert",
        },
    )
    config_entry.add_to_hass(hass)

    new_user_input = {
        CONF_HOST: "pikvm.local",
        CONF_USERNAME: "new_admin",
        CONF_PASSWORD: "new_secret",
    }

    with patch(
        "custom_components.pikvm_ha.options_flow.get_translations",
        new=AsyncMock(return_value=lambda key, default: default),
    ):
        init_result = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )
        assert init_result["type"] == FlowResultType.FORM

        with (
            patch(
                "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
                new=AsyncMock(return_value="new-cert"),
            ),
            patch(
                "custom_components.pikvm_ha.options_flow.is_pikvm_device",
                new=AsyncMock(
                    return_value=PiKVMResponse(
                        True, "model", "pikvm-9999", "My PiKVM", None
                    )
                ),
            ),
        ):
            result = await hass.config_entries.options.async_configure(
                init_result["flow_id"],
                user_input=new_user_input,
            )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert config_entry.data[CONF_HOST] == "pikvm.local"
    assert config_entry.data[CONF_USERNAME] == "new_admin"
    assert config_entry.data[CONF_PASSWORD] == "new_secret"
    assert config_entry.data[CONF_SERIAL] == "pikvm-9999"
    assert config_entry.data[CONF_CERTIFICATE] == "new-cert"


@pytest.mark.asyncio
async def test_options_flow_localhost_name_fallback(hass):
    """Hostname fallback should not block a successful update."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "https://old-host",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: DEFAULT_PASSWORD,
            CONF_SERIAL: "old-serial",
            CONF_CERTIFICATE: "old-cert",
        },
    )
    config_entry.add_to_hass(hass)

    new_user_input = {
        CONF_HOST: "pikvm.local",
        CONF_USERNAME: "new_admin",
        CONF_PASSWORD: "new_secret",
    }

    flow = PiKVMOptionsFlowHandler(config_entry)
    flow.hass = hass

    with (
        patch(
            "custom_components.pikvm_ha.options_flow.get_translations",
            new=AsyncMock(return_value=lambda key, default: default),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value="new-cert"),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "model", "pikvm-1111", "localhost.localdomain", None
                )
            ),
        ),
    ):
        result = await flow.async_step_init(user_input=new_user_input)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_options_flow_cannot_fetch_cert(hass):
    """Show an error when the certificate cannot be fetched."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "https://old-host",
            CONF_USERNAME: DEFAULT_USERNAME,
            CONF_PASSWORD: DEFAULT_PASSWORD,
        },
    )
    config_entry.add_to_hass(hass)

    with patch(
        "custom_components.pikvm_ha.options_flow.get_translations",
        new=AsyncMock(return_value=lambda key, default: default),
    ):
        init_result = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )

        assert init_result["type"] == FlowResultType.FORM

        with patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value=None),
        ):
            result = await hass.config_entries.options.async_configure(
                init_result["flow_id"],
                user_input={
                    CONF_HOST: "pikvm.local",
                    CONF_USERNAME: "user",
                    CONF_PASSWORD: "pass",
                },
            )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_fetch_cert"


@pytest.mark.asyncio
async def test_options_flow_exception_error(hass):
    """Surface device provided exception codes as form errors."""
    config_entry = MockConfigEntry(domain=DOMAIN, data={})
    config_entry.add_to_hass(hass)

    with patch(
        "custom_components.pikvm_ha.options_flow.get_translations",
        new=AsyncMock(return_value=lambda key, default: default),
    ):
        init_result = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )

        with (
            patch(
                "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
                new=AsyncMock(return_value="cert"),
            ),
            patch(
                "custom_components.pikvm_ha.options_flow.is_pikvm_device",
                new=AsyncMock(
                    return_value=PiKVMResponse(
                        True, "model", "serial", "Exception_error", None
                    )
                ),
            ),
        ):
            result = await hass.config_entries.options.async_configure(
                init_result["flow_id"],
                user_input={
                    CONF_HOST: "pikvm.local",
                    CONF_USERNAME: "user",
                    CONF_PASSWORD: "pass",
                },
            )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "Exception_error"


@pytest.mark.asyncio
async def test_options_flow_existing_entry_updates(hass):
    """Updating an existing entry should reuse the stored config entry."""
    config_entry = MockConfigEntry(domain=DOMAIN, data={})
    config_entry.add_to_hass(hass)

    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pikvm-9999",
        data={
            CONF_HOST: "https://existing",
            CONF_USERNAME: "saved",
            CONF_PASSWORD: "secret",
        },
    )
    existing_entry.add_to_hass(hass)

    with patch(
        "custom_components.pikvm_ha.options_flow.get_translations",
        new=AsyncMock(return_value=lambda key, default: default),
    ):
        init_result = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )

        with (
            patch(
                "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
                new=AsyncMock(return_value="cert"),
            ),
            patch(
                "custom_components.pikvm_ha.options_flow.is_pikvm_device",
                new=AsyncMock(
                    return_value=PiKVMResponse(
                        True, "model", "pikvm-9999", "My PiKVM", None
                    )
                ),
            ),
            patch(
                "custom_components.pikvm_ha.options_flow.update_existing_entry",
                autospec=True,
            ) as update_mock,
        ):
            result = await hass.config_entries.options.async_configure(
                init_result["flow_id"],
                user_input={
                    CONF_HOST: "pikvm.local",
                    CONF_USERNAME: "user",
                    CONF_PASSWORD: "pass",
                },
            )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_options_flow_cannot_connect(hass):
    """Show connection error when device validation fails."""
    config_entry = MockConfigEntry(domain=DOMAIN, data={})
    config_entry.add_to_hass(hass)

    flow = PiKVMOptionsFlowHandler(config_entry)
    flow.hass = hass

    with (
        patch(
            "custom_components.pikvm_ha.options_flow.get_translations",
            new=AsyncMock(return_value=lambda key, default: default),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value="cert"),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(False, "model", "SERIAL", "My PiKVM", None)
            ),
        ),
    ):
        result = await flow.async_step_init(
            user_input={
                CONF_HOST: "pikvm.local",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


class _DummyFlow:
    """Simple helper to exercise handle_user_input in isolation."""

    def __init__(self, hass):
        self.hass = hass
        self.unique_ids = []
        self.created_entries = []

    async def async_set_unique_id(self, serial):
        self.unique_ids.append(serial)

    def _abort_if_unique_id_configured(self):
        return None

    def async_create_entry(self, title, data):
        entry = {"title": title, "data": data}
        self.created_entries.append(entry)
        return entry


@pytest.mark.asyncio
async def test_handle_user_input_creates_new_entry(hass):
    """handle_user_input should create a new entry when validation succeeds."""
    flow = _DummyFlow(hass)

    with (
        patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value="cert"),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(True, "model", "SERIAL123", None, None)
            ),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.update_existing_entry"
        ) as update_mock,
    ):
        result, errors = await handle_user_input(
            flow,
            {
                CONF_HOST: "pikvm.local",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            },
        )

    assert errors is None
    assert result["data"][CONF_HOST] == "https://pikvm.local"
    assert result["data"][CONF_SERIAL] == "SERIAL123"
    assert flow.unique_ids == ["SERIAL123"]
    update_mock.assert_not_called()


@pytest.mark.asyncio
async def test_handle_user_input_existing_entry(hass):
    """Existing entries are updated and reused."""
    flow = _DummyFlow(hass)

    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="SERIAL123",
        data={
            CONF_HOST: "https://existing",
            CONF_USERNAME: "saved",
            CONF_PASSWORD: "secret",
        },
    )
    existing_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value="cert"),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "model", "SERIAL123", "My PiKVM", None
                )
            ),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.update_existing_entry",
            autospec=True,
        ) as update_mock,
    ):
        outcome = await handle_user_input(
            flow,
            {
                CONF_HOST: "pikvm.local",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            },
        )

    if isinstance(outcome, tuple):
        result, errors = outcome
    else:
        result, errors = outcome, None

    assert result["data"] == {}
    assert errors is None
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_handle_user_input_exception_error(hass):
    """Exception-prefixed names surface as errors."""
    flow = _DummyFlow(hass)

    with (
        patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value="cert"),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(
                    True, "model", "SERIAL", "Exception_problem", None
                )
            ),
        ),
    ):
        result, errors = await handle_user_input(
            flow,
            {
                CONF_HOST: "pikvm.local",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            },
        )

    assert result is None
    assert errors["base"] == "Exception_problem"


@pytest.mark.asyncio
async def test_handle_user_input_missing_certificate(hass):
    """Missing certificates should abort with an error."""
    flow = _DummyFlow(hass)

    with patch(
        "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
        new=AsyncMock(return_value=None),
    ):
        result, errors = await handle_user_input(
            flow,
            {
                CONF_HOST: "pikvm.local",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            },
        )

    assert result is None
    assert errors["base"] == "cannot_fetch_cert"


@pytest.mark.asyncio
async def test_handle_user_input_cannot_connect(hass):
    """Connection failures should propagate as errors."""
    flow = _DummyFlow(hass)

    with (
        patch(
            "custom_components.pikvm_ha.options_flow.fetch_serialized_cert",
            new=AsyncMock(return_value="cert"),
        ),
        patch(
            "custom_components.pikvm_ha.options_flow.is_pikvm_device",
            new=AsyncMock(
                return_value=PiKVMResponse(False, None, None, None, None)
            ),
        ),
    ):
        result, errors = await handle_user_input(
            flow,
            {
                CONF_HOST: "pikvm.local",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            },
        )

    assert result is None
    assert errors["base"] == "cannot_connect"
