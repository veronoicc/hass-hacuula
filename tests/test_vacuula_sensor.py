"""Tests for Vacuula sensors, binary sensors, buttons, and switches."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from custom_components.vacuula.api import VacuulaApiClient, VacuulaServerInfo
from custom_components.vacuula.binary_sensor import (
    ROBOT_BINARY_SENSORS,
    SERVER_BINARY_SENSORS,
    VacuulaRobotBinarySensor,
    VacuulaServerBinarySensor,
)
from custom_components.vacuula.button import (
    ROBOT_BUTTONS,
    VacuulaRobotButton,
)
from custom_components.vacuula.const import DOMAIN
from custom_components.vacuula.coordinator import VacuulaDataUpdateCoordinator
from custom_components.vacuula.models import (
    VacuulaData,
    VacuulaRobot,
    VacuulaRobotState,
)
from custom_components.vacuula.sensor import (
    ROBOT_SENSORS,
    SERVER_SENSORS,
    VacuulaRobotSensor,
    VacuulaServerSensor,
)
from custom_components.vacuula.switch import (
    SCHEDULE_SWITCH_DESCRIPTION,
    VacuulaRobotScheduleSwitch,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_sensor_setup(hass: HomeAssistant):
    """Set up test environment for sensors, buttons, switches."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 80},
        unique_id="v_test_sensor",
    )
    entry.add_to_hass(hass)

    api = VacuulaApiClient(host="127.0.0.1")
    api.async_find_me = AsyncMock()
    api.async_dismiss_alert = AsyncMock()
    api.async_set_schedule = AsyncMock()

    coordinator = VacuulaDataUpdateCoordinator(hass, api, entry)
    coordinator.async_request_refresh = AsyncMock()

    robot_gen3 = VacuulaRobot(
        serial="ROBOT-3",
        name="Neato D7",
        model="D7",
        robot_type="gen3",
        connected=True,
        firmware="4.5.3",
        state=VacuulaRobotState(
            action_description="house_cleaning",
            battery_level=92,
            is_charging=False,
            is_bin_full=True,
            schedule_enabled=True,
            error=None,
        ),
    )

    robot_gen4 = VacuulaRobot(
        serial="ROBOT-4",
        name="Neato D10",
        model="D10",
        robot_type="gen4",
        connected=False,
        firmware="1.8.0",
        state=VacuulaRobotState(
            action_description="idle",
            battery_level=40,
            is_charging=True,
            is_bin_full=False,
            schedule_enabled=False,
            error="brush_stuck",
        ),
    )

    coordinator.data = VacuulaData(
        server_info=VacuulaServerInfo(version="2.1.0"),
        robots={"ROBOT-3": robot_gen3, "ROBOT-4": robot_gen4},
        server_status=True,
    )
    entry.runtime_data = coordinator

    return entry, coordinator, api, robot_gen3, robot_gen4


async def test_server_sensors(mock_sensor_setup) -> None:
    """Test server-level diagnostic sensors."""
    entry, coordinator, _, _, _ = mock_sensor_setup

    s_version = VacuulaServerSensor(coordinator, entry, SERVER_SENSORS[0])
    assert s_version.unique_id == f"server_{entry.entry_id}_server_version"
    assert s_version.native_value == "2.1.0"

    s_robots = VacuulaServerSensor(coordinator, entry, SERVER_SENSORS[1])
    # 1 connected robot out of 2
    assert s_robots.native_value == 1


async def test_robot_sensors(mock_sensor_setup) -> None:
    """Test per-robot telemetry sensors."""
    entry, coordinator, _, _, _ = mock_sensor_setup

    # Battery sensor
    s_battery = VacuulaRobotSensor(coordinator, "ROBOT-3", entry, ROBOT_SENSORS[0])
    assert s_battery.unique_id == "ROBOT-3_battery"
    assert s_battery.native_value == 92
    assert s_battery.available is True

    # Current action sensor
    s_action = VacuulaRobotSensor(coordinator, "ROBOT-3", entry, ROBOT_SENSORS[1])
    assert s_action.native_value == "house_cleaning"

    # Error sensor
    s_error = VacuulaRobotSensor(coordinator, "ROBOT-4", entry, ROBOT_SENSORS[2])
    assert s_error.native_value == "brush_stuck"
    # robot4 is disconnected
    assert s_error.available is False


async def test_binary_sensors(mock_sensor_setup) -> None:
    """Test server and robot binary sensors."""
    entry, coordinator, _, _, _ = mock_sensor_setup

    # Server status
    bs_server = VacuulaServerBinarySensor(coordinator, entry, SERVER_BINARY_SENSORS[0])
    assert bs_server.is_on is True

    # Charging
    bs_charging = VacuulaRobotBinarySensor(
        coordinator, "ROBOT-3", entry, ROBOT_BINARY_SENSORS[0]
    )
    assert bs_charging.is_on is False

    # Dustbin
    bs_dustbin = VacuulaRobotBinarySensor(
        coordinator, "ROBOT-3", entry, ROBOT_BINARY_SENSORS[1]
    )
    assert bs_dustbin.is_on is True

    # Connected
    bs_connected3 = VacuulaRobotBinarySensor(
        coordinator, "ROBOT-3", entry, ROBOT_BINARY_SENSORS[2]
    )
    assert bs_connected3.is_on is True
    assert bs_connected3.available is True

    bs_connected4 = VacuulaRobotBinarySensor(
        coordinator, "ROBOT-4", entry, ROBOT_BINARY_SENSORS[2]
    )
    assert bs_connected4.is_on is False
    assert bs_connected4.available is True  # Connected sensor stays available


async def test_buttons(mock_sensor_setup) -> None:
    """Test locate and dismiss_alert buttons."""
    entry, coordinator, api, _, robot4 = mock_sensor_setup

    btn_locate = VacuulaRobotButton(coordinator, "ROBOT-3", entry, ROBOT_BUTTONS[0])
    await btn_locate.async_press()
    api.async_find_me.assert_called_once_with("ROBOT-3", "gen3")

    # Dismiss alert button (supported on Gen3)
    btn_dismiss = VacuulaRobotButton(coordinator, "ROBOT-3", entry, ROBOT_BUTTONS[1])
    await btn_dismiss.async_press()
    api.async_dismiss_alert.assert_called_once_with("ROBOT-3")

    # Gen4 dismiss alert not supported
    assert ROBOT_BUTTONS[1].supported_fn(robot4) is False


async def test_switch(mock_sensor_setup) -> None:
    """Test schedule switch."""
    entry, coordinator, api, _, _ = mock_sensor_setup

    switch = VacuulaRobotScheduleSwitch(
        coordinator, "ROBOT-3", entry, SCHEDULE_SWITCH_DESCRIPTION
    )
    assert switch.unique_id == "ROBOT-3_schedule"
    assert switch.is_on is True

    await switch.async_turn_off()
    api.async_set_schedule.assert_called_once_with("ROBOT-3", False, "gen3")

    await switch.async_turn_on()
    api.async_set_schedule.assert_called_with("ROBOT-3", True, "gen3")
