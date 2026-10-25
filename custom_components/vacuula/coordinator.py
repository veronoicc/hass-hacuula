"""DataUpdateCoordinator for Vacuula integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    VacuulaApiClient,
    VacuulaAuthError,
    VacuulaConnectionError,
    VacuulaError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SIGNAL_NEW_ROBOT,
)
from .models import (
    VacuulaData,
    VacuulaMap,
    VacuulaRobot,
    VacuulaRobotState,
    VacuulaZone,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class VacuulaDataUpdateCoordinator(DataUpdateCoordinator[VacuulaData]):
    """Class to manage fetching Vacuula data from the server."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: VacuulaApiClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.entry = entry
        self._known_serials: set[str] = set()

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> VacuulaData:
        """Fetch latest data from Vacuula server."""
        try:
            server_info = await self.api.async_get_server_info()
            raw_robots = await self.api.async_get_robots()
        except VacuulaAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except (VacuulaConnectionError, VacuulaError) as err:
            raise UpdateFailed(
                f"Error communicating with Vacuula server: {err}"
            ) from err

        previous_robots = self.data.robots if self.data else {}
        robots: dict[str, VacuulaRobot] = {}
        newly_discovered: list[VacuulaRobot] = []

        for r_dict in raw_robots:
            if not isinstance(r_dict, dict):
                continue

            serial = str(r_dict.get("serial") or r_dict.get("id") or "")
            if not serial:
                continue

            name = str(r_dict.get("name") or f"Robot {serial}")
            model = str(
                r_dict.get("model") or r_dict.get("model_name") or "Vacuula Vacuum"
            )
            robot_type = str(r_dict.get("type") or r_dict.get("robot_type") or "gen3")
            connected = bool(r_dict.get("connected", True))
            firmware = str(r_dict.get("firmware") or r_dict.get("version") or "")

            prev_robot = previous_robots.get(serial)

            # Fetch state if connected
            if connected:
                state = await self.api.async_get_robot_state(
                    serial, robot_type=robot_type
                )
            else:
                state = (
                    prev_robot.state
                    if prev_robot
                    else VacuulaRobotState(action_description="disconnected")
                )

            # Preserve or fetch maps, runs, and zones
            maps: list[VacuulaMap] = []
            zones: dict[str, VacuulaZone] = {}
            boundaries: list[dict[str, Any]] = []
            floormap: dict[str, Any] | None = None
            last_run: dict[str, Any] | None = None
            last_runmap: dict[str, Any] | None = None
            last_clean_area: float | None = None
            last_clean_duration: int | None = None
            total_cleans: int = 0
            active_map_id: str | None = None
            active_map_name: str | None = None

            if prev_robot and prev_robot.maps:
                maps = prev_robot.maps
                zones = prev_robot.zones
                boundaries = prev_robot.boundaries
                floormap = prev_robot.floormap
                last_run = prev_robot.last_run
                last_runmap = prev_robot.last_runmap
                last_clean_area = prev_robot.last_clean_area
                last_clean_duration = prev_robot.last_clean_duration
                total_cleans = prev_robot.total_cleans
                active_map_id = prev_robot.active_map_id
                active_map_name = prev_robot.active_map_name
            elif connected:
                map_res = await self._async_load_maps_and_runs(serial, robot_type)
                maps = map_res["maps"]
                zones = map_res["zones"]
                boundaries = map_res["boundaries"]
                floormap = map_res["floormap"]
                last_run = map_res["last_run"]
                last_runmap = map_res["last_runmap"]
                last_clean_area = map_res["last_clean_area"]
                last_clean_duration = map_res["last_clean_duration"]
                total_cleans = map_res["total_cleans"]
                active_map_id = map_res["active_map_id"]
                active_map_name = map_res["active_map_name"]

            # Preserve user preferences across updates
            pref_nav = prev_robot.preferred_navigation_mode if prev_robot else "normal"
            pref_cat = prev_robot.preferred_category if prev_robot else 2
            pref_fan = prev_robot.preferred_fan_speed if prev_robot else "turbo"
            sel_zone = prev_robot.selected_zone if prev_robot else "all"

            robot = VacuulaRobot(
                serial=serial,
                name=name,
                model=model,
                robot_type=robot_type,
                connected=connected,
                firmware=firmware or None,
                state=state,
                maps=maps,
                zones=zones,
                floormap=floormap,
                last_run=last_run,
                last_runmap=last_runmap,
                active_map_id=active_map_id,
                active_map_name=active_map_name,
                boundaries=boundaries,
                preferred_navigation_mode=pref_nav,
                preferred_category=pref_cat,
                preferred_fan_speed=pref_fan,
                selected_zone=sel_zone,
                last_clean_area=last_clean_area,
                last_clean_duration=last_clean_duration,
                total_cleans=total_cleans,
            )
            robots[serial] = robot

            if serial not in self._known_serials:
                newly_discovered.append(robot)
                self._known_serials.add(serial)

        # Dispatch signals for any newly discovered robots
        for new_robot in newly_discovered:
            async_dispatcher_send(
                self.hass,
                SIGNAL_NEW_ROBOT.format(self.entry.entry_id),
                new_robot,
            )

        return VacuulaData(
            server_info=server_info,
            robots=robots,
            server_status=True,
        )

    async def _async_load_maps_and_runs(
        self, serial: str, robot_type: str
    ) -> dict[str, Any]:
        """Fetch all maps, floor detail, historical runs, and zones for a robot."""
        maps = await self.api.async_get_maps(serial)
        zones: dict[str, VacuulaZone] = {}
        boundaries: list[dict[str, Any]] = []
        floormap: dict[str, Any] | None = None
        active_map_id: str | None = None
        active_map_name: str | None = None

        if maps:
            active_m = maps[0]
            active_map_id = active_m.id
            active_map_name = active_m.name
            floormap = await self.api.async_get_map_detail(serial, active_m.id)

        for m in maps:
            map_zones = await self.api.async_get_boundaries(serial, m.id, robot_type)
            for z in map_zones:
                z.map_name = m.name
                zones[f"{m.id}:{z.id}"] = z
                boundaries.append(
                    {
                        "id": z.id,
                        "name": z.name,
                        "type": z.boundary_type,
                        "vertices": z.vertices,
                        "map_id": m.id,
                    }
                )
            m.zones = map_zones

        # Fetch runs
        runs = await self.api.async_get_runs(serial)
        total_cleans = len(runs)
        last_run: dict[str, Any] | None = None
        last_runmap: dict[str, Any] | None = None
        last_clean_area: float | None = None
        last_clean_duration: int | None = None

        if runs:
            last_run = runs[0]
            run_id = str(last_run.get("id") or last_run.get("run_id") or "")
            if run_id:
                last_runmap = await self.api.async_get_run_detail(serial, run_id)

            area_val = last_run.get("cleaned_area") or last_run.get("area")
            if area_val is not None:
                try:
                    last_clean_area = round(float(area_val), 1)
                except (ValueError, TypeError):
                    pass

            start_t = last_run.get("start_at")
            end_t = last_run.get("end_at")
            if start_t and end_t:
                try:
                    s_dt = datetime.fromisoformat(start_t)
                    e_dt = datetime.fromisoformat(end_t)
                    last_clean_duration = int((e_dt - s_dt).total_seconds())
                except (ValueError, TypeError):
                    pass
            elif last_run.get("duration") is not None:
                try:
                    last_clean_duration = int(last_run["duration"])
                except (ValueError, TypeError):
                    pass

        return {
            "maps": maps,
            "zones": zones,
            "boundaries": boundaries,
            "floormap": floormap,
            "last_run": last_run,
            "last_runmap": last_runmap,
            "last_clean_area": last_clean_area,
            "last_clean_duration": last_clean_duration,
            "total_cleans": total_cleans,
            "active_map_id": active_map_id,
            "active_map_name": active_map_name,
        }

    async def async_refresh_robot_maps(self, serial: str) -> None:
        """Explicitly re-fetch maps, floorplans, and run history for a robot."""
        if not self.data or serial not in self.data.robots:
            return

        robot = self.data.robots[serial]
        res = await self._async_load_maps_and_runs(serial, robot.robot_type)
        robot.maps = res["maps"]
        robot.zones = res["zones"]
        robot.boundaries = res["boundaries"]
        robot.floormap = res["floormap"]
        robot.last_run = res["last_run"]
        robot.last_runmap = res["last_runmap"]
        robot.last_clean_area = res["last_clean_area"]
        robot.last_clean_duration = res["last_clean_duration"]
        robot.total_cleans = res["total_cleans"]
        robot.active_map_id = res["active_map_id"]
        robot.active_map_name = res["active_map_name"]
        self.async_set_updated_data(self.data)

    async def async_handle_sse_event(self, event_data: dict[str, Any]) -> None:
        """Handle incoming real-time SSE event and update coordinator cache."""
        if not self.data:
            return

        event_name = event_data.get("event")
        serial = event_data.get("serial") or event_data.get("robot_id")

        if not serial or serial not in self.data.robots:
            if event_name in ("robot_registered", "robot_connected", "new_robot"):
                await self.async_request_refresh()
            return

        robot = self.data.robots[serial]

        if (
            "state" in event_data
            or "data" in event_data
            or event_name == "state_changed"
        ):
            raw_state = event_data.get("data") if "data" in event_data else event_data
            if isinstance(raw_state, dict):
                robot.state = VacuulaRobotState.from_raw(raw_state, robot.robot_type)
                self.async_set_updated_data(self.data)
        elif event_name in ("connected", "disconnected"):
            robot.connected = event_name == "connected"
            self.async_set_updated_data(self.data)
        elif event_name in ("map_updated", "run_completed"):
            await self.async_refresh_robot_maps(serial)
