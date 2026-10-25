"""Diagnostics support for Vacuula."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import VacuulaConfigEntry

TO_REDACT = {
    CONF_HOST,
    "ip",
    "serial",
    "serial_number",
    "secret",
    "token",
    "key",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    robots_data: dict[str, Any] = {}

    if coordinator.data and coordinator.data.robots:
        for serial, robot in coordinator.data.robots.items():
            robots_data[serial] = {
                "name": robot.name,
                "model": robot.model,
                "robot_type": robot.robot_type,
                "is_gen4": robot.is_gen4,
                "connected": robot.connected,
                "firmware": robot.firmware,
                "state": {
                    "action": robot.state.action_description,
                    "error": robot.state.error,
                    "battery_level": robot.state.battery_level,
                    "is_charging": robot.state.is_charging,
                    "is_docked": robot.state.is_docked,
                    "is_bin_full": robot.state.is_bin_full,
                    "schedule_enabled": robot.state.schedule_enabled,
                },
                "maps_count": len(robot.maps),
                "zones_count": len(robot.zones),
                "zones": [
                    {"id": z.id, "name": z.name, "map_name": z.map_name}
                    for z in robot.zones.values()
                ],
            }

    diag_data = {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "server_info": (
            {
                "version": coordinator.data.server_info.version,
                "ports": coordinator.data.server_info.ports,
                "timezone": coordinator.data.server_info.timezone,
            }
            if coordinator.data
            else None
        ),
        "robots_count": len(robots_data),
        "robots": robots_data,
    }

    return async_redact_data(diag_data, TO_REDACT)
