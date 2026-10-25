"""Switch platform for Vacuula integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_NEW_ROBOT
from .coordinator import VacuulaDataUpdateCoordinator
from .models import VacuulaRobot

if TYPE_CHECKING:
    from . import VacuulaConfigEntry

SCHEDULE_SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="schedule",
    translation_key="schedule",
    device_class=SwitchDeviceClass.SWITCH,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula switch entities."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    known_serials: set[str] = set()

    def _create_robot_switches(serial: str) -> list[SwitchEntity]:
        return [
            VacuulaRobotScheduleSwitch(
                coordinator, serial, entry, SCHEDULE_SWITCH_DESCRIPTION
            )
        ]

    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.extend(_create_robot_switches(serial))
                known_serials.add(serial)

    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        """Handle dynamic addition of new robots."""
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities(_create_robot_switches(new_robot.serial))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaRobotScheduleSwitch(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], SwitchEntity
):
    """Switch to enable or disable onboard robot schedule."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
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

    @property
    def is_on(self) -> bool:
        """Return True if schedule is enabled."""
        if not self.robot:
            return False
        return self.robot.state.schedule_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable robot schedule."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_set_schedule(
            self._serial, True, robot.robot_type
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable robot schedule."""
        robot = self.robot
        if not robot:
            return
        await self.coordinator.api.async_set_schedule(
            self._serial, False, robot.robot_type
        )
        await self.coordinator.async_request_refresh()
