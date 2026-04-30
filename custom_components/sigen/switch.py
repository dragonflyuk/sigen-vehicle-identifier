"""Switch platform — DC charger start / stop."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, RUNNING_STATE_CHARGING, RUNNING_STATE_DISCHARGING
from .coordinator import SigenergyDataUpdateCoordinator
from .modbus import SigenModbusClient
from .sigen_entity import SigenergyEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: SigenergyDataUpdateCoordinator = data["coordinator"]
    modbus_client: SigenModbusClient = data["modbus_client"]
    dc_device = data["dc_charger_device"]

    async_add_entities(
        [DCChargingSwitch(coordinator, modbus_client, dc_device, entry.entry_id)]
    )


class DCChargingSwitch(SigenergyEntity, SwitchEntity):
    """Start / stop DC charging via holding register 41000."""

    _attr_name = "DC Charging"
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: SigenergyDataUpdateCoordinator,
        modbus_client: SigenModbusClient,
        device_info,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, device_info, entry_id, "dc_charging")
        self._modbus_client = modbus_client

    @property
    def is_on(self) -> bool | None:
        state = self._dc_charger_value("dc_charger_running_state")
        if state is None:
            return None
        return state in (RUNNING_STATE_CHARGING, RUNNING_STATE_DISCHARGING)

    @property
    def available(self) -> bool:
        connected = (self.coordinator.data or {}).get("dc_charger", {}).get("connected", False)
        return self.coordinator.last_update_success and connected

    async def async_turn_on(self, **kwargs) -> None:
        await self._modbus_client.async_write_dc_charger_start_stop(
            0, self.coordinator.read_only
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._modbus_client.async_write_dc_charger_start_stop(
            1, self.coordinator.read_only
        )
        await self.coordinator.async_request_refresh()
