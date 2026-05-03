"""Binary sensor platform for the Sigen Vehicle Identifier integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_STATES, DOMAIN, RUNNING_STATE_FAULT, RUNNING_STATE_ALARM
from .coordinator import SigenergyDataUpdateCoordinator
from .sigen_entity import SigenergyEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: SigenergyDataUpdateCoordinator = data["coordinator"]
    dc_device = data["dc_charger_device"]

    async_add_entities([
        EVConnectedBinarySensor(coordinator, dc_device, entry.entry_id),
        ChargerFaultBinarySensor(coordinator, dc_device, entry.entry_id),
    ])


class EVConnectedBinarySensor(SigenergyEntity, BinarySensorEntity):
    """True when an EV is physically connected and the session is active."""

    _attr_name = "EV Connected"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator, device_info, entry_id):
        super().__init__(coordinator, device_info, entry_id, "ev_connected")

    @property
    def is_on(self) -> bool:
        state = self._dc_charger_value("dc_charger_running_state")
        return state in ACTIVE_STATES if state is not None else False


class ChargerFaultBinarySensor(SigenergyEntity, BinarySensorEntity):
    """True when the DC charger is in a fault or alarm state."""

    _attr_name = "DC Charger Fault"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_info, entry_id):
        super().__init__(coordinator, device_info, entry_id, "dc_charger_fault")

    @property
    def is_on(self) -> bool:
        state = self._dc_charger_value("dc_charger_running_state")
        return state in (RUNNING_STATE_FAULT, RUNNING_STATE_ALARM) if state is not None else False
