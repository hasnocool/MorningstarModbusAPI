# src/morningstar_modbus/catalog/types.py
"""Declarative types for Morningstar register catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RegisterFunction = Literal["holding", "input"]
RegisterCategory = Literal["telemetry", "state", "fault", "alarm", "metadata", "network", "configuration"]


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    """A contiguous read-only Modbus register block."""

    address: int
    count: int
    function: RegisterFunction = "holding"
    category: RegisterCategory = "telemetry"
    optional: bool = False
    cache: bool = False
    since_firmware: str | None = None
    until_firmware: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterSpec:
    """A named register or multi-word field inside a device catalog."""

    name: str
    address: int
    function: RegisterFunction = "holding"
    words: int = 1
    decoder: str = "raw"
    unit: str | None = None
    category: RegisterCategory = "telemetry"
    enum: tuple[tuple[int, str], ...] = ()
    bits: tuple[tuple[int, str], ...] = ()
    description: str = ""
    since_firmware: str | None = None
    until_firmware: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceProfileSpec:
    """Complete catalog metadata for one Morningstar product family."""

    name: str
    family: str
    aliases: tuple[str, ...]
    source_id: str
    source_url: str
    blocks: tuple[RegisterBlock, ...]
    registers: tuple[RegisterSpec, ...]
    capabilities: tuple[str, ...] = ()
    network: tuple[tuple[str, str], ...] = ()
    detection_priority: int = 100
    coverage: str = "documented"
    notes: str = ""
    catalog_revision: str = ""
    firmware_verified_min: str | None = None
    firmware_verified_max: str | None = None

    @property
    def register_names(self) -> tuple[str, ...]:
        return tuple(register.name for register in self.registers)

    def to_dict(self, *, include_registers: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "family": self.family,
            "aliases": list(self.aliases),
            "source_id": self.source_id,
            "source_url": self.source_url,
            "capabilities": list(self.capabilities),
            "network": dict(self.network),
            "detection_priority": self.detection_priority,
            "coverage": self.coverage,
            "notes": self.notes,
            "catalog_revision": self.catalog_revision,
            "firmware_verified_min": self.firmware_verified_min,
            "firmware_verified_max": self.firmware_verified_max,
            "blocks": [
                {
                    "address": block.address,
                    "count": block.count,
                    "function": block.function,
                    "category": block.category,
                    "optional": block.optional,
                    "cache": block.cache,
                    "since_firmware": block.since_firmware,
                    "until_firmware": block.until_firmware,
                }
                for block in self.blocks
            ],
            "register_count": len(self.registers),
        }
        if include_registers:
            payload["registers"] = [
                {
                    "name": register.name,
                    "address": register.address,
                    "function": register.function,
                    "words": register.words,
                    "decoder": register.decoder,
                    "unit": register.unit,
                    "category": register.category,
                    "enum": dict(register.enum),
                    "bits": dict(register.bits),
                    "description": register.description,
                    "since_firmware": register.since_firmware,
                    "until_firmware": register.until_firmware,
                }
                for register in self.registers
            ]
        return payload
