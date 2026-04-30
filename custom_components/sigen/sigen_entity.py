"""Base entity for the Sigenergy ESS integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SigenergyDataUpdateCoordinator


class SigenergyEntity(CoordinatorEntity[SigenergyDataUpdateCoordinator]):
    """Base class for all Sigenergy entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SigenergyDataUpdateCoordinator,
        device_info: DeviceInfo,
        unique_id_prefix: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{unique_id_prefix}_{key}"
        self._attr_device_info = device_info

    def _dc_charger_value(self, key: str):
        """Convenience accessor for DC charger coordinator data."""
        return (self.coordinator.data or {}).get("dc_charger", {}).get(key)
