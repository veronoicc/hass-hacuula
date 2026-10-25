"""Select entities for Vacuula robot vacuums (Navigation mode, Cleaning mode, Target zone)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ALL_ZONES_OPTION,
    CLEAN_CATEGORY_HOUSE,
    CLEAN_CATEGORY_MAP,
    DOMAIN,
    GEN3_CLEAN_CATEGORIES,
    GEN3_NAV_MODES,
    GEN4_NAV_MODES,
    MODE_TURBO,
    NAV_MODE_DEEP,
    SIGNAL_NEW_ROBOT,
)
from .coordinator import VacuulaDataUpdateCoordinator
from .models import VacuulaRobot

if TYPE_CHECKING:
    from . import VacuulaConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula select entities with dynamic discovery."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    known_serials: set[str] = set()

    def _create_selects(serial: str) -> list[SelectEntity]:
        robot = coordinator.data.robots.get(serial) if coordinator.data else None
        entities: list[SelectEntity] = [
            VacuulaNavigationModeSelect(coordinator, serial, entry),
            VacuulaTargetZoneSelect(coordinator, serial, entry),
        ]
        if robot and not robot.is_gen4:
            entities.append(VacuulaCleaningCategorySelect(coordinator, serial, entry))
        return entities

    entities: list[SelectEntity] = []
    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.extend(_create_selects(serial))
                known_serials.add(serial)

    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities(_create_selects(new_robot.serial))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaNavigationModeSelect(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], SelectEntity
):
    """Select entity for choosing the robot's navigation mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "navigation_mode"
    _attr_icon = "mdi:map-marker-path"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the navigation mode select entity."""
        super().__init__(coordinator)
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_navigation_mode"

    @property
    def robot(self) -> VacuulaRobot | None:
        """Get robot data."""
        if self.coordinator.data and self._serial in self.coordinator.data.robots:
            return self.coordinator.data.robots[self._serial]
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry info for robot."""
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
        """Return True if robot is online."""
        return bool(super().available and self.robot and self.robot.connected)

    @property
    def options(self) -> list[str]:
        """Return available navigation modes based on robot generation."""
        if self.robot and not self.robot.is_gen4:
            return GEN3_NAV_MODES
        return GEN4_NAV_MODES

    @property
    def current_option(self) -> str | None:
        """Return currently selected navigation mode."""
        if not self.robot:
            return None
        return self.robot.preferred_navigation_mode

    async def async_select_option(self, option: str) -> None:
        """Update the preferred navigation mode for subsequent clean runs."""
        if not self.robot:
            return
        self.robot.preferred_navigation_mode = option
        if not self.robot.is_gen4 and option == NAV_MODE_DEEP:
            self.robot.preferred_fan_speed = MODE_TURBO
        self.coordinator.async_set_updated_data(self.coordinator.data)


class VacuulaCleaningCategorySelect(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], SelectEntity
):
    """Select entity for Gen3 cleaning category ('map' with No-Go lines vs 'house')."""

    _attr_has_entity_name = True
    _attr_translation_key = "cleaning_category"
    _attr_icon = "mdi:floor-plan"
    _attr_options = GEN3_CLEAN_CATEGORIES
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the cleaning category select entity."""
        super().__init__(coordinator)
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_cleaning_category"

    @property
    def robot(self) -> VacuulaRobot | None:
        """Get robot data."""
        if self.coordinator.data and self._serial in self.coordinator.data.robots:
            return self.coordinator.data.robots[self._serial]
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry info for robot."""
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
        """Return True if robot is online."""
        return bool(super().available and self.robot and self.robot.connected)

    @property
    def current_option(self) -> str | None:
        """Return 'map' or 'house'."""
        if not self.robot:
            return None
        return (
            CLEAN_CATEGORY_HOUSE
            if self.robot.preferred_category == 2
            else CLEAN_CATEGORY_MAP
        )

    async def async_select_option(self, option: str) -> None:
        """Update the preferred cleaning category."""
        if not self.robot:
            return
        self.robot.preferred_category = 2 if option == CLEAN_CATEGORY_HOUSE else 4
        self.coordinator.async_set_updated_data(self.coordinator.data)


class VacuulaTargetZoneSelect(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], SelectEntity
):
    """Select entity for choosing a target room zone (or 'all' for full map)."""

    _attr_has_entity_name = True
    _attr_translation_key = "target_zone"
    _attr_icon = "mdi:vector-polygon"

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the target zone select entity."""
        super().__init__(coordinator)
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_target_zone"

    @property
    def robot(self) -> VacuulaRobot | None:
        """Get robot data."""
        if self.coordinator.data and self._serial in self.coordinator.data.robots:
            return self.coordinator.data.robots[self._serial]
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry info for robot."""
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
        """Return True if robot is online."""
        return bool(super().available and self.robot and self.robot.connected)

    @property
    def options(self) -> list[str]:
        """Return 'all' plus all discovered room zone names on the active floorplan."""
        if not self.robot:
            return [ALL_ZONES_OPTION]
        zone_names = [z.name for z in self.robot.zones.values() if z.name]
        seen: set[str] = {ALL_ZONES_OPTION}
        opts = [ALL_ZONES_OPTION]
        for name in zone_names:
            if name not in seen:
                seen.add(name)
                opts.append(name)
        return opts

    @property
    def current_option(self) -> str:
        """Return currently selected target zone (or 'all')."""
        if not self.robot:
            return ALL_ZONES_OPTION
        if self.robot.selected_zone in self.options:
            return self.robot.selected_zone
        return ALL_ZONES_OPTION

    async def async_select_option(self, option: str) -> None:
        """Select target zone for the next vacuum.start action."""
        if not self.robot:
            return
        self.robot.selected_zone = option
        self.coordinator.async_set_updated_data(self.coordinator.data)
