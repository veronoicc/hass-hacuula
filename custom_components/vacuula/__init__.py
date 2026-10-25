"""The Vacuula Home Assistant integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VacuulaApiClient, VacuulaError
from .const import (
    ATTR_COMMAND,
    ATTR_MAP_NAME,
    ATTR_MODE,
    ATTR_NAV_MODE,
    ATTR_PARAMS,
    ATTR_SERIAL,
    ATTR_ZONE_NAME,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MODE,
    DEFAULT_NAV_MODE,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
    SERVICE_CLEAN_ZONE,
    SERVICE_DISMISS_ALERT,
    SERVICE_SEND_RAW_COMMAND,
)
from .coordinator import VacuulaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type VacuulaConfigEntry = ConfigEntry[VacuulaDataUpdateCoordinator]

SERVICE_CLEAN_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL): cv.string,
        vol.Required(ATTR_ZONE_NAME): cv.string,
        vol.Optional(ATTR_MAP_NAME): cv.string,
        vol.Optional(ATTR_MODE): cv.string,
        vol.Optional(ATTR_NAV_MODE): cv.string,
    }
)

SERVICE_DISMISS_ALERT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL): cv.string,
    }
)

SERVICE_SEND_RAW_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SERIAL): cv.string,
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Optional(ATTR_PARAMS): dict,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Set up Vacuula from a config entry."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
    use_ssl: bool = entry.data.get(CONF_USE_SSL, False)
    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, True)

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    api = VacuulaApiClient(
        host=host,
        port=port,
        session=session,
        use_ssl=use_ssl,
        verify_ssl=verify_ssl,
    )

    coordinator = VacuulaDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Register Hub device in Device Registry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"server_{entry.entry_id}")},
        name=entry.title,
        manufacturer="Vacuula",
        model="Vacuula Server",
        sw_version=coordinator.data.server_info.version,
        entry_type=dr.DeviceEntryType.SERVICE,
        configuration_url=api.base_url,
    )

    # Start background SSE listener
    entry.async_create_background_task(
        hass,
        api.async_listen_events(coordinator.async_handle_sse_event),
        name=f"{DOMAIN}_sse_{entry.entry_id}",
    )

    # Set up entity platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register integration-level services
    _async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        await coordinator.api.async_close()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_setup_services(hass: HomeAssistant) -> None:
    """Register custom Vacuula services."""
    if hass.services.has_service(DOMAIN, SERVICE_CLEAN_ZONE):
        return

    async def async_handle_clean_zone(call: ServiceCall) -> None:
        """Handle vacuula.clean_zone service."""
        serial: str = call.data[ATTR_SERIAL]
        zone_name: str = call.data[ATTR_ZONE_NAME].strip().lower()
        map_name_filter: str | None = (
            call.data[ATTR_MAP_NAME].strip().lower()
            if ATTR_MAP_NAME in call.data
            else None
        )
        mode: str = call.data.get(ATTR_MODE, DEFAULT_MODE)
        nav_mode: str = call.data.get(ATTR_NAV_MODE, DEFAULT_NAV_MODE)

        # Locate coordinator and robot
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
            if (
                not coordinator
                or not coordinator.data
                or serial not in coordinator.data.robots
            ):
                continue

            robot = coordinator.data.robots[serial]
            target_zone = None
            for zone in robot.zones.values():
                if zone.name.lower() == zone_name and (
                    map_name_filter is None
                    or (zone.map_name and zone.map_name.lower() == map_name_filter)
                ):
                    target_zone = zone
                    break

            if not target_zone:
                raise HomeAssistantError(
                    f"Zone '{call.data[ATTR_ZONE_NAME]}' not found for robot {serial}"
                )

            try:
                await coordinator.api.async_start_cleaning(
                    serial=serial,
                    robot_type=robot.robot_type,
                    mode=mode,
                    nav_mode=nav_mode,
                    map_id=target_zone.map_id,
                    zone_ids=[target_zone.id],
                )
            except VacuulaError as err:
                raise HomeAssistantError(
                    f"Failed to start zone cleaning: {err}"
                ) from err
            return

        raise HomeAssistantError(f"Robot with serial '{serial}' not found")

    async def async_handle_dismiss_alert(call: ServiceCall) -> None:
        """Handle vacuula.dismiss_alert service."""
        serial: str = call.data[ATTR_SERIAL]
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
            if coordinator and coordinator.data and serial in coordinator.data.robots:
                try:
                    await coordinator.api.async_dismiss_alert(serial)
                except VacuulaError as err:
                    raise HomeAssistantError(f"Failed to dismiss alert: {err}") from err
                return
        raise HomeAssistantError(f"Robot with serial '{serial}' not found")

    async def async_handle_send_raw_command(call: ServiceCall) -> None:
        """Handle vacuula.send_raw_command service."""
        serial: str = call.data[ATTR_SERIAL]
        command: str = call.data[ATTR_COMMAND]
        params: dict[str, Any] | None = call.data.get(ATTR_PARAMS)

        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: VacuulaDataUpdateCoordinator = entry.runtime_data
            if coordinator and coordinator.data and serial in coordinator.data.robots:
                try:
                    await coordinator.api.async_send_raw_command(
                        serial, command, params
                    )
                except VacuulaError as err:
                    raise HomeAssistantError(
                        f"Failed to send raw command: {err}"
                    ) from err
                return
        raise HomeAssistantError(f"Robot with serial '{serial}' not found")

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_ZONE,
        async_handle_clean_zone,
        schema=SERVICE_CLEAN_ZONE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISMISS_ALERT,
        async_handle_dismiss_alert,
        schema=SERVICE_DISMISS_ALERT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        async_handle_send_raw_command,
        schema=SERVICE_SEND_RAW_COMMAND_SCHEMA,
    )
