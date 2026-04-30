"""Config flow and options flow for the Sigenergy ESS integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_STEP_CONNECTION = "connection"
_STEP_MENU = "menu"
_STEP_SETTINGS = "settings"
_STEP_CARS = "cars"
_STEP_ADD_CAR = "add_car"
_STEP_REMOVE_CAR = "remove_car"


class SigenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()

            # Basic connectivity check
            from .modbus import SigenModbusClient
            client = SigenModbusClient(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_SLAVE_ID],
            )
            connected = await client.async_connect()
            await client.async_close()

            if not connected:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "Sigenergy ESS"),
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(1, 65535)),
                vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): vol.All(int, vol.Range(1, 247)),
                vol.Required(CONF_NAME, default="Sigenergy ESS"): str,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(10, 300)),
                vol.Required(CONF_READ_ONLY, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SigenOptionsFlow:
        return SigenOptionsFlow(config_entry)


class SigenOptionsFlow(OptionsFlow):
    """Handle options — connection settings and car management."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._pending_car_name: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            choice = user_input.get("action")
            if choice == "settings":
                return await self.async_step_settings()
            elif choice == "cars":
                return await self.async_step_cars()
            elif choice == "done":
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="done"): vol.In(
                        {"settings": "Connection & polling settings", "cars": "Manage cars", "done": "Save & close"}
                    )
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options or self._config_entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(int, vol.Range(10, 300)),
                vol.Required(CONF_READ_ONLY, default=current.get(CONF_READ_ONLY, False)): bool,
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_cars(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        sm = self._get_session_manager()
        cars = sm.get_cars() if sm else {}
        car_summary = "\n".join(
            f"• **{car['name']}** — {car.get('session_count', 0)} sessions, "
            f"{car.get('correct_predictions', 0)} correct"
            for car in cars.values()
        ) or "No cars configured."

        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                return await self.async_step_add_car()
            elif action == "remove":
                return await self.async_step_remove_car()
            else:
                return await self.async_step_menu()

        return self.async_show_form(
            step_id="cars",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="back"): vol.In(
                        {"add": "Add a car", "remove": "Remove a car", "back": "Back"}
                    )
                }
            ),
            description_placeholders={"car_list": car_summary},
        )

    async def async_step_add_car(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            sm = self._get_session_manager()
            if sm:
                await sm.async_add_car(user_input["name"], user_input["color"])
            return await self.async_step_cars()

        return self.async_show_form(
            step_id="add_car",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required("color", default="#808080"): str,
                }
            ),
        )

    async def async_step_remove_car(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        sm = self._get_session_manager()
        cars = sm.get_cars() if sm else {}

        if not cars:
            return await self.async_step_cars()

        if user_input is not None:
            car_name = user_input.get("car")
            car_id = sm.get_car_id_by_name(car_name) if sm and car_name else None
            if sm and car_id:
                await sm.async_remove_car(car_id)
            return await self.async_step_cars()

        car_names = [car["name"] for car in cars.values()]
        return self.async_show_form(
            step_id="remove_car",
            data_schema=vol.Schema(
                {vol.Required("car"): vol.In(car_names)}
            ),
        )

    def _get_session_manager(self):
        """Retrieve the live session manager for this config entry."""
        from homeassistant.core import HomeAssistant
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if entry_data:
            return entry_data.get("session_manager")
        return None
