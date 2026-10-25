"""Tests for Vacuula coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from custom_components.vacuula.api import (
    VacuulaApiClient,
    VacuulaAuthError,
    VacuulaConnectionError,
    VacuulaServerInfo,
)
from custom_components.vacuula.const import DOMAIN, SIGNAL_NEW_ROBOT
from custom_components.vacuula.coordinator import VacuulaDataUpdateCoordinator
from custom_components.vacuula.models import (
    VacuulaMap,
    VacuulaRobotState,
    VacuulaZone,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_api():
    """Create a mock VacuulaApiClient."""
    api = VacuulaApiClient(host="127.0.0.1")
    api.async_get_server_info = AsyncMock(
        return_value=VacuulaServerInfo(version="1.5.0", timezone="UTC")
    )
    api.async_get_robots = AsyncMock(
        return_value=[
            {
                "serial": "ROBOT-GEN3",
                "name": "Botvac D7",
                "model": "D7 Connected",
                "type": "gen3",
                "connected": True,
                "firmware": "4.5.3-189",
            }
        ]
    )
    api.async_get_robot_state = AsyncMock(
        return_value=VacuulaRobotState(
            battery_level=90,
            is_docked=True,
            action_description="idle",
        )
    )
    api.async_get_maps = AsyncMock(
        return_value=[VacuulaMap(id="map_1", name="First Floor")]
    )
    api.async_get_boundaries = AsyncMock(
        return_value=[
            VacuulaZone(
                id="zone_kitchen",
                name="Kitchen",
                map_id="map_1",
                map_name="First Floor",
            )
        ]
    )
    api.async_get_map_detail = AsyncMock(return_value={})
    api.async_get_runs = AsyncMock(return_value=[])
    api.async_get_run_detail = AsyncMock(return_value={})
    return api


async def test_coordinator_initial_refresh(hass: HomeAssistant, mock_api) -> None:
    """Test coordinator successful update and robot discovery."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="v1")
    entry.add_to_hass(hass)

    discovered_robots = []

    def on_new_robot(robot):
        discovered_robots.append(robot)

    async_dispatcher_connect(
        hass, SIGNAL_NEW_ROBOT.format(entry.entry_id), on_new_robot
    )

    coordinator = VacuulaDataUpdateCoordinator(hass, mock_api, entry)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data.server_info.version == "1.5.0"
    assert "ROBOT-GEN3" in coordinator.data.robots

    robot = coordinator.data.robots["ROBOT-GEN3"]
    assert robot.name == "Botvac D7"
    assert robot.state.battery_level == 90
    assert len(robot.maps) == 1
    assert "map_1:zone_kitchen" in robot.zones

    # Check that dispatcher signal was emitted
    assert len(discovered_robots) == 1
    assert discovered_robots[0].serial == "ROBOT-GEN3"


async def test_coordinator_auth_failure(hass: HomeAssistant, mock_api) -> None:
    """Test auth failure raises ConfigEntryAuthFailed."""
    mock_api.async_get_server_info = AsyncMock(
        side_effect=VacuulaAuthError("Unauthorized")
    )

    entry = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="v1")
    entry.add_to_hass(hass)

    coordinator = VacuulaDataUpdateCoordinator(hass, mock_api, entry)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_connection_failure(hass: HomeAssistant, mock_api) -> None:
    """Test connection error raises UpdateFailed."""
    mock_api.async_get_server_info = AsyncMock(
        side_effect=VacuulaConnectionError("Server unreachable")
    )

    entry = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="v1")
    entry.add_to_hass(hass)

    coordinator = VacuulaDataUpdateCoordinator(hass, mock_api, entry)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_offline_robot(hass: HomeAssistant, mock_api) -> None:
    """Test offline robot handling."""
    mock_api.async_get_robots = AsyncMock(
        return_value=[
            {
                "serial": "ROBOT-OFFLINE",
                "name": "Botvac D5",
                "model": "D5",
                "type": "gen3",
                "connected": False,
            }
        ]
    )

    entry = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="v1")
    entry.add_to_hass(hass)

    coordinator = VacuulaDataUpdateCoordinator(hass, mock_api, entry)
    await coordinator.async_refresh()

    robot = coordinator.data.robots["ROBOT-OFFLINE"]
    assert robot.connected is False
    assert robot.state.action_description == "disconnected"


async def test_coordinator_sse_events(hass: HomeAssistant, mock_api) -> None:
    """Test processing SSE real-time events."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="v1")
    entry.add_to_hass(hass)

    coordinator = VacuulaDataUpdateCoordinator(hass, mock_api, entry)
    await coordinator.async_refresh()

    robot = coordinator.data.robots["ROBOT-GEN3"]
    assert robot.state.battery_level == 90

    # Simulate SSE state_changed
    sse_state_event = {
        "event": "state_changed",
        "serial": "ROBOT-GEN3",
        "data": {
            "version": 1,
            "data": {
                "state": 2,
                "action": 1,
                "details": {"charge": 75, "isCharging": False, "isDocked": False},
            },
        },
    }
    await coordinator.async_handle_sse_event(sse_state_event)
    assert robot.state.battery_level == 75
    assert robot.state.action_description == "house_cleaning"

    # Simulate disconnected event
    await coordinator.async_handle_sse_event(
        {"event": "disconnected", "serial": "ROBOT-GEN3"}
    )
    assert robot.connected is False

    # Simulate reconnected event
    await coordinator.async_handle_sse_event(
        {"event": "connected", "serial": "ROBOT-GEN3"}
    )
    assert robot.connected is True


async def test_coordinator_refresh_robot_maps(hass: HomeAssistant, mock_api) -> None:
    """Test explicitly refreshing maps and zones."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="v1")
    entry.add_to_hass(hass)

    coordinator = VacuulaDataUpdateCoordinator(hass, mock_api, entry)
    await coordinator.async_refresh()

    # Now change mock maps and trigger refresh
    mock_api.async_get_maps = AsyncMock(
        return_value=[
            VacuulaMap(id="map_2", name="Second Floor"),
        ]
    )
    mock_api.async_get_boundaries = AsyncMock(
        return_value=[
            VacuulaZone(
                id="zone_bedroom",
                name="Master Bedroom",
                map_id="map_2",
                map_name="Second Floor",
            )
        ]
    )

    await coordinator.async_refresh_robot_maps("ROBOT-GEN3")
    robot = coordinator.data.robots["ROBOT-GEN3"]
    assert len(robot.maps) == 1
    assert robot.maps[0].name == "Second Floor"
    assert "map_2:zone_bedroom" in robot.zones
