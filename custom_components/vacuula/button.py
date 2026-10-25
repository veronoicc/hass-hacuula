"""Button platform for Vacuula integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_NEW_ROBOT
from .coordinator import VacuulaDataUpdateCoordinator
from .models import VacuulaRobot

if TYPE_CHECKING:
    from . import VacuulaConfigEntry


@dataclass(frozen=True, kw_only=True)
class VacuulaRobotButtonDescription(ButtonEntityDescription):
    """Description of a Vacuula robot button."""

    press_fn: Callable[
        [VacuulaDataUpdateCoordinator, VacuulaRobot], Coroutine[Any, Any, None]
    ]
    supported_fn: Callable[[VacuulaRobot], bool] = lambda _: True


async def _async_press_locate(
    coordinator: VacuulaDataUpdateCoordinator, robot: VacuulaRobot
) -> None:
    """Press locate button."""
    await coordinator.api.async_find_me(robot.serial, robot.robot_type)


async def _async_press_dismiss_alert(
    coordinator: VacuulaDataUpdateCoordinator, robot: VacuulaRobot
) -> None:
    """Press dismiss alert button."""
    await coordinator.api.async_dismiss_alert(robot.serial)
    await coordinator.async_request_refresh()


ROBOT_BUTTONS: tuple[VacuulaRobotButtonDescription, ...] = (
    VacuulaRobotButtonDescription(
        key="locate",
        translation_key="locate",
        device_class=ButtonDeviceClass.IDENTIFY,
        press_fn=_async_press_locate,
    ),
    VacuulaRobotButtonDescription(
        key="dismiss_alert",
        translation_key="dismiss_alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=_async_press_dismiss_alert,
        supported_fn=lambda r: not r.is_gen4,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula button entities."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    known_serials: set[str] = set()

    def _create_robot_buttons(serial: str) -> list[ButtonEntity]:
        robot = coordinator.data.robots.get(serial)
        if not robot:
            return []
        return [
            VacuulaRobotButton(coordinator, serial, entry, desc)
            for desc in ROBOT_BUTTONS
            if desc.supported_fn(robot)
        ]

    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.extend(_create_robot_buttons(serial))
                known_serials.add(serial)

    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        """Handle dynamic addition of new robots."""
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities(_create_robot_buttons(new_robot.serial))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaRobotButton(CoordinatorEntity[VacuulaDataUpdateCoordinator], ButtonEntity):
    """Vacuula robot button entity."""

    entity_description: VacuulaRobotButtonDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
        description: VacuulaRobotButtonDescription,
    ) -> None:
        """Initialize the robot button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._serial = serial
        self._entry = entry
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def robot(self) -> VacuulaRobot | None:
        """Get robot object."""
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
        """Return availability."""
        if not super().available or not self.robot:
            return False
        return self.robot.connected

    async def async_press(self) -> None:
        """Press the button."""
        robot = self.robot
        if not robot:
            return
        await self.entity_description.press_fn(self.coordinator, robot)
