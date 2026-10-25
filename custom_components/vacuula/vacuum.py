"""Support for Vacuula robot vacuums as modern StateVacuumEntity."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEFAULT_MODE,
    CONF_DEFAULT_NAV_MODE,
    DEFAULT_MODE,
    DEFAULT_NAV_MODE,
    DOMAIN,
    MODE_ECO,
    MODE_TURBO,
    SIGNAL_NEW_ROBOT,
)
from .coordinator import VacuulaDataUpdateCoordinator
from .models import VacuulaRobot

if TYPE_CHECKING:
    from . import VacuulaConfigEntry

_LOGGER = logging.getLogger(__name__)

# Modern CLEAN_AREA feature flag (or fallback IntFlag value)
FEATURE_CLEAN_AREA = getattr(VacuumEntityFeature, "CLEAN_AREA", 16384)


@dataclass
class Segment:
    """Segment representation for area/room cleaning."""

    id: str
    name: str
    group: str | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula vacuum entities from a config entry."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    known_serials: set[str] = set()

    def _create_entity(serial: str) -> VacuulaVacuumEntity:
        return VacuulaVacuumEntity(coordinator, serial, entry)

    entities = []
    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.append(_create_entity(serial))
                known_serials.add(serial)
    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        """Handle dynamic addition of new robots."""
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities([_create_entity(new_robot.serial)])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaVacuumEntity(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], StateVacuumEntity
):
    """Vacuula robot vacuum entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator)
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_vacuum"
        self._attr_fan_speed_list = [MODE_TURBO, MODE_ECO]

        self._current_mode = entry.options.get(CONF_DEFAULT_MODE, DEFAULT_MODE)
        self._current_nav_mode = entry.options.get(
            CONF_DEFAULT_NAV_MODE, DEFAULT_NAV_MODE
        )

    @property
    def robot(self) -> VacuulaRobot | None:
        """Get current robot data from coordinator."""
        if self.coordinator.data and self._serial in self.coordinator.data.robots:
            return self.coordinator.data.robots[self._serial]
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry information."""
        robot = self.robot
        name = robot.name if robot else f"Robot {self._serial}"
        model = robot.model if robot else "Vacuula Vacuum"
        sw_version = robot.firmware if robot else None

        return {
            "identifiers": {(DOMAIN, self._serial)},
            "via_device": (DOMAIN, f"server_{self._entry.entry_id}"),
            "name": name,
            "manufacturer": "Neato Robotics",
            "model": model,
            "sw_version": sw_version,
        }

    @property
    def available(self) -> bool:
        """Return True if robot is online and coordinator is functional."""
        if not super().available or not self.robot:
            return False
        return self.robot.connected

    @property
    def activity(self) -> VacuumActivity | None:
        """Map robot internal state to VacuumActivity."""
        robot = self.robot
        if not robot:
            return None

        state = robot.state
        if state.error:
            return VacuumActivity.ERROR

        # Gen3 numeric state check
        if state.state_code == 4:
            return VacuumActivity.ERROR
        if state.state_code == 3:
            return VacuumActivity.PAUSED

        action = (state.action_description or "").lower()
        if action in (
            "house_cleaning",
            "spot_cleaning",
            "zone_cleaning",
            "cleaning",
            "manual_cleaning",
        ):
            return VacuumActivity.CLEANING
        if action in ("docking", "returning"):
            return VacuumActivity.RETURNING
        if action in ("docked", "charging"):
            return VacuumActivity.DOCKED
        if action in ("paused", "suspended_cleaning", "suspended"):
            return VacuumActivity.PAUSED
        if action in ("user_interaction_needed", "error"):
            return VacuumActivity.ERROR

        if state.state_code == 2:
            return VacuumActivity.CLEANING

        if state.is_docked:
            return VacuumActivity.DOCKED

        return VacuumActivity.IDLE

    @property
    def battery_level(self) -> int | None:
        """Return battery level percentage."""
        return self.robot.state.battery_level if self.robot else None

    @property
    def fan_speed(self) -> str | None:
        """Return current fan speed/cleaning mode."""
        return self._current_mode

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Flag supported features for this vacuum."""
        features = (
            VacuumEntityFeature.START
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.RETURN_HOME
            | VacuumEntityFeature.LOCATE
            | VacuumEntityFeature.BATTERY
            | VacuumEntityFeature.STATE
            | VacuumEntityFeature.FAN_SPEED
        )

        robot = self.robot
        if robot:
            if not robot.is_gen4:
                features |= VacuumEntityFeature.CLEAN_SPOT
            if robot.zones:
                features |= FEATURE_CLEAN_AREA

        return features

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        robot = self.robot
        if not robot:
            return {}

        zones_payload = [
            {"id": zid, "name": z.name, "map_name": z.map_name}
            for zid, z in robot.zones.items()
        ]
        maps_payload = [m.name for m in robot.maps]

        return {
            "action": robot.state.action_description,
            "error": robot.state.error,
            "is_charging": robot.state.is_charging,
            "is_docked": robot.state.is_docked,
            "is_bin_full": robot.state.is_bin_full,
            "schedule_enabled": robot.state.schedule_enabled,
            "cleanable_zones": zones_payload,
            "maps": maps_payload,
        }

    async def async_start(self) -> None:
        """Start or resume cleaning."""
        robot = self.robot
        if not robot:
            return

        if self.activity == VacuumActivity.PAUSED:
            await self.coordinator.api.async_resume_cleaning(
                self._serial, robot.robot_type
            )
        else:
            await self.coordinator.api.async_start_cleaning(
                self._serial,
                robot_type=robot.robot_type,
                mode=self._current_mode,
                nav_mode=self._current_nav_mode,
            )
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause cleaning."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_pause_cleaning(self._serial, robot.robot_type)
        await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop cleaning."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_stop_cleaning(self._serial, robot.robot_type)
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return to docking station."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_send_to_base(self._serial, robot.robot_type)
        await self.coordinator.async_request_refresh()

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum by playing identify chime."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_find_me(self._serial, robot.robot_type)

    async def async_clean_spot(self, **kwargs: Any) -> None:
        """Perform spot cleaning."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_clean_spot(
            self._serial,
            robot_type=robot.robot_type,
            mode=self._current_mode,
            nav_mode=self._current_nav_mode,
        )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set fan speed (mode)."""
        mode = fan_speed.lower()
        if mode in (MODE_TURBO, MODE_ECO):
            self._current_mode = mode
            if self.hass:
                self.async_write_ha_state()

    # --- Modern CLEAN_AREA contract ---

    async def async_get_segments(self) -> list[Segment]:
        """Return list of cleanable segments (zones/rooms)."""
        robot = self.robot
        if not robot or not robot.zones:
            return []

        return [
            Segment(id=composite_id, name=zone.name, group=zone.map_name)
            for composite_id, zone in robot.zones.items()
        ]

    async def async_clean_segments(self, segment_ids: list[str], **kwargs: Any) -> None:
        """Clean selected segments/rooms."""
        robot = self.robot
        if not robot or not segment_ids:
            return

        # Separate composite IDs into map_id and zone_ids
        map_id: str | None = None
        target_zone_ids: list[str] = []

        for seg_id in segment_ids:
            if ":" in seg_id:
                m_id, z_id = seg_id.split(":", 1)
                map_id = m_id
                target_zone_ids.append(z_id)
            elif seg_id in robot.zones:
                zone = robot.zones[seg_id]
                map_id = zone.map_id
                target_zone_ids.append(zone.id)
            else:
                # Direct zone id matching
                for z in robot.zones.values():
                    if z.id == seg_id:
                        map_id = z.map_id
                        target_zone_ids.append(z.id)
                        break

        if not target_zone_ids:
            _LOGGER.warning("No matching zones found for segment_ids: %s", segment_ids)
            return

        await self.coordinator.api.async_start_cleaning(
            self._serial,
            robot_type=robot.robot_type,
            mode=self._current_mode,
            nav_mode=self._current_nav_mode,
            map_id=map_id,
            zone_ids=target_zone_ids,
        )
        await self.coordinator.async_request_refresh()
