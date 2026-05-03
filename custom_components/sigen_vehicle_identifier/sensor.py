"""Sensor platform for the Sigen Vehicle Identifier integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SigenergyDataUpdateCoordinator
from .sigen_entity import SigenergyEntity
from .static_sensor import DC_CHARGER_SENSORS, SigenSensorDescription

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: SigenergyDataUpdateCoordinator = data["coordinator"]
    dc_device = data["dc_charger_device"]
    entry_id = entry.entry_id

    entities: list[SigenSensor] = [
        SigenSensor(coordinator, dc_device, entry_id, description)
        for description in DC_CHARGER_SENSORS
    ]
    async_add_entities(entities)


class SigenSensor(SigenergyEntity, SensorEntity):
    """A sensor reading from the Sigenergy coordinator data."""

    entity_description: SigenSensorDescription

    def __init__(
        self,
        coordinator: SigenergyDataUpdateCoordinator,
        device_info,
        entry_id: str,
        description: SigenSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_info, entry_id, description.key)
        self.entity_description = description
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        raw = self._dc_charger_value(self._key)
        if raw is None:
            return None

        # Convert confidence from 0–1 fraction to percentage
        if self._key == "prediction_confidence":
            return round(raw * 100, 1)

        return raw

    @property
    def available(self) -> bool:
        # Identification sensors are available even without an active session
        if self._key in ("identified_car", "prediction_confidence", "session_id",
                          "session_capacity_estimate"):
            return self.coordinator.last_update_success
        # Hardware sensors require EV connection
        connected = (self.coordinator.data or {}).get("dc_charger", {}).get("connected", False)
        return self.coordinator.last_update_success and connected
