# src/morningstar_modbus/catalog/profile.py
"""Runtime profile implementation backed by declarative Morningstar catalogs."""

from __future__ import annotations

import asyncio
import logging

from morningstar_modbus.catalog.scaling import decode_value
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec
from morningstar_modbus.models import RegisterValue
from morningstar_modbus.transport import ReadOnlyModbusClient

LOGGER = logging.getLogger(__name__)


class CatalogProfile:
    """Read and decode a Morningstar device using a declarative profile specification."""

    def __init__(self, spec: DeviceProfileSpec) -> None:
        self.spec = spec
        self.name = spec.name
        self._metadata: dict[tuple[str, int], int] = {}
        self._metadata_loaded = False
        self._metadata_lock = asyncio.Lock()

    async def _read_block(
        self,
        client: ReadOnlyModbusClient,
        block: RegisterBlock,
    ) -> list[int]:
        if block.function == "input":
            return await client.read_input_registers(block.address, block.count)
        return await client.read_holding_registers(block.address, block.count)

    async def _load_metadata(self, client: ReadOnlyModbusClient) -> None:
        if self._metadata_loaded:
            return
        async with self._metadata_lock:
            if self._metadata_loaded:
                return
            for block in self.spec.blocks:
                if not block.cache:
                    continue
                try:
                    words = await self._read_block(client, block)
                except Exception as exc:
                    if block.optional:
                        LOGGER.debug(
                            "optional metadata block unavailable profile=%s address=0x%04X: %s",
                            self.name,
                            block.address,
                            exc,
                        )
                        continue
                    raise
                for offset, word in enumerate(words):
                    self._metadata[(block.function, block.address + offset)] = word
            self._metadata_loaded = True

    async def poll(self, client: ReadOnlyModbusClient) -> tuple[RegisterValue, ...]:
        await self._load_metadata(client)
        words_by_key = dict(self._metadata)

        for block in self.spec.blocks:
            if block.cache:
                continue
            try:
                words = await self._read_block(client, block)
            except Exception:
                if block.optional:
                    continue
                raise
            for offset, word in enumerate(words):
                words_by_key[(block.function, block.address + offset)] = word

        values: list[RegisterValue] = []
        ordered_words = sorted(words_by_key.items(), key=lambda item: (item[0][0], item[0][1]))
        for (function, address), word in ordered_words:
            values.append(
                RegisterValue(
                    name=f"{function}_0x{address:04X}",
                    address=address,
                    function=function,
                    raw=(word,),
                    value=word,
                )
            )

        holding_context = {
            address: word
            for (function, address), word in words_by_key.items()
            if function == "holding"
        }
        input_context = {
            address: word
            for (function, address), word in words_by_key.items()
            if function == "input"
        }
        for register in self.spec.registers:
            context = holding_context if register.function == "holding" else input_context
            addresses = range(register.address, register.address + register.words)
            raw = tuple(context[address] for address in addresses if address in context)
            if len(raw) != register.words:
                continue
            value = self._decode_register(register, raw, context)
            values.append(
                RegisterValue(
                    name=register.name,
                    address=register.address,
                    function=register.function,
                    raw=raw,
                    value=value,
                    unit=register.unit,
                )
            )
        return tuple(values)

    @staticmethod
    def _decode_register(
        register: RegisterSpec,
        raw: tuple[int, ...],
        context: dict[int, int],
    ) -> float | int | str:
        value = decode_value(register.decoder, raw, context)
        if register.enum and isinstance(value, int):
            return dict(register.enum).get(value, f"UNKNOWN_{value}")
        if register.bits and isinstance(value, int):
            active = [name for bit, name in register.bits if value & (1 << bit)]
            return ",".join(active) if active else "NONE"
        return value
