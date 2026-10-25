"""Tests for Vacuula vacuum platform."""

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
from custom_components.vacuula.vacuum import (
    FEATURE_CLEAN_AREA,
    Segment,
    VacuulaVacuumEntity,
)
from homeassistant.components.vacuum import (
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_vacuum_setup(hass: HomeAssistant):
    """Set up test vacuum environment."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 80},
        unique_id="v_test_vac",
        options={"default_mode": "turbo", "default_nav_mode": "normal"},
    )
    entry.add_to_hass(hass)

    api = VacuulaApiClient(host="127.0.0.1")
    api.async_start_cleaning = AsyncMock()
    api.async_pause_cleaning = AsyncMock()
    api.async_resume_cleaning = AsyncMock()
    api.async_stop_cleaning = AsyncMock()
    api.async_send_to_base = AsyncMock()
    api.async_find_me = AsyncMock()
    api.async_clean_spot = AsyncMock()

    coordinator = VacuulaDataUpdateCoordinator(hass, api, entry)
    coordinator.async_request_refresh = AsyncMock()

    zone1 = VacuulaZone(
        id="z_kitchen", name="Kitchen", map_id="m_ground", map_name="Ground Floor"
    )
    zone2 = VacuulaZone(
        id="z_living", name="Living Room", map_id="m_ground", map_name="Ground Floor"
    )

    robot_gen3 = VacuulaRobot(
        serial="SN-GEN3",
        name="Neato D7",
        model="Botvac D7 Connected",
        robot_type="gen3",
        connected=True,
        firmware="4.5.3",
        state=VacuulaRobotState(
            action_description="idle",
            battery_level=85,
            is_docked=True,
            is_charging=True,
        ),
        maps=[VacuulaMap(id="m_ground", name="Ground Floor", zones=[zone1, zone2])],
        zones={"m_ground:z_kitchen": zone1, "m_ground:z_living": zone2},
    )

    robot_gen4 = VacuulaRobot(
        serial="SN-GEN4",
        name="Neato D10",
        model="D10",
        robot_type="gen4",
        connected=True,
        firmware="1.8.0",
        state=VacuulaRobotState(
            action_description="docked",
            battery_level=100,
            is_docked=True,
        ),
        maps=[],
        zones={},
    )

    coordinator.data = VacuulaData(
        server_info=VacuulaServerInfo(version="1.0.0"),
        robots={"SN-GEN3": robot_gen3, "SN-GEN4": robot_gen4},
        server_status=True,
    )
    entry.runtime_data = coordinator

    return entry, coordinator, api, robot_gen3, robot_gen4


async def test_vacuum_properties_and_device_info(mock_vacuum_setup) -> None:
    """Test entity identification, device_info, and basic properties."""
    entry, coordinator, _, _, _ = mock_vacuum_setup
    vacuum = VacuulaVacuumEntity(coordinator, "SN-GEN3", entry)

    assert vacuum.unique_id == "SN-GEN3_vacuum"
    assert vacuum.has_entity_name is True
    assert vacuum.name is None

    device = vacuum.device_info
    assert (DOMAIN, "SN-GEN3") in device["identifiers"]
    assert device["via_device"] == (DOMAIN, f"server_{entry.entry_id}")
    assert device["manufacturer"] == "Neato Robotics"
    assert device["model"] == "Botvac D7 Connected"
    assert device["sw_version"] == "4.5.3"

    assert vacuum.available is True
    assert vacuum.battery_level == 85
    assert vacuum.fan_speed == "turbo"
    assert vacuum.fan_speed_list == ["turbo", "eco"]


async def test_vacuum_activity_states(mock_vacuum_setup) -> None:
    """Test mapping of robot states to VacuumActivity."""
    entry, coordinator, _, robot, _ = mock_vacuum_setup
    vacuum = VacuulaVacuumEntity(coordinator, "SN-GEN3", entry)

    # Docked
    robot.state.action_description = "idle"
    robot.state.is_docked = True
    assert vacuum.activity == VacuumActivity.DOCKED

    # Cleaning
    robot.state.action_description = "house_cleaning"
    robot.state.is_docked = False
    assert vacuum.activity == VacuumActivity.CLEANING

    # Returning / docking
    robot.state.action_description = "docking"
    assert vacuum.activity == VacuumActivity.RETURNING

    # Paused
    robot.state.action_description = "paused"
    assert vacuum.activity == VacuumActivity.PAUSED

    # Error
    robot.state.action_description = "idle"
    robot.state.error = "ui_alert_dust_bin_full"
    assert vacuum.activity == VacuumActivity.ERROR

    # Idle off dock
    robot.state.error = None
    robot.state.action_description = "idle"
    robot.state.is_docked = False
    assert vacuum.activity == VacuumActivity.IDLE


async def test_vacuum_supported_features(mock_vacuum_setup) -> None:
    """Test feature flags for Gen3 with zones vs Gen4 without zones."""
    entry, coordinator, _, _, _ = mock_vacuum_setup

    vacuum_gen3 = VacuulaVacuumEntity(coordinator, "SN-GEN3", entry)
    features_gen3 = vacuum_gen3.supported_features

    # Standard features
    assert features_gen3 & VacuumEntityFeature.START
    assert features_gen3 & VacuumEntityFeature.PAUSE
    assert features_gen3 & VacuumEntityFeature.STOP
    assert features_gen3 & VacuumEntityFeature.RETURN_HOME
    assert features_gen3 & VacuumEntityFeature.LOCATE
    assert features_gen3 & VacuumEntityFeature.BATTERY
    assert features_gen3 & VacuumEntityFeature.FAN_SPEED
    # Gen3 spot clean
    assert features_gen3 & VacuumEntityFeature.CLEAN_SPOT
    # Clean area when zones exist
    assert features_gen3 & FEATURE_CLEAN_AREA

    vacuum_gen4 = VacuulaVacuumEntity(coordinator, "SN-GEN4", entry)
    features_gen4 = vacuum_gen4.supported_features
    # Gen4 does not support spot clean in Neato app
    assert not (features_gen4 & VacuumEntityFeature.CLEAN_SPOT)
    # Gen4 without zones does not report FEATURE_CLEAN_AREA
    assert not (features_gen4 & FEATURE_CLEAN_AREA)


async def test_vacuum_commands(mock_vacuum_setup) -> None:
    """Test start, pause, resume, stop, return_to_base, locate, clean_spot."""
    entry, coordinator, api, robot, _ = mock_vacuum_setup
    vacuum = VacuulaVacuumEntity(coordinator, "SN-GEN3", entry)

    # Start cleaning
    robot.state.action_description = "idle"
    robot.state.is_docked = True
    await vacuum.async_start()
    api.async_start_cleaning.assert_called_once_with(
        "SN-GEN3", robot_type="gen3", mode="turbo", nav_mode="normal"
    )

    # Resume cleaning when paused
    robot.state.action_description = "paused"
    await vacuum.async_start()
    api.async_resume_cleaning.assert_called_once_with("SN-GEN3", "gen3")

    # Pause cleaning
    await vacuum.async_pause()
    api.async_pause_cleaning.assert_called_once_with("SN-GEN3", "gen3")

    # Stop cleaning
    await vacuum.async_stop()
    api.async_stop_cleaning.assert_called_once_with("SN-GEN3", "gen3")

    # Return home
    await vacuum.async_return_to_base()
    api.async_send_to_base.assert_called_once_with("SN-GEN3", "gen3")

    # Locate
    await vacuum.async_locate()
    api.async_find_me.assert_called_once_with("SN-GEN3", "gen3")

    # Spot clean
    await vacuum.async_clean_spot()
    api.async_clean_spot.assert_called_once_with(
        "SN-GEN3", robot_type="gen3", mode="turbo", nav_mode="normal"
    )


async def test_vacuum_fan_speed_change(mock_vacuum_setup) -> None:
    """Test changing fan speed / cleaning mode."""
    entry, coordinator, _, _, _ = mock_vacuum_setup
    vacuum = VacuulaVacuumEntity(coordinator, "SN-GEN3", entry)

    assert vacuum.fan_speed == "turbo"
    await vacuum.async_set_fan_speed("eco")
    assert vacuum.fan_speed == "eco"


async def test_clean_area_segments(mock_vacuum_setup) -> None:
    """Test native area cleaning segment retrieval and dispatch."""
    entry, coordinator, api, _, _ = mock_vacuum_setup
    vacuum = VacuulaVacuumEntity(coordinator, "SN-GEN3", entry)

    segments = await vacuum.async_get_segments()
    assert len(segments) == 2
    assert isinstance(segments[0], Segment)
    assert segments[0].id == "m_ground:z_kitchen"
    assert segments[0].name == "Kitchen"
    assert segments[0].group == "Ground Floor"

    # Clean selected segments
    await vacuum.async_clean_segments(["m_ground:z_kitchen", "m_ground:z_living"])
    api.async_start_cleaning.assert_called_with(
        "SN-GEN3",
        robot_type="gen3",
        mode="turbo",
        nav_mode="normal",
        map_id="m_ground",
        zone_ids=["z_kitchen", "z_living"],
    )
