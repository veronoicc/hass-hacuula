"""Tests for Vacuula diagnostics."""

from __future__ import annotations

from custom_components.vacuula.api import VacuulaServerInfo
from custom_components.vacuula.const import DOMAIN
from custom_components.vacuula.coordinator import VacuulaDataUpdateCoordinator
from custom_components.vacuula.diagnostics import async_get_config_entry_diagnostics
from custom_components.vacuula.models import (
    VacuulaData,
    VacuulaMap,
    VacuulaRobot,
    VacuulaRobotState,
    VacuulaZone,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_diagnostics_redaction(hass: HomeAssistant) -> None:
    """Test diagnostics redacts sensitive data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80},
        unique_id="vacuula_192.168.1.100_80",
    )
    entry.add_to_hass(hass)

    robot = VacuulaRobot(
        serial="SECRET_SERIAL_123",
        name="Living Room Neato",
        model="Botvac D7",
        robot_type="gen3",
        connected=True,
        firmware="4.5.3",
        state=VacuulaRobotState(
            action_description="idle",
            battery_level=95,
        ),
        maps=[VacuulaMap(id="map_1", name="Main Floor")],
        zones={
            "map_1:z1": VacuulaZone(
                id="z1", name="Kitchen", map_id="map_1", map_name="Main Floor"
            )
        },
    )

    coordinator = VacuulaDataUpdateCoordinator(hass, None, entry)
    coordinator.data = VacuulaData(
        server_info=VacuulaServerInfo(version="1.0.0", timezone="America/New_York"),
        robots={"SECRET_SERIAL_123": robot},
        server_status=True,
    )
    entry.runtime_data = coordinator

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Ensure host in entry data is redacted
    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_PORT] == 80

    # Ensure server info is present
    assert diag["server_info"]["version"] == "1.0.0"
    assert diag["server_info"]["timezone"] == "America/New_York"

    # Ensure robots are present
    assert diag["robots_count"] == 1
    robot_diag = diag["robots"]["SECRET_SERIAL_123"]
    assert robot_diag["name"] == "Living Room Neato"
    assert robot_diag["model"] == "Botvac D7"
    assert robot_diag["state"]["battery_level"] == 95
    assert robot_diag["zones_count"] == 1
