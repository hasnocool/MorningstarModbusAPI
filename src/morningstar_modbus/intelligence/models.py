# src/morningstar_modbus/intelligence/models.py
"""Immutable models for device identity, confidence, and validation evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal

IntelligenceStatus = Literal[
    "verified",
    "probable",
    "family-only",
    "newer-firmware-unverified",
    "generic",
    "invalid",
]
Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class IntelligenceEvidence:
    code: str
    message: str
    weight: float
    passed: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: Severity = "warning"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DeviceIntelligence:
    profile: str
    family: str
    model: str = ""
    serial_number: str = ""
    firmware: str = ""
    hardware_revision: str = ""
    catalog_revision: str = ""
    confidence: float = 0.0
    status: IntelligenceStatus = "family-only"
    capabilities: tuple[str, ...] = ()
    network: tuple[tuple[str, str], ...] = ()
    evidence: tuple[IntelligenceEvidence, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()
    metadata: tuple[tuple[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload

    def updated(self, **changes: object) -> DeviceIntelligence:
        return replace(self, **changes)
