"""Tests for Vacuula map image platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from custom_components.vacuula.api import VacuulaApiClient, VacuulaServerInfo
from custom_components.vacuula.const import DOMAIN
from custom_components.vacuula.coordinator import VacuulaDataUpdateCoordinator
from custom_components.vacuula.image import VacuulaFloorMapImage, VacuulaLastRunMapImage
from custom_components.vacuula.models import (
    VacuulaData,
    VacuulaMap,
    VacuulaRobot,
    VacuulaRobotState,
    VacuulaZone,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_image_setup(hass: HomeAssistant):
    """Set up test environment for map image entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 80},
        unique_id="v_test_image",
    )
    entry.add_to_hass(hass)

    api = VacuulaApiClient(host="127.0.0.1")
    coordinator = VacuulaDataUpdateCoordinator(hass, api, entry)
    coordinator.async_request_refresh = AsyncMock()

    zone = VacuulaZone(id="z1", name="Kitchen", map_id="m1", map_name="Main")

    robot = VacuulaRobot(
        serial="ROBOT-MAP",
        name="Neato D7",
        model="D7 Connected",
        robot_type="gen3",
        connected=True,
        state=VacuulaRobotState(action_description="idle"),
        maps=[VacuulaMap(id="m1", name="Main", zones=[zone])],
        zones={"m1:z1": zone},
        floormap={
            "width": 10,
            "height": 10,
            "rle": [[1, 50], [2, 50]],
            "dock": {"pixel_x": 5, "pixel_y": 5},
        },
        boundaries=[
            {
                "id": "z1",
                "name": "Kitchen",
                "type": "polygon",
                "color": "#5aa9ff",
                "vertices": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
            }
        ],
        last_run={
            "id": "run_100",
            "cleaned_area": 25.4,
            "start_at": "2026-10-25T10:00:00Z",
            "end_at": "2026-10-25T10:30:00Z",
            "status": "completed",
        },
        last_runmap={
            "width": 10,
            "height": 10,
            "rle": [[3, 30], [150, 20], [128, 50]],
        },
        last_clean_area=25.4,
        last_clean_duration=1800,
        total_cleans=5,
    )

    coordinator.data = VacuulaData(
        server_info=VacuulaServerInfo(version="1.0.0"),
        robots={"ROBOT-MAP": robot},
        server_status=True,
    )
    entry.runtime_data = coordinator

    return entry, coordinator, robot


async def test_floor_map_image(hass: HomeAssistant, mock_image_setup) -> None:
    """Test floor map image rendering and attributes."""
    entry, coordinator, _ = mock_image_setup
    img_entity = VacuulaFloorMapImage(coordinator, "ROBOT-MAP", entry)

    assert img_entity.unique_id == "ROBOT-MAP_floor_map"
    assert img_entity.available is True
    assert img_entity.content_type == "image/png"

    attrs = img_entity.extra_state_attributes
    assert attrs["serial"] == "ROBOT-MAP"
    assert len(attrs["zones"]) == 1
    assert attrs["zones"][0]["name"] == "Kitchen"

    # Render image bytes
    png_bytes = await img_entity.async_image()
    assert png_bytes is not None
    assert png_bytes.startswith(b"\x89PNG")


async def test_last_run_map_image(hass: HomeAssistant, mock_image_setup) -> None:
    """Test last run map image rendering and attributes."""
    entry, coordinator, _ = mock_image_setup
    img_entity = VacuulaLastRunMapImage(coordinator, "ROBOT-MAP", entry)

    assert img_entity.unique_id == "ROBOT-MAP_last_run_map"
    assert img_entity.available is True

    attrs = img_entity.extra_state_attributes
    assert attrs["run_id"] == "run_100"
    assert attrs["cleaned_area_m2"] == 25.4

    png_bytes = await img_entity.async_image()
    assert png_bytes is not None
    assert png_bytes.startswith(b"\x89PNG")
