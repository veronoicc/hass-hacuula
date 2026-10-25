"""Config flow for Vacuula integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    VacuulaApiClient,
    VacuulaAuthError,
    VacuulaConnectionError,
    VacuulaError,
    VacuulaServerInfo,
)
from .const import (
    CLEANING_MODES,
    CONF_DEFAULT_MODE,
    CONF_DEFAULT_NAV_MODE,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MODE,
    DEFAULT_NAV_MODE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NAVIGATION_MODES,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: Any, data: dict[str, Any]) -> VacuulaServerInfo:
    """Validate that the host and port can connect to a Vacuula server."""
    host: str = data[CONF_HOST].strip()
    port: int = data.get(CONF_PORT, DEFAULT_PORT)
    use_ssl: bool = data.get(CONF_USE_SSL, False)
    verify_ssl: bool = data.get(CONF_VERIFY_SSL, True)

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    api = VacuulaApiClient(
        host=host,
        port=port,
        session=session,
        use_ssl=use_ssl,
        verify_ssl=verify_ssl,
    )

    try:
        return await api.async_get_server_info()
    except VacuulaAuthError as err:
        raise InvalidAuth from err
    except VacuulaConnectionError as err:
        raise CannotConnect from err
    except VacuulaError as err:
        raise InvalidServer from err


class VacuulaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vacuula."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            unique_id = f"vacuula_{host.lower()}_{port}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidServer:
                errors["base"] = "invalid_server"
            except Exception:
                _LOGGER.exception("Unexpected exception in config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Vacuula ({host})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_USE_SSL, default=False): bool,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            new_unique_id = f"vacuula_{host.lower()}_{port}"

            await self.async_set_unique_id(new_unique_id)
            self._abort_if_unique_id_configured(updates=user_input)

            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidServer:
                errors["base"] = "invalid_server"
            except Exception:
                _LOGGER.exception("Unexpected exception during reconfiguration")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, **user_input},
                    unique_id=new_unique_id,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str,
                vol.Optional(
                    CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                ): int,
                vol.Optional(
                    CONF_USE_SSL, default=entry.data.get(CONF_USE_SSL, False)
                ): bool,
                vol.Optional(
                    CONF_VERIFY_SSL, default=entry.data.get(CONF_VERIFY_SSL, True)
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return VacuulaOptionsFlowHandler(config_entry)


class VacuulaOptionsFlowHandler(OptionsFlow):
    """Handle Vacuula options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage Vacuula options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        default_mode = options.get(CONF_DEFAULT_MODE, DEFAULT_MODE)
        default_nav_mode = options.get(CONF_DEFAULT_NAV_MODE, DEFAULT_NAV_MODE)

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=300,
                        step=5,
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(CONF_DEFAULT_MODE, default=default_mode): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=m, label=m.capitalize())
                            for m in CLEANING_MODES
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_DEFAULT_NAV_MODE, default=default_nav_mode
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=n, label=n.replace("_", " ").capitalize()
                            )
                            for n in NAVIGATION_MODES
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidServer(HomeAssistantError):
    """Error to indicate unexpected server response."""
