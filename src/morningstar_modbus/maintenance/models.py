# src/morningstar_modbus/maintenance/models.py
"""Structured records shared by the catalog-maintenance pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_id: str
    title: str
    url: str
    filename: str
    format: str
    version: str = ""
    document_id: str = ""
    document_date: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    source: SourceDocument
    path: str
    sha256: str
    size_bytes: int
    etag: str = ""
    last_modified: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source"] = self.source.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class RegisterObservation:
    source_id: str
    address: int
    label: str
    page: int
    source_text: str
    confidence: float

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:04X}"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["address_hex"] = self.address_hex
        return payload


@dataclass(frozen=True, slots=True)
class ProposedChange:
    profile: str
    source_id: str
    change_type: str
    address: int
    observed_label: str
    declared_names: tuple[str, ...]
    confidence: float
    page: int
    source_text: str

    @property
    def address_hex(self) -> str:
        return f"0x{self.address:04X}"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["address_hex"] = self.address_hex
        return payload
