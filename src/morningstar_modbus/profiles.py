# src/morningstar_modbus/profiles.py
"""Compatibility exports for the structured Morningstar device catalog."""

from __future__ import annotations

from morningstar_modbus.catalog.families.tristar_mppt import TRISTAR_MPPT
from morningstar_modbus.catalog.profile import CatalogProfile
from morningstar_modbus.catalog.registry import get_profile, select_profile
from morningstar_modbus.catalog.scaling import fixed_point_scale, signed_16
from morningstar_modbus.catalog.types import RegisterBlock
from morningstar_modbus.models import RegisterValue
from morningstar_modbus.transport import ReadOnlyModbusClient


class TriStarMpptProfile(CatalogProfile):
    """Backward-compatible TriStar MPPT profile backed by the catalog."""

    def __init__(self) -> None:
        super().__init__(TRISTAR_MPPT)


class GenericProfile:
    """Backward-compatible arbitrary raw register profile."""

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


__all__ = [
    "CatalogProfile",
    "GenericProfile",
    "RegisterBlock",
    "TriStarMpptProfile",
    "fixed_point_scale",
    "get_profile",
    "select_profile",
    "signed_16",
]
