# src/morningstar_modbus/profiles.py
"""Register profiles and TriStar MPPT decoding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from morningstar_modbus.models import RegisterValue
from morningstar_modbus.transport import ReadOnlyModbusClient


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    function: str
    address: int
    count: int


class Profile(Protocol):
    name: str

    async def poll(self, client: ReadOnlyModbusClient) -> tuple[RegisterValue, ...]: ...


def signed_16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def fixed_point_scale(high_word: int, low_word: int) -> float:
    return float(high_word & 0xFFFF) + float(low_word & 0xFFFF) / 65536.0


def _metric(
    name: str,
    address: int,
    raw: int,
    value: float | int | str,
    unit: str | None = None,
) -> RegisterValue:
    return RegisterValue(name, address, "holding", (raw,), value, unit)


class TriStarMpptProfile:
    name = "tristar_mppt"

    async def poll(self, client: ReadOnlyModbusClient) -> tuple[RegisterValue, ...]:
        raw = await client.read_holding_registers(0x0000, 0x0050)
        voltage_scale = fixed_point_scale(raw[0x0000], raw[0x0001])
        current_scale = fixed_point_scale(raw[0x0002], raw[0x0003])

        def voltage(address: int) -> float:
            return signed_16(raw[address]) * voltage_scale / 32768.0

        def current(address: int) -> float:
            return signed_16(raw[address]) * current_scale / 32768.0

        def power(address: int) -> float:
            return (raw[address] & 0xFFFF) * voltage_scale * current_scale / 131072.0

        charge_states = {
            0: "START",
            1: "NIGHT_CHECK",
            2: "DISCONNECT",
            3: "NIGHT",
            4: "FAULT",
            5: "MPPT",
            6: "ABSORPTION",
            7: "FLOAT",
            8: "EQUALIZE",
            9: "SLAVE",
        }
        values = [
            _metric("battery_voltage", 0x0018, raw[0x0018], voltage(0x0018), "V"),
            _metric("battery_terminal_voltage", 0x0019, raw[0x0019], voltage(0x0019), "V"),
            _metric("battery_sense_voltage", 0x001A, raw[0x001A], voltage(0x001A), "V"),
            _metric("array_voltage", 0x001B, raw[0x001B], voltage(0x001B), "V"),
            _metric("battery_charge_current", 0x001C, raw[0x001C], current(0x001C), "A"),
            _metric("array_current", 0x001D, raw[0x001D], current(0x001D), "A"),
            _metric("heatsink_temp", 0x0023, raw[0x0023], signed_16(raw[0x0023]), "C"),
            _metric("rts_temp", 0x0024, raw[0x0024], signed_16(raw[0x0024]), "C"),
            _metric("battery_temp", 0x0025, raw[0x0025], signed_16(raw[0x0025]), "C"),
            _metric("faults", 0x002C, raw[0x002C], raw[0x002C]),
            _metric(
                "charge_state",
                0x0032,
                raw[0x0032],
                charge_states.get(raw[0x0032], str(raw[0x0032])),
            ),
            _metric("target_voltage", 0x0033, raw[0x0033], voltage(0x0033), "V"),
            _metric("output_power", 0x003A, raw[0x003A], power(0x003A), "W"),
            _metric("input_power", 0x003B, raw[0x003B], power(0x003B), "W"),
            _metric("daily_charge_wh", 0x0044, raw[0x0044], raw[0x0044], "Wh"),
        ]
        values.extend(
            RegisterValue(f"holding_0x{address:04X}", address, "holding", (word,), word)
            for address, word in enumerate(raw)
        )
        return tuple(values)


class GenericProfile:
    name = "generic"

    def __init__(self, *, address: int = 0, count: int = 16, function: str = "holding") -> None:
        self.address = address
        self.count = count
        self.function = function

    async def poll(self, client: ReadOnlyModbusClient) -> tuple[RegisterValue, ...]:
        if self.function == "input":
            raw = await client.read_input_registers(self.address, self.count)
        else:
            raw = await client.read_holding_registers(self.address, self.count)
        return tuple(
            RegisterValue(
                name=f"{self.function}_0x{self.address + index:04X}",
                address=self.address + index,
                function="input" if self.function == "input" else "holding",
                raw=(word,),
                value=word,
            )
            for index, word in enumerate(raw)
        )


def select_profile(vendor_name: str, product_code: str) -> Profile:
    identity = f"{vendor_name} {product_code}".casefold()
    if "morningstar" in identity and ("tristar" in identity or "ts-mppt" in identity):
        return TriStarMpptProfile()
    return GenericProfile()
