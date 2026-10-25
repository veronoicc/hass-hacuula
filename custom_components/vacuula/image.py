"""Image platform for Vacuula robot floor maps and last cleaning run maps."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_NEW_ROBOT
from .coordinator import VacuulaDataUpdateCoordinator
from .map_renderer import compute_cropped_zones, render_map_png
from .models import VacuulaRobot

if TYPE_CHECKING:
    from . import VacuulaConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula map image entities with dynamic robot discovery."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    known_serials: set[str] = set()

    def _create_images(serial: str) -> list[ImageEntity]:
        return [
            VacuulaFloorMapImage(coordinator, serial, entry),
            VacuulaLastRunMapImage(coordinator, serial, entry),
        ]

    entities: list[ImageEntity] = []
    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.extend(_create_images(serial))
                known_serials.add(serial)

    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities(_create_images(new_robot.serial))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaFloorMapImage(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], ImageEntity
):
    """Image entity rendering the robot's active floor plan and room zones."""

    _attr_has_entity_name = True
    _attr_translation_key = "floor_map"
    _attr_icon = "mdi:floor-plan"
    _attr_content_type = "image/png"

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the floor map image entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_floor_map"
        self._cached_key: tuple[str | None, int] | None = None
        self._cached_png: bytes | None = None
        self._attr_image_last_updated = datetime.now(UTC)

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
        """Remain available while server is reachable and floor map is loaded."""
        return bool(
            self.coordinator.last_update_success
            and self.robot is not None
            and self.robot.floormap is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return metadata about the active floor plan and interactive cropped zones."""
        robot = self.robot
        if not robot:
            return {}
        return {
            "serial": self._serial,
            "map_id": robot.active_map_id,
            "map_name": robot.active_map_name,
            "zones": compute_cropped_zones(robot.floormap, robot.boundaries),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate cache and bump timestamp when map or boundaries change."""
        robot = self.robot
        if robot:
            new_key = (robot.active_map_id, len(robot.boundaries))
            if new_key != self._cached_key:
                self._attr_image_last_updated = datetime.now(UTC)
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return rendered PNG bytes of the active floor plan."""
        robot = self.robot
        if not robot or not robot.floormap:
            return None
        key = (robot.active_map_id, len(robot.boundaries))
        if key == self._cached_key and self._cached_png is not None:
            return self._cached_png

        hass = self.hass or self.coordinator.hass
        png = await hass.async_add_executor_job(
            render_map_png, robot.floormap, robot.boundaries, None
        )
        self._cached_key = key
        self._cached_png = png
        return png


class VacuulaLastRunMapImage(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], ImageEntity
):
    """Image entity rendering the latest cleaning run path overlaid on the floor plan."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_run_map"
    _attr_icon = "mdi:map-check-outline"
    _attr_content_type = "image/png"

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the last run map image entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_last_run_map"
        self._cached_key: tuple[str | None, str | None, int] | None = None
        self._cached_png: bytes | None = None
        self._attr_image_last_updated = datetime.now(UTC)

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
        """Remain available while server is reachable and run or floor map is loaded."""
        return bool(
            self.coordinator.last_update_success
            and self.robot is not None
            and (self.robot.last_runmap is not None or self.robot.floormap is not None)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return metadata about the latest cleaning run."""
        robot = self.robot
        if not robot or not robot.last_run:
            return {}
        return {
            "serial": self._serial,
            "run_id": robot.last_run.get("id"),
            "cleaned_area_m2": robot.last_clean_area,
            "start_at": robot.last_run.get("start_at"),
            "end_at": robot.last_run.get("end_at"),
            "status": robot.last_run.get("status"),
            "zones": compute_cropped_zones(robot.floormap, robot.boundaries),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate cache and bump timestamp when last run changes."""
        robot = self.robot
        if robot:
            run_id = robot.last_run.get("id") if robot.last_run else None
            new_key = (
                robot.active_map_id,
                run_id,
                len(robot.boundaries),
            )
            if new_key != self._cached_key:
                self._attr_image_last_updated = datetime.now(UTC)
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return rendered PNG bytes of the latest cleaning run overlaid on the floor map."""
        robot = self.robot
        if not robot or (not robot.last_runmap and not robot.floormap):
            return None
        run_id = robot.last_run.get("id") if robot.last_run else None
        key = (robot.active_map_id, run_id, len(robot.boundaries))
        if key == self._cached_key and self._cached_png is not None:
            return self._cached_png

        hass = self.hass or self.coordinator.hass
        png = await hass.async_add_executor_job(
            render_map_png, robot.floormap, robot.boundaries, robot.last_runmap
        )
        self._cached_key = key
        self._cached_png = png
        return png
