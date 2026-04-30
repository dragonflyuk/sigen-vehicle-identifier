"""Diagnostics support for the Sigenergy ESS integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics data for a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    session_manager = data.get("session_manager")

    diag: dict[str, Any] = {
        "config_entry": {
            "host": entry.data.get("host"),
            "port": entry.data.get("port"),
            "slave_id": entry.data.get("slave_id"),
            "scan_interval": entry.data.get("scan_interval"),
            "read_only": entry.data.get("read_only"),
            "plant_name": entry.data.get("name"),
        },
        "last_coordinator_data": coordinator.data if coordinator else None,
        "last_update_success": coordinator.last_update_success if coordinator else None,
    }

    if session_manager:
        current = session_manager.get_current_session()
        cars = session_manager.get_cars()
        sessions = session_manager.get_sessions()
        diag["current_session"] = current
        diag["car_profiles"] = cars
        diag["total_sessions_stored"] = len(sessions)
        diag["last_session_summary"] = (
            {k: v for k, v in sessions[-1].items() if k != "timeseries"}
            if sessions
            else None
        )

    return diag
