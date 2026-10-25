"""Sensor platform for Vacuula integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
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
class VacuulaServerSensorDescription(SensorEntityDescription):
    """Description of a Vacuula server sensor."""

    value_fn: Callable[[VacuulaDataUpdateCoordinator], Any]


@dataclass(frozen=True, kw_only=True)
class VacuulaRobotSensorDescription(SensorEntityDescription):
    """Description of a Vacuula robot sensor."""

    value_fn: Callable[[VacuulaRobot], Any]


SERVER_SENSORS: tuple[VacuulaServerSensorDescription, ...] = (
    VacuulaServerSensorDescription(
        key="server_version",
        translation_key="server_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.server_info.version if c.data else None,
    ),
    VacuulaServerSensorDescription(
        key="connected_robots",
        translation_key="connected_robots",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: (
            sum(1 for r in c.data.robots.values() if r.connected) if c.data else 0
        ),
    ),
)

ROBOT_SENSORS: tuple[VacuulaRobotSensorDescription, ...] = (
    VacuulaRobotSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.state.battery_level,
    ),
    VacuulaRobotSensorDescription(
        key="current_action",
        translation_key="current_action",
        value_fn=lambda r: r.state.action_description,
    ),
    VacuulaRobotSensorDescription(
        key="error",
        translation_key="error",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda r: r.state.error,
    ),
    VacuulaRobotSensorDescription(
        key="last_clean_area",
        translation_key="last_clean_area",
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.last_clean_area,
    ),
    VacuulaRobotSensorDescription(
        key="last_clean_duration",
        translation_key="last_clean_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.last_clean_duration,
    ),
    VacuulaRobotSensorDescription(
        key="total_cleans",
        translation_key="total_cleans",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda r: r.total_cleans,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula sensor entities."""
    coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # Add server sensors
    for desc in SERVER_SENSORS:
        entities.append(VacuulaServerSensor(coordinator, entry, desc))

    # Add robot sensors
    known_serials: set[str] = set()

    def _create_robot_sensors(serial: str) -> list[SensorEntity]:
        return [
            VacuulaRobotSensor(coordinator, serial, entry, desc)
            for desc in ROBOT_SENSORS
        ]

    if coordinator.data and coordinator.data.robots:
        for serial in coordinator.data.robots:
            if serial not in known_serials:
                entities.extend(_create_robot_sensors(serial))
                known_serials.add(serial)

    async_add_entities(entities)

    @callback
    def _async_add_new_robot(new_robot: VacuulaRobot) -> None:
        """Handle dynamic addition of new robots."""
        if new_robot.serial not in known_serials:
            known_serials.add(new_robot.serial)
            async_add_entities(_create_robot_sensors(new_robot.serial))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_ROBOT.format(entry.entry_id),
            _async_add_new_robot,
        )
    )


class VacuulaServerSensor(
    CoordinatorEntity[VacuulaDataUpdateCoordinator], SensorEntity
):
    """Vacuula server sensor."""

    entity_description: VacuulaServerSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        entry: VacuulaConfigEntry,
        description: VacuulaServerSensorDescription,
    ) -> None:
        """Initialize the server sensor."""
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
    def native_value(self) -> Any:
        """Return sensor native value."""
        return self.entity_description.value_fn(self.coordinator)


class VacuulaRobotSensor(CoordinatorEntity[VacuulaDataUpdateCoordinator], SensorEntity):
    """Vacuula robot sensor."""

    entity_description: VacuulaRobotSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaDataUpdateCoordinator,
        serial: str,
        entry: VacuulaConfigEntry,
        description: VacuulaRobotSensorDescription,
    ) -> None:
        """Initialize the robot sensor."""
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
    def native_value(self) -> Any:
        """Return sensor native value."""
        if not self.robot:
            return None
        return self.entity_description.value_fn(self.robot)
