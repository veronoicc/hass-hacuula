"""Asynchronous API client for Vacuula server."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .models import VacuulaMap, VacuulaRobotState, VacuulaServerInfo, VacuulaZone

_LOGGER = logging.getLogger(__name__)


class VacuulaError(Exception):
    """Base exception for Vacuula API errors."""


class VacuulaConnectionError(VacuulaError):
    """Exception raised when connecting to Vacuula server fails."""


class VacuulaAuthError(VacuulaError):
    """Exception raised when authentication fails."""


class VacuulaCommandError(VacuulaError):
    """Exception raised when a command to a robot fails."""


class VacuulaResponseError(VacuulaError):
    """Exception raised when Vacuula returns an invalid response."""


class VacuulaApiClient:
    """Asynchronous client for interacting with a Vacuula server."""

    def __init__(
        self,
        host: str,
        port: int = 80,
        session: aiohttp.ClientSession | None = None,
        use_ssl: bool = False,
        verify_ssl: bool = True,
        request_timeout: float = 10.0,
    ) -> None:
        """Initialize the Vacuula API client."""
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.verify_ssl = verify_ssl
        self.request_timeout = request_timeout

        scheme = "https" if use_ssl else "http"
        self.base_url = f"{scheme}://{host}:{port}"
        self._session = session
        self._owns_session = False
        self._stop_events = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp client session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def async_close(self) -> None:
        """Close the client session and stop event listeners."""
        self._stop_events = True
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Perform an HTTP request with error handling."""
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        timeout_val = aiohttp.ClientTimeout(total=timeout or self.request_timeout)

        ssl_ctx: bool | None = None if self.verify_ssl else False

        try:
            async with session.request(
                method=method,
                url=url,
                json=json_data,
                ssl=ssl_ctx,
                timeout=timeout_val,
            ) as response:
                if response.status in (401, 403):
                    raise VacuulaAuthError(f"Authentication failed: {response.status}")
                if response.status == 404:
                    raise VacuulaResponseError(f"Resource not found: {path}")
                if response.status >= 500:
                    text = await response.text()
                    raise VacuulaCommandError(f"Server error {response.status}: {text}")

                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json()
                text = await response.text()
                if not text:
                    return {}
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}

        except aiohttp.ClientConnectorError as err:
            raise VacuulaConnectionError(f"Failed to connect to {url}: {err}") from err
        except TimeoutError as err:
            raise VacuulaConnectionError(
                f"Request timeout connecting to {url}"
            ) from err
        except aiohttp.ClientError as err:
            raise VacuulaConnectionError(
                f"Network error connecting to {url}: {err}"
            ) from err

    async def async_get_server_info(self) -> VacuulaServerInfo:
        """Query Vacuula server metadata. Falls back to /api/robots if /api/server 404s."""
        try:
            data = await self._request("GET", "/api/server")
            if isinstance(data, dict):
                return VacuulaServerInfo(
                    version=str(data.get("version", "unknown")),
                    ports=data.get("ports", {}),
                    timezone=data.get("timezone"),
                    raw=data,
                )
        except VacuulaResponseError:
            # Fallback for older Vacuula builds that lack /api/server
            _LOGGER.debug(
                "GET /api/server 404'd, verifying with GET /api/robots fallback"
            )
            await self._request("GET", "/api/robots")
            return VacuulaServerInfo(version="legacy", ports={}, timezone=None, raw={})

        return VacuulaServerInfo(version="unknown", ports={}, timezone=None, raw={})

    async def async_get_robots(self) -> list[dict[str, Any]]:
        """Query all registered robots on the server."""
        data = await self._request("GET", "/api/robots")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "robots" in data and isinstance(data["robots"], list):
                return data["robots"]
            if "robots" in data and isinstance(data["robots"], dict):
                return list(data["robots"].values())
            # Dictionary keyed by serial number
            return list(data.values())
        return []

    async def async_get_robot_state(
        self, serial: str, robot_type: str = "gen3"
    ) -> VacuulaRobotState:
        """Get live state of a robot."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        payload = {"ability": "state.show"} if is_gen4 else {"cmd": "getRobotState"}
        try:
            raw = await self._request(
                "POST", f"/api/robot/{serial}/command", json_data=payload
            )
        except VacuulaError as err:
            _LOGGER.warning("Failed to fetch state for %s: %s", serial, err)
            return VacuulaRobotState()

        if isinstance(raw, dict):
            return VacuulaRobotState.from_raw(raw, robot_type)
        return VacuulaRobotState()

    async def async_get_maps(self, serial: str) -> list[VacuulaMap]:
        """Fetch maps associated with a robot."""
        try:
            data = await self._request("GET", f"/api/robot/{serial}/maps")
        except VacuulaError as err:
            _LOGGER.debug("Could not fetch maps for %s: %s", serial, err)
            return []

        raw_maps = (
            data
            if isinstance(data, list)
            else data.get("maps", [])
            if isinstance(data, dict)
            else []
        )
        maps: list[VacuulaMap] = []
        for m in raw_maps:
            if not isinstance(m, dict):
                continue
            map_id = str(m.get("id") or m.get("mapId") or m.get("rank_id") or "")
            map_name = str(m.get("name") or m.get("mapName") or f"Map {map_id}")
            if map_id:
                maps.append(VacuulaMap(id=map_id, name=map_name, zones=[]))
        return maps

    async def async_get_map_detail(self, serial: str, map_id: str) -> dict[str, Any]:
        """Fetch map detail including RLE floor grid."""
        try:
            data = await self._request("GET", f"/api/robot/{serial}/maps/{map_id}")
            return data if isinstance(data, dict) else {}
        except VacuulaError as err:
            _LOGGER.debug(
                "Could not fetch map detail for %s map %s: %s", serial, map_id, err
            )
            return {}

    async def async_get_runs(self, serial: str) -> list[dict[str, Any]]:
        """Fetch historical cleaning runs for a robot."""
        try:
            data = await self._request("GET", f"/api/robot/{serial}/runs")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("runs", [])
            return []
        except VacuulaError as err:
            _LOGGER.debug("Could not fetch cleaning runs for %s: %s", serial, err)
            return []

    async def async_get_run_detail(self, serial: str, run_id: str) -> dict[str, Any]:
        """Fetch detail and RLE path of a cleaning run."""
        try:
            data = await self._request("GET", f"/api/robot/{serial}/runs/{run_id}")
            return data if isinstance(data, dict) else {}
        except VacuulaError as err:
            _LOGGER.debug(
                "Could not fetch run detail for %s run %s: %s", serial, run_id, err
            )
            return {}

    async def async_start_map_exploration(
        self, serial: str, robot_type: str = "gen3"
    ) -> Any:
        """Start a house cleaning exploration run to generate or update map."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        if is_gen4:
            payload = {"ability": "exploration.start"}
        else:
            payload = {
                "cmd": "startCleaning",
                "params": {"category": 2, "mode": 2, "navigationMode": 1},
            }
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_get_boundaries(
        self, serial: str, map_id: str, robot_type: str = "gen3"
    ) -> list[VacuulaZone]:
        """Fetch boundaries/zones for a specific map."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )

        try:
            if is_gen4:
                data = await self._request(
                    "GET", f"/api/robot/{serial}/maps/{map_id}/boundaries"
                )
            else:
                data = await self._request(
                    "POST",
                    f"/api/robot/{serial}/command",
                    json_data={"cmd": "getMapBoundaries", "params": {"mapId": map_id}},
                )
        except VacuulaError as err:
            _LOGGER.debug(
                "Could not fetch boundaries for %s map %s: %s", serial, map_id, err
            )
            return []

        raw_zones = []
        if isinstance(data, list):
            raw_zones = data
        elif isinstance(data, dict):
            data_inner = data.get("data", data)
            raw_zones = (
                data_inner.get("boundaries")
                or data_inner.get("zones")
                or data.get("boundaries")
                or []
            )

        zones: list[VacuulaZone] = []
        for z in raw_zones:
            if not isinstance(z, dict):
                continue
            b_type = str(z.get("type", "polygon")).lower()
            # Only polygon boundaries are cleanable zones
            if "polygon" not in b_type and b_type not in ("zone", "room"):
                continue

            zone_id = str(z.get("id") or z.get("boundaryId") or z.get("track_id") or "")
            zone_name = str(z.get("name") or z.get("zoneName") or f"Zone {zone_id}")
            vertices = z.get("vertices") or z.get("recs") or []

            if zone_id:
                zones.append(
                    VacuulaZone(
                        id=zone_id,
                        name=zone_name,
                        map_id=map_id,
                        map_name="",
                        boundary_type=b_type,
                        vertices=vertices if isinstance(vertices, list) else [],
                    )
                )
        return zones

    async def async_start_cleaning(
        self,
        serial: str,
        robot_type: str = "gen3",
        mode: str | int = "turbo",
        nav_mode: str | int = "normal",
        map_id: str | None = None,
        zone_ids: list[str] | None = None,
    ) -> Any:
        """Start a house or zone cleaning run."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )

        if is_gen4:
            mode_str = (
                mode if isinstance(mode, str) else ("eco" if mode == 1 else "turbo")
            )
            nav_str = (
                nav_mode
                if isinstance(nav_mode, str)
                else (
                    "extra_care"
                    if nav_mode == 2
                    else ("deep" if nav_mode == 3 else "normal")
                )
            )

            if zone_ids and map_id:
                runs = [
                    {
                        "map": {
                            "rank_id": map_id,
                            "track_id": zid,
                            "nogo_enabled": True,
                        },
                        "settings": {"mode": mode_str, "navigation_mode": nav_str},
                    }
                    for zid in zone_ids
                ]
            else:
                run_item: dict[str, Any] = {
                    "settings": {"mode": mode_str, "navigation_mode": nav_str}
                }
                if map_id:
                    run_item["map"] = {"rank_id": map_id, "nogo_enabled": True}
                runs = [run_item]

            payload = {"ability": "cleaning.start", "runs": runs}
            return await self._request(
                "POST", f"/api/robot/{serial}/command", json_data=payload
            )

        # Gen3 handling
        mode_int = 1 if mode in ("eco", 1) else 2
        if nav_mode in ("extra_care", 2):
            nav_int = 2
        elif nav_mode in ("deep", 3):
            nav_int = 3
        else:
            nav_int = 1

        if zone_ids and map_id:
            params = {
                "category": 4,
                "mode": mode_int,
                "navigationMode": nav_int,
                "mapId": map_id,
                "boundaryIds": zone_ids,
            }
        else:
            params = {
                "category": 2,
                "mode": mode_int,
                "navigationMode": nav_int,
            }

        payload = {"cmd": "startCleaning", "params": params}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_pause_cleaning(self, serial: str, robot_type: str = "gen3") -> Any:
        """Pause cleaning."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        payload = {"ability": "cleaning.pause"} if is_gen4 else {"cmd": "pauseCleaning"}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_resume_cleaning(self, serial: str, robot_type: str = "gen3") -> Any:
        """Resume cleaning."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        payload = (
            {"ability": "cleaning.resume"} if is_gen4 else {"cmd": "resumeCleaning"}
        )
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_stop_cleaning(self, serial: str, robot_type: str = "gen3") -> Any:
        """Stop/cancel cleaning."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        payload = {"ability": "cleaning.cancel"} if is_gen4 else {"cmd": "stopCleaning"}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_send_to_base(self, serial: str, robot_type: str = "gen3") -> Any:
        """Send robot back to base."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        payload = (
            {"ability": "navigation.return_to_base"}
            if is_gen4
            else {"cmd": "sendToBase"}
        )
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_find_me(self, serial: str, robot_type: str = "gen3") -> Any:
        """Sound robot chime to locate it."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        payload = {"ability": "utilities.find_me"} if is_gen4 else {"cmd": "findMe"}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_clean_spot(
        self,
        serial: str,
        robot_type: str = "gen3",
        mode: str | int = "turbo",
        nav_mode: str | int = "normal",
        modifier: int = 1,
    ) -> Any:
        """Trigger spot clean for Gen3 robots."""
        mode_int = 1 if mode in ("eco", 1) else 2
        nav_int = (
            2
            if nav_mode in ("extra_care", 2)
            else (3 if nav_mode in ("deep", 3) else 1)
        )
        payload = {
            "cmd": "startCleaning",
            "params": {
                "category": 1,
                "mode": mode_int,
                "navigationMode": nav_int,
                "modifier": modifier,
            },
        }
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_dismiss_alert(self, serial: str) -> Any:
        """Dismiss current active alert on robot (Gen3)."""
        payload = {"cmd": "dismissCurrentAlert"}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_set_schedule(
        self, serial: str, enable: bool, robot_type: str = "gen3"
    ) -> Any:
        """Enable or disable onboard robot schedule."""
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )
        if is_gen4:
            payload = {"ability": "schedule.set", "enabled": enable}
        else:
            payload = {"cmd": "enableSchedule" if enable else "disableSchedule"}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_send_raw_command(
        self, serial: str, command: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Send raw command to robot."""
        if params is not None:
            payload = {"cmd": command, "params": params}
        elif "." in command:
            payload = {"ability": command}
        else:
            payload = {"cmd": command}
        return await self._request(
            "POST", f"/api/robot/{serial}/command", json_data=payload
        )

    async def async_listen_events(
        self, on_event: Callable[[dict[str, Any]], Any]
    ) -> None:
        """Connect to Server-Sent Events (SSE) endpoint and dispatch events."""
        session = await self._get_session()
        url = f"{self.base_url}/api/events"
        backoff = 1.0

        while not self._stop_events:
            try:
                ssl_ctx = None if self.verify_ssl else False
                async with session.get(
                    url,
                    ssl=ssl_ctx,
                    headers={"Accept": "text/event-stream"},
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=60.0),
                ) as response:
                    if response.status != 200:
                        _LOGGER.warning(
                            "SSE connection returned status %s", response.status
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30.0)
                        continue

                    backoff = 1.0
                    buffer = ""
                    async for chunk in response.content.iter_any():
                        if self._stop_events:
                            break
                        buffer += chunk.decode("utf-8", errors="replace")
                        while "\n\n" in buffer:
                            message, buffer = buffer.split("\n\n", 1)
                            event_data = self._parse_sse_message(message)
                            if event_data:
                                try:
                                    if asyncio.iscoroutinefunction(on_event):
                                        await on_event(event_data)
                                    else:
                                        on_event(event_data)
                                except Exception:
                                    _LOGGER.exception("Error in SSE event callback")

            except (TimeoutError, aiohttp.ClientError) as err:
                if not self._stop_events:
                    _LOGGER.debug(
                        "SSE disconnected: %s; reconnecting in %.1fs", err, backoff
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
            except asyncio.CancelledError:
                break
            except Exception:
                if not self._stop_events:
                    _LOGGER.exception("Unexpected error in SSE listener")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)

    @staticmethod
    def _parse_sse_message(message: str) -> dict[str, Any] | None:
        """Parse raw SSE frame into dictionary."""
        lines = message.strip().splitlines()
        event_name = "message"
        data_lines = []

        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())

        if not data_lines:
            return None

        combined_data = "\n".join(data_lines)
        try:
            payload = json.loads(combined_data)
        except json.JSONDecodeError:
            payload = {"raw": combined_data}

        if isinstance(payload, dict):
            payload.setdefault("event", event_name)
            return payload
        return {"event": event_name, "data": payload}
