"""Select platform — Car on Charger override."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SigenergyDataUpdateCoordinator
from .session_manager import DCChargerSessionManager
from .sigen_entity import SigenergyEntity

_LOGGER = logging.getLogger(__name__)

_NONE_OPTION = "— None —"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: SigenergyDataUpdateCoordinator = data["coordinator"]
    session_manager: DCChargerSessionManager = data["session_manager"]
    dc_device = data["dc_charger_device"]

    async_add_entities(
        [CarOnChargerSelect(coordinator, session_manager, dc_device, entry.entry_id)]
    )


class CarOnChargerSelect(SigenergyEntity, SelectEntity):
    """Select entity for confirming / overriding the identified car."""

    _attr_icon = "mdi:car-electric"
    _attr_name = "Car on Charger"

    def __init__(
        self,
        coordinator: SigenergyDataUpdateCoordinator,
        session_manager: DCChargerSessionManager,
        device_info,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, device_info, entry_id, "car_override")
        self._session_manager = session_manager

    @property
    def options(self) -> list[str]:
        return [_NONE_OPTION] + self._session_manager.get_car_names()

    @property
    def current_option(self) -> str | None:
        session = self._session_manager.get_current_session()
        if session is None:
            return _NONE_OPTION
        confirmed_id = session.get("confirmed_car_id") or session.get("predicted_car_id")
        if confirmed_id is None:
            return _NONE_OPTION
        return self._session_manager.get_cars().get(confirmed_id, {}).get("name", _NONE_OPTION)

    async def async_select_option(self, option: str) -> None:
        if option == _NONE_OPTION:
            return
        car_id = self._session_manager.get_car_id_by_name(option)
        if car_id:
            await self._session_manager.async_confirm_car(car_id)
            await self.coordinator.async_request_refresh()
