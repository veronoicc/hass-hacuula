"""Tests for Vacuula select platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from custom_components.vacuula.api import VacuulaApiClient, VacuulaServerInfo
from custom_components.vacuula.const import DOMAIN
from custom_components.vacuula.coordinator import VacuulaDataUpdateCoordinator
from custom_components.vacuula.models import (
    VacuulaData,
    VacuulaMap,
    VacuulaRobot,
    VacuulaRobotState,
    VacuulaZone,
)
from custom_components.vacuula.select import (
    VacuulaCleaningCategorySelect,
    VacuulaNavigationModeSelect,
    VacuulaTargetZoneSelect,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_select_setup(hass: HomeAssistant):
    """Set up test environment for select entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 80},
        unique_id="v_test_select",
    )
    entry.add_to_hass(hass)

    api = VacuulaApiClient(host="127.0.0.1")
    coordinator = VacuulaDataUpdateCoordinator(hass, api, entry)
    coordinator.async_request_refresh = AsyncMock()

    zone1 = VacuulaZone(id="z1", name="Kitchen", map_id="m1", map_name="Main")
    zone2 = VacuulaZone(id="z2", name="Living Room", map_id="m1", map_name="Main")

    robot = VacuulaRobot(
        serial="ROBOT-SEL",
        name="Neato D7",
        model="D7",
        robot_type="gen3",
        connected=True,
        state=VacuulaRobotState(action_description="idle"),
        maps=[VacuulaMap(id="m1", name="Main", zones=[zone1, zone2])],
        zones={"m1:z1": zone1, "m1:z2": zone2},
        preferred_navigation_mode="normal",
        preferred_category=4,
        selected_zone="all",
    )

    coordinator.data = VacuulaData(
        server_info=VacuulaServerInfo(version="1.0.0"),
        robots={"ROBOT-SEL": robot},
        server_status=True,
    )
    entry.runtime_data = coordinator

    return entry, coordinator, robot


async def test_navigation_mode_select(hass: HomeAssistant, mock_select_setup) -> None:
    """Test navigation mode select entity."""
    entry, coordinator, robot = mock_select_setup
    sel = VacuulaNavigationModeSelect(coordinator, "ROBOT-SEL", entry)

    assert sel.unique_id == "ROBOT-SEL_navigation_mode"
    assert sel.current_option == "normal"
    assert "deep" in sel.options

    await sel.async_select_option("deep")
    assert robot.preferred_navigation_mode == "deep"
    assert robot.preferred_fan_speed == "turbo"


async def test_cleaning_category_select(hass: HomeAssistant, mock_select_setup) -> None:
    """Test cleaning category select entity."""
    entry, coordinator, robot = mock_select_setup
    sel = VacuulaCleaningCategorySelect(coordinator, "ROBOT-SEL", entry)

    assert sel.unique_id == "ROBOT-SEL_cleaning_category"
    assert sel.current_option == "map"

    await sel.async_select_option("house")
    assert robot.preferred_category == 2


async def test_target_zone_select(hass: HomeAssistant, mock_select_setup) -> None:
    """Test target zone select entity."""
    entry, coordinator, robot = mock_select_setup
    sel = VacuulaTargetZoneSelect(coordinator, "ROBOT-SEL", entry)

    assert sel.unique_id == "ROBOT-SEL_target_zone"
    assert sel.current_option == "all"
    assert "Kitchen" in sel.options
    assert "Living Room" in sel.options

    await sel.async_select_option("Kitchen")
    assert robot.selected_zone == "Kitchen"
