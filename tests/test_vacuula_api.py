"""Unit tests for Vacuula API client and data models."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from custom_components.vacuula.api import (
    VacuulaApiClient,
    VacuulaResponseError,
)
from custom_components.vacuula.models import (
    VacuulaRobot,
    VacuulaRobotState,
)


def test_robot_state_gen3_parsing():
    """Test Gen3 Neato getRobotState payload parsing."""
    raw = {
        "version": 1,
        "result": "ok",
        "data": {
            "state": 2,
            "action": 1,
            "error": None,
            "details": {
                "charge": 88,
                "isCharging": True,
                "isDocked": True,
                "isScheduleEnabled": True,
                "isBinFull": False,
            },
        },
    }
    state = VacuulaRobotState.from_raw(raw, robot_type="gen3")
    assert state.state_code == 2
    assert state.action_code == 1
    assert state.action_description == "house_cleaning"
    assert state.battery_level == 88
    assert state.is_charging is True
    assert state.is_docked is True
    assert state.is_bin_full is False
    assert state.schedule_enabled is True
    assert state.error is None


def test_robot_state_gen4_parsing():
    """Test Gen4 Neato state.show payload parsing."""
    raw = {
        "data": {
            "battery": {"level": 72, "charging": False},
            "status": {"state": "cleaning", "substate": "active"},
            "dock": {"docked": False},
            "dirtbin": {"alert": True, "present": True},
            "schedule": {"enabled": True},
        }
    }
    state = VacuulaRobotState.from_raw(raw, robot_type="gen4")
    assert state.action_description == "cleaning"
    assert state.battery_level == 72
    assert state.is_charging is False
    assert state.is_docked is False
    assert state.is_bin_full is True
    assert state.schedule_enabled is True


def test_robot_is_gen4_property():
    """Test VacuulaRobot is_gen4 property detection."""
    r_gen3 = VacuulaRobot(
        serial="OPS123", name="D7", model="Botvac D7 Connected", robot_type="gen3"
    )
    assert r_gen3.is_gen4 is False

    r_gen4 = VacuulaRobot(
        serial="OPS456", name="D10", model="Neato D10", robot_type="gen4"
    )
    assert r_gen4.is_gen4 is True

    r_d8 = VacuulaRobot(serial="OPS789", name="D8", model="D8", robot_type="neato_gen4")
    assert r_d8.is_gen4 is True


@pytest.mark.asyncio
async def test_api_client_urls():
    """Test URL and base URL construction."""
    client_http = VacuulaApiClient(host="192.168.1.100", port=8080)
    assert client_http.base_url == "http://192.168.1.100:8080"

    client_https = VacuulaApiClient(host="vacuula.local", port=443, use_ssl=True)
    assert client_https.base_url == "https://vacuula.local:443"


@pytest.mark.asyncio
async def test_get_server_info_success():
    """Test getting server info."""
    client = VacuulaApiClient(host="127.0.0.1")
    with patch.object(
        client,
        "_request",
        AsyncMock(
            return_value={"version": "1.2.3", "ports": {"http": 80}, "timezone": "UTC"}
        ),
    ):
        info = await client.async_get_server_info()
        assert info.version == "1.2.3"
        assert info.timezone == "UTC"
        assert info.ports == {"http": 80}


@pytest.mark.asyncio
async def test_get_server_info_fallback():
    """Test 404 fallback to legacy server info when /api/server is absent."""
    client = VacuulaApiClient(host="127.0.0.1")

    async def mock_request(method, path, **kwargs):
        if path == "/api/server":
            raise VacuulaResponseError("Resource not found")
        if path == "/api/robots":
            return []
        return {}

    with patch.object(client, "_request", side_effect=mock_request):
        info = await client.async_get_server_info()
        assert info.version == "legacy"


@pytest.mark.asyncio
async def test_get_robots():
    """Test fetching robot list."""
    client = VacuulaApiClient(host="127.0.0.1")
    with patch.object(
        client,
        "_request",
        AsyncMock(
            return_value=[
                {
                    "serial": "ROBOT1",
                    "name": "Living Room",
                    "model": "D7",
                    "type": "gen3",
                    "connected": True,
                }
            ]
        ),
    ):
        robots = await client.async_get_robots()
        assert len(robots) == 1
        assert robots[0]["serial"] == "ROBOT1"


@pytest.mark.asyncio
async def test_cleaning_commands():
    """Test Gen3 and Gen4 start cleaning requests."""
    client = VacuulaApiClient(host="127.0.0.1")

    # Gen3 house clean
    with patch.object(client, "_request", AsyncMock()) as mock_req:
        await client.async_start_cleaning(
            "SN1", robot_type="gen3", mode="turbo", nav_mode="normal"
        )
        mock_req.assert_called_once_with(
            "POST",
            "/api/robot/SN1/command",
            json_data={
                "cmd": "startCleaning",
                "params": {"category": 2, "mode": 2, "navigationMode": 1},
            },
        )

    # Gen3 zone clean
    with patch.object(client, "_request", AsyncMock()) as mock_req:
        await client.async_start_cleaning(
            "SN1",
            robot_type="gen3",
            mode="eco",
            nav_mode="extra_care",
            map_id="map1",
            zone_ids=["z1", "z2"],
        )
        mock_req.assert_called_once_with(
            "POST",
            "/api/robot/SN1/command",
            json_data={
                "cmd": "startCleaning",
                "params": {
                    "category": 4,
                    "mode": 1,
                    "navigationMode": 2,
                    "mapId": "map1",
                    "boundaryIds": ["z1", "z2"],
                },
            },
        )

    # Gen4 house clean
    with patch.object(client, "_request", AsyncMock()) as mock_req:
        await client.async_start_cleaning(
            "SN2", robot_type="gen4", mode="turbo", nav_mode="deep"
        )
        mock_req.assert_called_once_with(
            "POST",
            "/api/robot/SN2/command",
            json_data={
                "ability": "cleaning.start",
                "runs": [{"settings": {"mode": "turbo", "navigation_mode": "deep"}}],
            },
        )

    # Gen4 zone clean
    with patch.object(client, "_request", AsyncMock()) as mock_req:
        await client.async_start_cleaning(
            "SN2",
            robot_type="gen4",
            mode="eco",
            nav_mode="normal",
            map_id="m10",
            zone_ids=["z1"],
        )
        mock_req.assert_called_once_with(
            "POST",
            "/api/robot/SN2/command",
            json_data={
                "ability": "cleaning.start",
                "runs": [
                    {
                        "map": {
                            "rank_id": "m10",
                            "track_id": "z1",
                            "nogo_enabled": True,
                        },
                        "settings": {"mode": "eco", "navigation_mode": "normal"},
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_control_commands():
    """Test pause, resume, stop, sendToBase, findMe, dismiss."""
    client = VacuulaApiClient(host="127.0.0.1")

    # Gen3 controls
    with patch.object(client, "_request", AsyncMock()) as mock_req:
        await client.async_pause_cleaning("SN1", "gen3")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN1/command", json_data={"cmd": "pauseCleaning"}
        )

        await client.async_resume_cleaning("SN1", "gen3")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN1/command", json_data={"cmd": "resumeCleaning"}
        )

        await client.async_stop_cleaning("SN1", "gen3")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN1/command", json_data={"cmd": "stopCleaning"}
        )

        await client.async_send_to_base("SN1", "gen3")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN1/command", json_data={"cmd": "sendToBase"}
        )

        await client.async_find_me("SN1", "gen3")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN1/command", json_data={"cmd": "findMe"}
        )

        await client.async_dismiss_alert("SN1")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN1/command", json_data={"cmd": "dismissCurrentAlert"}
        )

    # Gen4 controls
    with patch.object(client, "_request", AsyncMock()) as mock_req:
        await client.async_pause_cleaning("SN2", "gen4")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN2/command", json_data={"ability": "cleaning.pause"}
        )

        await client.async_resume_cleaning("SN2", "gen4")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN2/command", json_data={"ability": "cleaning.resume"}
        )

        await client.async_stop_cleaning("SN2", "gen4")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN2/command", json_data={"ability": "cleaning.cancel"}
        )

        await client.async_send_to_base("SN2", "gen4")
        mock_req.assert_called_with(
            "POST",
            "/api/robot/SN2/command",
            json_data={"ability": "navigation.return_to_base"},
        )

        await client.async_find_me("SN2", "gen4")
        mock_req.assert_called_with(
            "POST", "/api/robot/SN2/command", json_data={"ability": "utilities.find_me"}
        )


def test_sse_message_parser():
    """Test parsing SSE event frames."""
    raw_sse = 'event: robot_update\ndata: {"serial": "OPS123", "state": 1}\n'
    msg = VacuulaApiClient._parse_sse_message(raw_sse)
    assert msg is not None
    assert msg["event"] == "robot_update"
    assert msg["serial"] == "OPS123"
