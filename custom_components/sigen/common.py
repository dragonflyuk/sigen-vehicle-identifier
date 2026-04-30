"""Shared helpers for the Sigenergy ESS integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def dc_charger_device_info(entry_id: str, plant_name: str) -> DeviceInfo:
    """Device info for the DC charger child device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_dc_charger")},
        name=f"{plant_name} DC Charger",
        manufacturer="Sigenergy",
        model="DC EV Charger",
        via_device=(DOMAIN, entry_id),
    )


def inverter_device_info(entry_id: str, plant_name: str) -> DeviceInfo:
    """Device info for the inverter (root device)."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=plant_name,
        manufacturer="Sigenergy",
        model="Inverter / ESS",
    )
