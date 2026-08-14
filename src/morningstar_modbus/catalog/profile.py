# src/morningstar_modbus/catalog/profile.py
"""Runtime profile implementation backed by declarative Morningstar catalogs."""

from __future__ import annotations

import asyncio
import logging

from morningstar_modbus.catalog.compatibility import effective_items
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
        self._cached_blocks: set[tuple[str, int, int]] = set()
        self._metadata_lock = asyncio.Lock()

    async def _read_block(
        self,
        client: ReadOnlyModbusClient,
        block: RegisterBlock,
    ) -> list[int]:
        if block.function == "input":
            return await client.read_input_registers(block.address, block.count)
        return await client.read_holding_registers(block.address, block.count)

    async def _read_words(
        self,
        client: ReadOnlyModbusClient,
        function: str,
        address: int,
        count: int,
    ) -> list[int]:
        if function == "input":
            return await client.read_input_registers(address, count)
        return await client.read_holding_registers(address, count)

    async def _load_metadata(self, client: ReadOnlyModbusClient) -> None:
        async with self._metadata_lock:
            for block in self.spec.blocks:
                if not block.cache:
                    continue
                block_key = (block.function, block.address, block.count)
                if block_key in self._cached_blocks:
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
                self._cached_blocks.add(block_key)

    async def read_metadata(self, client: ReadOnlyModbusClient) -> tuple[RegisterValue, ...]:
        """Read stable/profile metadata without performing a full telemetry poll."""
        await self._load_metadata(client)
        async with self._metadata_lock:
            for register in self.spec.registers:
                if register.category != "metadata":
                    continue
                keys = [
                    (register.function, address)
                    for address in range(register.address, register.address + register.words)
                ]
                if all(key in self._metadata for key in keys):
                    continue
                try:
                    words = await self._read_words(
                        client,
                        register.function,
                        register.address,
                        register.words,
                    )
                except Exception as exc:
                    LOGGER.debug(
                        "metadata field unavailable profile=%s register=%s: %s",
                        self.name,
                        register.name,
                        exc,
                    )
                    continue
                for offset, word in enumerate(words):
                    self._metadata[(register.function, register.address + offset)] = word
        return self._decode_named(dict(self._metadata), category="metadata")

    async def poll(
        self,
        client: ReadOnlyModbusClient,
        *,
        firmware: object = "",
    ) -> tuple[RegisterValue, ...]:
        await self._load_metadata(client)
        words_by_key = dict(self._metadata)

        for block in effective_items(self.spec.blocks, firmware):
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

        values.extend(self._decode_named(words_by_key, firmware=firmware))
        return tuple(values)

    def _decode_named(
        self,
        words_by_key: dict[tuple[str, int], int],
        *,
        category: str | None = None,
        firmware: object = "",
    ) -> tuple[RegisterValue, ...]:
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
        values: list[RegisterValue] = []
        for register in effective_items(self.spec.registers, firmware):
            if category is not None and register.category != category:
                continue
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
