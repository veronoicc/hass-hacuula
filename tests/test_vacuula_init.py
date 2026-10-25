"""Tests for Vacuula __init__ lifecycle and services."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.vacuula.api import VacuulaServerInfo
from custom_components.vacuula.const import (
    ATTR_COMMAND,
    ATTR_PARAMS,
    ATTR_SERIAL,
    ATTR_ZONE_NAME,
    DOMAIN,
    SERVICE_CLEAN_ZONE,
    SERVICE_DISMISS_ALERT,
    SERVICE_SEND_RAW_COMMAND,
)
from custom_components.vacuula.models import (
    VacuulaMap,
    VacuulaRobotState,
    VacuulaZone,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_vacuula_api():
    """Create a mock VacuulaApiClient."""
    with patch("custom_components.vacuula.VacuulaApiClient") as mock_cls:
        api = mock_cls.return_value
        api.base_url = "http://192.168.1.50:80"
        api.async_get_server_info = AsyncMock(
            return_value=VacuulaServerInfo(version="1.2.3")
        )
        api.async_get_robots = AsyncMock(
            return_value=[
                {
                    "serial": "ROBOT-SRV",
                    "name": "Hallway Robot",
                    "model": "D7",
                    "type": "gen3",
                    "connected": True,
                }
            ]
        )
        api.async_get_robot_state = AsyncMock(
            return_value=VacuulaRobotState(battery_level=80)
        )
        api.async_get_maps = AsyncMock(
            return_value=[VacuulaMap(id="map_srv", name="Floor 1")]
        )
        api.async_get_boundaries = AsyncMock(
            return_value=[
                VacuulaZone(
                    id="zone_hall",
                    name="Hallway",
                    map_id="map_srv",
                    map_name="Floor 1",
                )
            ]
        )
        api.async_start_cleaning = AsyncMock()
        api.async_dismiss_alert = AsyncMock()
        api.async_send_raw_command = AsyncMock()
        api.async_close = AsyncMock()
        api.async_listen_events = AsyncMock(side_effect=asyncio.CancelledError)
        yield api


async def test_setup_and_unload_entry(hass: HomeAssistant, mock_vacuula_api) -> None:
    """Test setting up and unloading Vacuula config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vacuula (192.168.1.50)",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 80},
        unique_id="vacuula_192.168.1.50_80",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id) is True
    await hass.async_block_till_done()

    # Verify hub registered in device registry
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"server_{entry.entry_id}")}
    )
    assert device is not None
    assert device.name == "Vacuula (192.168.1.50)"
    assert device.manufacturer == "Vacuula"
    assert device.model == "Vacuula Server"
    assert device.sw_version == "1.2.3"
    assert device.entry_type == dr.DeviceEntryType.SERVICE

    # Verify services registered
    assert hass.services.has_service(DOMAIN, SERVICE_CLEAN_ZONE)
    assert hass.services.has_service(DOMAIN, SERVICE_DISMISS_ALERT)
    assert hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND)

    # Test clean_zone service call
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONE,
        {
            ATTR_SERIAL: "ROBOT-SRV",
            ATTR_ZONE_NAME: "Hallway",
        },
        blocking=True,
    )
    mock_vacuula_api.async_start_cleaning.assert_called_once_with(
        serial="ROBOT-SRV",
        robot_type="gen3",
        mode="turbo",
        nav_mode="normal",
        map_id="map_srv",
        zone_ids=["zone_hall"],
    )

    # Test dismiss_alert service call
    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISMISS_ALERT,
        {ATTR_SERIAL: "ROBOT-SRV"},
        blocking=True,
    )
    mock_vacuula_api.async_dismiss_alert.assert_called_once_with("ROBOT-SRV")

    # Test send_raw_command service call
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        {
            ATTR_SERIAL: "ROBOT-SRV",
            ATTR_COMMAND: "getRobotState",
            ATTR_PARAMS: {"test": 1},
        },
        blocking=True,
    )
    mock_vacuula_api.async_send_raw_command.assert_called_once_with(
        "ROBOT-SRV", "getRobotState", {"test": 1}
    )

    # Unload entry
    assert await hass.config_entries.async_unload(entry.entry_id) is True
    await hass.async_block_till_done()
    mock_vacuula_api.async_close.assert_called_once()
