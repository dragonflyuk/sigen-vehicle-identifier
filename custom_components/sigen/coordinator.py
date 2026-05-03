"""Data update coordinator for the Sigen Vehicle Identifier integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    RUNNING_STATE_NAMES,
)
from .modbus import SigenModbusClient
from .session_manager import DCChargerSessionManager

_LOGGER = logging.getLogger(__name__)


class SigenergyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the Sigenergy DC charger and passes data to the session manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        modbus_client: SigenModbusClient,
        session_manager: DCChargerSessionManager,
        scan_interval: int,
    ) -> None:
        self.modbus_client = modbus_client
        self.session_manager = session_manager
        self.read_only: bool = entry.data.get("read_only", False)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Modbus and update session state."""
        if not self.modbus_client.connected:
            connected = await self.modbus_client.async_connect()
            if not connected:
                raise UpdateFailed("Cannot connect to Sigenergy Modbus")

        dc_data = await self.modbus_client.async_read_dc_charger()

        # Always pass result to session manager (even None = no EV)
        await self.session_manager.on_data_update(dc_data)

        # Build coordinator data dict
        current_session = self.session_manager.get_current_session()

        dc_section: dict[str, Any] = {}
        if dc_data:
            state_code = dc_data.get("dc_charger_running_state")
            dc_section = {
                **dc_data,
                "dc_charger_running_state_name": RUNNING_STATE_NAMES.get(state_code, "Unknown"),
                "connected": True,
            }
        else:
            dc_section = {"connected": False}

        # Overlay session / prediction data
        if current_session:
            dc_section["identified_car"] = self._car_name(current_session.get("predicted_car_id"))
            dc_section["identified_car_id"] = current_session.get("predicted_car_id")
            dc_section["prediction_confidence"] = current_session.get("prediction_confidence")
            dc_section["prediction_method"] = current_session.get("prediction_method")
            dc_section["session_capacity_estimate"] = current_session.get("estimated_capacity_kwh")
            dc_section["session_id"] = current_session.get("session_id")
        else:
            dc_section.setdefault("identified_car", None)
            dc_section.setdefault("identified_car_id", None)
            dc_section.setdefault("prediction_confidence", None)
            dc_section.setdefault("prediction_method", None)
            dc_section.setdefault("session_capacity_estimate", None)
            dc_section.setdefault("session_id", None)

        return {"dc_charger": dc_section}

    def _car_name(self, car_id: str | None) -> str | None:
        if car_id is None:
            return None
        return self.session_manager.get_cars().get(car_id, {}).get("name")
