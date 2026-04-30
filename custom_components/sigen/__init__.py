"""Sigenergy ESS — Home Assistant custom integration."""
from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .common import dc_charger_device_info, inverter_device_info
from .coordinator import SigenergyDataUpdateCoordinator
from .modbus import SigenModbusClient
from .session_manager import DCChargerSessionManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sigenergy ESS from a config entry."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data.get(CONF_PORT, 502)
    slave_id: int = entry.data.get(CONF_SLAVE_ID, 1)
    scan_interval: int = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    plant_name: str = entry.data.get(CONF_NAME, "Sigenergy")

    modbus_client = SigenModbusClient(host, port, slave_id)
    connected = await modbus_client.async_connect()
    if not connected:
        _LOGGER.error("Could not connect to Sigenergy at %s:%s — will retry", host, port)

    session_manager = DCChargerSessionManager(hass, plant_name)
    await session_manager.async_load()

    coordinator = SigenergyDataUpdateCoordinator(
        hass,
        entry,
        modbus_client,
        session_manager,
        scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "modbus_client": modbus_client,
        "session_manager": session_manager,
        "plant_name": plant_name,
        "dc_charger_device": dc_charger_device_info(entry.entry_id, plant_name),
        "inverter_device": inverter_device_info(entry.entry_id, plant_name),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["modbus_client"].async_close()

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload entry to apply new scan interval."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (idempotent)."""
    if hass.services.has_service(DOMAIN, "confirm_session_car"):
        return

    async def _confirm_session_car(call: ServiceCall) -> None:
        car_id: str = call.data["car_id"]
        session_id: str | None = call.data.get("session_id")
        for entry_data in hass.data.get(DOMAIN, {}).values():
            sm: DCChargerSessionManager = entry_data["session_manager"]
            await sm.async_confirm_car(car_id, session_id)
            # Trigger a coordinator refresh so entities update immediately
            coordinator: SigenergyDataUpdateCoordinator = entry_data["coordinator"]
            await coordinator.async_request_refresh()

    async def _export_sessions(call: ServiceCall) -> None:
        export_path = os.path.join(hass.config.config_dir, "sigen_sessions_export.json")
        for entry_data in hass.data.get(DOMAIN, {}).values():
            sm: DCChargerSessionManager = entry_data["session_manager"]
            await sm.async_export_sessions(export_path)
        _LOGGER.info("Sigenergy session log exported to %s", export_path)

    hass.services.async_register(
        DOMAIN,
        "confirm_session_car",
        _confirm_session_car,
        schema=vol.Schema(
            {
                vol.Required("car_id"): cv.string,
                vol.Optional("session_id"): cv.string,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "export_sessions",
        _export_sessions,
        schema=vol.Schema({}),
    )
