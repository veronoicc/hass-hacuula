"""DataUpdateCoordinator for Vacuula integration."""

from __future__ import annotations

import logging
from datetime import timedelta
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

            # Preserve or fetch maps and zones
            maps: list[VacuulaMap] = []
            zones: dict[str, VacuulaZone] = {}

            if prev_robot and prev_robot.maps:
                maps = prev_robot.maps
                zones = prev_robot.zones
            elif connected:
                maps, zones = await self._async_load_maps_and_zones(serial, robot_type)

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

    async def _async_load_maps_and_zones(
        self, serial: str, robot_type: str
    ) -> tuple[list[VacuulaMap], dict[str, VacuulaZone]]:
        """Fetch all maps and zones for a robot."""
        maps = await self.api.async_get_maps(serial)
        zones: dict[str, VacuulaZone] = {}

        for m in maps:
            map_zones = await self.api.async_get_boundaries(serial, m.id, robot_type)
            for z in map_zones:
                z.map_name = m.name
                zones[f"{m.id}:{z.id}"] = z
            m.zones = map_zones

        return maps, zones

    async def async_refresh_robot_maps(self, serial: str) -> None:
        """Explicitly re-fetch maps and zones for a robot."""
        if not self.data or serial not in self.data.robots:
            return

        robot = self.data.robots[serial]
        maps, zones = await self._async_load_maps_and_zones(serial, robot.robot_type)
        robot.maps = maps
        robot.zones = zones
        self.async_set_updated_data(self.data)

    async def async_handle_sse_event(self, event_data: dict[str, Any]) -> None:
        """Handle incoming real-time SSE event and update coordinator cache."""
        if not self.data:
            return

        event_name = event_data.get("event")
        serial = event_data.get("serial") or event_data.get("robot_id")

        if not serial or serial not in self.data.robots:
            # If unknown robot or new robot registered, trigger full refresh
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
