"""Data models for the Vacuula integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VacuulaServerInfo:
    """Vacuula server metadata."""

    version: str = "unknown"
    ports: dict[str, Any] = field(default_factory=dict)
    timezone: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class VacuulaZone:
    """Cleanable boundary/zone representation."""

    id: str
    name: str
    map_id: str
    map_name: str
    boundary_type: str = "polygon"
    vertices: list[list[float]] = field(default_factory=list)


@dataclass
class VacuulaMap:
    """Robot persistent floor map."""

    id: str
    name: str
    zones: list[VacuulaZone] = field(default_factory=list)


@dataclass
class VacuulaRobotState:
    """Parsed robot runtime state."""

    state_code: int | None = None
    action_code: int | None = None
    action_description: str = "idle"
    error: str | None = None
    battery_level: int = 0
    is_charging: bool = False
    is_docked: bool = False
    is_bin_full: bool = False
    schedule_enabled: bool = False
    raw_state: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls, raw: dict[str, Any], robot_type: str = "gen3"
    ) -> VacuulaRobotState:
        """Parse raw state dictionary for Gen3 or Gen4 robots."""
        if not raw:
            return cls()

        data = raw.get("data", raw)
        is_gen4 = "gen4" in robot_type.lower() or any(
            g in robot_type.lower() for g in ("d8", "d9", "d10")
        )

        if is_gen4 or "battery" in data or "status" in data:
            return cls._parse_gen4(data, raw)
        return cls._parse_gen3(data, raw)

    @classmethod
    def _parse_gen3(
        cls, data: dict[str, Any], raw: dict[str, Any]
    ) -> VacuulaRobotState:
        """Parse Neato Gen3 getRobotState response."""
        state_code = data.get("state")
        action_code = data.get("action")
        error = data.get("error")
        details = data.get("details", {})

        action_names = {
            0: "idle",
            1: "house_cleaning",
            2: "spot_cleaning",
            3: "manual_cleaning",
            4: "docking",
            5: "user_interaction_needed",
            6: "suspended_cleaning",
            7: "updating",
            8: "copying_logs",
            9: "recovering_location",
            10: "iec_test",
            11: "zone_cleaning",
        }
        action_description = (
            action_names.get(action_code, "unknown")
            if action_code is not None
            else "idle"
        )

        return cls(
            state_code=state_code,
            action_code=action_code,
            action_description=action_description,
            error=str(error) if error else None,
            battery_level=int(details.get("charge", 0)),
            is_charging=bool(details.get("isCharging", False)),
            is_docked=bool(details.get("isDocked", False)),
            is_bin_full=bool(details.get("isBinFull", False)),
            schedule_enabled=bool(details.get("isScheduleEnabled", False)),
            raw_state=raw,
        )

    @classmethod
    def _parse_gen4(
        cls, data: dict[str, Any], raw: dict[str, Any]
    ) -> VacuulaRobotState:
        """Parse Neato Gen4 state.show response."""
        battery = data.get("battery", {})
        status = data.get("status", {})
        dock = data.get("dock", {})
        dirtbin = data.get("dirtbin", {})
        schedule = data.get("schedule", {})

        state_str = str(status.get("state", "idle")).lower()

        # Normalize action description
        if state_str in ("cleaning", "running"):
            action_description = "cleaning"
        elif state_str in ("docking", "returning"):
            action_description = "docking"
        elif state_str in ("docked", "charging"):
            action_description = "docked"
        elif state_str in ("paused", "suspended"):
            action_description = "paused"
        elif state_str == "error":
            action_description = "error"
        else:
            action_description = state_str

        is_docked = bool(dock.get("docked", False)) or state_str == "docked"
        is_charging = bool(battery.get("charging", False))
        is_bin_full = bool(dirtbin.get("alert", False) or dirtbin.get("full", False))

        error = status.get("error") or data.get("error")

        return cls(
            state_code=None,
            action_code=None,
            action_description=action_description,
            error=str(error) if error else None,
            battery_level=int(battery.get("level", battery.get("charge", 0))),
            is_charging=is_charging,
            is_docked=is_docked,
            is_bin_full=is_bin_full,
            schedule_enabled=bool(schedule.get("enabled", False)),
            raw_state=raw,
        )


@dataclass
class VacuulaRobot:
    """Robot data container."""

    serial: str
    name: str
    model: str
    robot_type: str = "gen3"
    connected: bool = True
    firmware: str | None = None
    state: VacuulaRobotState = field(default_factory=VacuulaRobotState)
    maps: list[VacuulaMap] = field(default_factory=list)
    zones: dict[str, VacuulaZone] = field(default_factory=dict)

    @property
    def is_gen4(self) -> bool:
        """Return True if robot is Gen4."""
        t = self.robot_type.lower()
        m = self.model.lower()
        return "gen4" in t or any(g in t or g in m for g in ("d8", "d9", "d10"))


@dataclass
class VacuulaData:
    """Runtime data held in ConfigEntry."""

    server_info: VacuulaServerInfo
    robots: dict[str, VacuulaRobot] = field(default_factory=dict)
    server_status: bool = True
