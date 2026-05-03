"""Modbus TCP client for the Sigen Vehicle Identifier integration."""
from __future__ import annotations

import logging
from typing import Any

from pymodbus.client import AsyncModbusTcpClient, ModbusClientMixin
from pymodbus.exceptions import ModbusException

from .const import (
    REG_DC_VOLTAGE,
    REG_DC_START_STOP,
)

_LOGGER = logging.getLogger(__name__)

# Register addresses are used exactly as documented by Sigenergy (no base offset).
# Confirmed against the TypQxQ/Sigenergy-Local-Modbus reference implementation.

# Burst read: 31500–31513 inclusive = 14 registers
_DC_CHARGER_REG_COUNT = 14


class SigenModbusClient:
    """Async Modbus TCP client wrapping pymodbus 3.13+."""

    def __init__(self, host: str, port: int, slave_id: int) -> None:
        self._host = host
        self._port = port
        self._slave_id = slave_id
        self._client: AsyncModbusTcpClient | None = None

    async def async_connect(self) -> bool:
        """Open the TCP connection."""
        self._client = AsyncModbusTcpClient(self._host, port=self._port)
        connected = await self._client.connect()
        if not connected:
            _LOGGER.error("Failed to connect to Sigenergy at %s:%s", self._host, self._port)
        return connected

    async def async_close(self) -> None:
        """Close the TCP connection."""
        if self._client:
            self._client.close()
            self._client = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.connected

    async def async_read_dc_charger(self) -> dict[str, Any] | None:
        """Read all DC charger input registers.

        Returns None when no EV is connected (device raises Modbus exception)
        or when the TCP connection is unavailable.
        """
        if not self.connected:
            return None

        try:
            result = await self._client.read_input_registers(
                REG_DC_VOLTAGE,
                count=_DC_CHARGER_REG_COUNT,
                device_id=self._slave_id,
            )
        except ModbusException as err:
            _LOGGER.debug("DC charger read exception (likely no EV connected): %s", err)
            return None

        if result.isError():
            _LOGGER.debug("DC charger returned Modbus error — no EV connected")
            return None

        regs = result.registers

        # Use pymodbus convert_from_registers for correct endianness handling
        power_raw = ModbusClientMixin.convert_from_registers(
            regs[2:4], data_type=ModbusClientMixin.DATATYPE.INT32
        )
        capacity_raw = ModbusClientMixin.convert_from_registers(
            regs[5:7], data_type=ModbusClientMixin.DATATYPE.UINT32
        )
        duration_raw = ModbusClientMixin.convert_from_registers(
            regs[7:9], data_type=ModbusClientMixin.DATATYPE.UINT32
        )

        return {
            "dc_charger_vehicle_battery_voltage": regs[0] / 10.0,
            "dc_charger_charging_current": regs[1] / 10.0,
            "dc_charger_output_power": power_raw / 1000.0,
            "dc_charger_vehicle_soc": regs[4] / 10.0,
            "dc_charger_current_charging_capacity": capacity_raw / 100.0,
            "dc_charger_current_charging_duration": int(duration_raw),
            # regs[9..12] are reserved gap registers (not documented)
            "dc_charger_running_state": regs[13],
        }

    async def async_write_dc_charger_start_stop(self, value: int, read_only: bool) -> bool:
        """Write start (0) or stop (1) to the DC charger holding register."""
        if read_only:
            _LOGGER.warning("Write blocked: integration is in read-only mode")
            return False
        if not self.connected:
            return False
        try:
            result = await self._client.write_register(
                REG_DC_START_STOP,
                value,
                device_id=self._slave_id,
            )
            return not result.isError()
        except ModbusException as err:
            _LOGGER.error("Failed to write DC charger start/stop: %s", err)
            return False
