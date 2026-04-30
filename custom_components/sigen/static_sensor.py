"""Static sensor entity descriptions for the Sigenergy ESS DC charger."""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)


@dataclass(frozen=True, kw_only=True)
class SigenSensorDescription(SensorEntityDescription):
    """Extended sensor description with optional post-processing."""
    # coordinator data section ("dc_charger", etc.)
    data_section: str = "dc_charger"


DC_CHARGER_SENSORS: tuple[SigenSensorDescription, ...] = (
    SigenSensorDescription(
        key="dc_charger_vehicle_battery_voltage",
        name="Vehicle Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        suggested_display_precision=1,
    ),
    SigenSensorDescription(
        key="dc_charger_charging_current",
        name="Charging Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-dc",
        suggested_display_precision=1,
    ),
    SigenSensorDescription(
        key="dc_charger_output_power",
        name="Output Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        suggested_display_precision=2,
    ),
    SigenSensorDescription(
        key="dc_charger_vehicle_soc",
        name="Vehicle SOC",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
        suggested_display_precision=1,
    ),
    SigenSensorDescription(
        key="dc_charger_current_charging_capacity",
        name="Session Energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:ev-plug-ccs2",
        suggested_display_precision=2,
    ),
    SigenSensorDescription(
        key="dc_charger_current_charging_duration",
        name="Session Duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SigenSensorDescription(
        key="dc_charger_running_state_name",
        name="Charger State",
        icon="mdi:state-machine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Car identification sensors
    SigenSensorDescription(
        key="identified_car",
        name="Identified Car",
        icon="mdi:car-electric",
    ),
    SigenSensorDescription(
        key="prediction_confidence",
        name="Car ID Confidence",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    SigenSensorDescription(
        key="session_capacity_estimate",
        name="Session Battery Capacity Estimate",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-unknown",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    SigenSensorDescription(
        key="session_id",
        name="Session ID",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)
