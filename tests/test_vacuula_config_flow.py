"""Tests for Vacuula config flow."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.vacuula.api import VacuulaServerInfo
from custom_components.vacuula.config_flow import (
    CannotConnect,
    InvalidAuth,
    InvalidServer,
)
from custom_components.vacuula.const import (
    CONF_DEFAULT_MODE,
    CONF_DEFAULT_NAV_MODE,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_flow_user_success(hass: HomeAssistant) -> None:
    """Test successful user step in config flow."""
    with (
        patch(
            "custom_components.vacuula.config_flow.validate_input",
            return_value=VacuulaServerInfo(version="1.0.0"),
        ),
        patch("custom_components.vacuula.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_PORT: 80,
                CONF_USE_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] is FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Vacuula (192.168.1.50)"
        assert result2["data"] == {
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 80,
            CONF_USE_SSL: False,
            CONF_VERIFY_SSL: True,
        }
        assert result2["result"].unique_id == "vacuula_192.168.1.50_80"


async def test_flow_user_cannot_connect(hass: HomeAssistant) -> None:
    """Test error handling when server cannot be reached."""
    with patch(
        "custom_components.vacuula.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_PORT: 80,
                CONF_USE_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_flow_user_invalid_auth(hass: HomeAssistant) -> None:
    """Test error handling on authentication error."""
    with patch(
        "custom_components.vacuula.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_PORT: 80,
            },
        )
        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_flow_user_invalid_server(hass: HomeAssistant) -> None:
    """Test error handling on invalid server response."""
    with patch(
        "custom_components.vacuula.config_flow.validate_input",
        side_effect=InvalidServer,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_PORT: 80,
            },
        )
        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_server"}


async def test_flow_duplicate_abort(hass: HomeAssistant) -> None:
    """Test aborting when unique ID is already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vacuula (192.168.1.50)",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 80},
        unique_id="vacuula_192.168.1.50_80",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.vacuula.config_flow.validate_input",
        return_value=VacuulaServerInfo(version="1.0.0"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_PORT: 80,
            },
        )
        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "already_configured"


async def test_flow_reconfigure_success(hass: HomeAssistant) -> None:
    """Test reconfiguring an existing entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vacuula (192.168.1.50)",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 80},
        unique_id="vacuula_192.168.1.50_80",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.vacuula.config_flow.validate_input",
            return_value=VacuulaServerInfo(version="1.0.0"),
        ),
        patch("custom_components.vacuula.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.60",
                CONF_PORT: 8080,
            },
        )
        assert result2["type"] is FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"
        assert entry.data[CONF_HOST] == "192.168.1.60"
        assert entry.data[CONF_PORT] == 8080
        assert entry.unique_id == "vacuula_192.168.1.60_8080"


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options flow configuration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vacuula (192.168.1.50)",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 80},
        unique_id="vacuula_192.168.1.50_80",
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 45,
            CONF_DEFAULT_MODE: "eco",
            CONF_DEFAULT_NAV_MODE: "deep",
        },
    )
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {
        CONF_SCAN_INTERVAL: 45,
        CONF_DEFAULT_MODE: "eco",
        CONF_DEFAULT_NAV_MODE: "deep",
    }
