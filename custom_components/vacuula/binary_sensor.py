"""Binary sensor platform for Vacuula integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
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
class VacuulaServerBinarySensorDescription(BinarySensorEntityDescription):
    """Description of a Vacuula server binary sensor."""

    is_on_fn: Callable[[VacuulaDataUpdateCoordinator], bool]


@dataclass(frozen=True, kw_only=True)
class VacuulaRobotBinarySensorDescription(BinarySensorEntityDescription):
    """Description of a Vacuula robot binary sensor."""

    is_on_fn: Callable[[VacuulaRobot], bool]


SERVER_BINARY_SENSORS: tuple[VacuulaServerBinarySensorDescription, ...] = (
    VacuulaServerBinarySensorDescription(
        key="server_status",
        translation_key="server_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda c: bool(c.data and c.data.server_status),
    ),
)

ROBOT_BINARY_SENSORS: tuple[VacuulaRobotBinarySensorDescription, ...] = (
    VacuulaRobotBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda r: r.state.is_charging,
    ),
    VacuulaRobotBinarySensorDescription(
        key="dustbin",
        translation_key="dustbin",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda r: r.state.is_bin_full,
    ),
    VacuulaRobotBinarySensorDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda r: r.connected,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula binary sensor entities."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []

    # Add server binary sensors
    for desc in SERVER_BINARY_SENSORS:
        entities.append(VacuulaServerBinarySensor(coordinator, entry, desc))

    # Add robot binary sensors
    known_serials: set[str] = set()

    def _create_robot_binary_sensors(serial: str) -> list[BinarySensorEntity]:
        return [
            VacuulaRobotBinarySensor(coordinator, serial, entry, desc)
            for desc in ROBOT_BINARY_SENSORS
        ]

    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.extend(_create_robot_binary_sensors(serial))
                known_serials.add(serial)

    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        """Handle dynamic addition of new robots."""
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities(_create_robot_binary_sensors(new_robot.serial))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaServerBinarySensor(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], BinarySensorEntity
):
    """Vacuula server binary sensor."""

    entity_description: VacuulaServerBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        entry: VacuulaConfigEntry,
        description: VacuulaServerBinarySensorDescription,
    ) -> None:
        """Initialize the server binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"server_{entry.entry_id}_{description.key}"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device registry info for server hub."""
        return {
            "identifiers": {(DOMAIN, f"server_{self._entry.entry_id}")},
            "name": self._entry.title,
            "manufacturer": "Vacuula",
            "model": "Vacuula Server",
            "sw_version": self.coordinator.data.server_info.version
            if self.coordinator.data
            else None,
        }

    @property
    def is_on(self) -> bool:
        """Return True if the binary sensor is on."""
        return self.entity_description.is_on_fn(self.coordinator)


class VacuulaRobotBinarySensor(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], BinarySensorEntity
):
    """Vacuula robot binary sensor."""

    entity_description: VacuulaRobotBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
        description: VacuulaRobotBinarySensorDescription,
    ) -> None:
        """Initialize the robot binary sensor."""
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
        # The 'connected' sensor itself should remain available so users can see when it disconnects
        if self.entity_description.key == "connected":
            return True
        return self.robot.connected

    @property
    def is_on(self) -> bool:
        """Return True if the binary sensor is on."""
        if not self.robot:
            return False
        return self.entity_description.is_on_fn(self.robot)
