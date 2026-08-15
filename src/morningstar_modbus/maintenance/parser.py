# src/morningstar_modbus/maintenance/parser.py
"""Conservative extraction of register-table observations from vendor document text."""

from __future__ import annotations

import re

from morningstar_modbus.maintenance.models import ObservationScope, RegisterObservation

_TABLE_ROW_RE = re.compile(
    r"^\s*0[xX](?P<address>[0-9A-Fa-f]{4})"
    r"(?:\s+(?P<logical>\d{1,5}|-))?"
    r"\s+(?P<label>[A-Za-z][A-Za-z0-9_\[\]./-]{1,})\b"
)
_WEAK_LABELS = {
    "address",
    "and",
    "bit",
    "description",
    "instead",
    "non",
    "output",
    "register",
    "registers",
    "unit",
    "units",
    "value",
    "values",
    "which",
}
_CONTROL_LABEL_RE = re.compile(
    r"(?:^EQTRIG$|^CLEAR_|^RESET$|DISCONNECT$|RECONNECT$|OVERRIDE$|TRIGGER$)",
    re.IGNORECASE,
)
_FLOAT32_PART_RE = re.compile(r"(?:_[01]|_(?:HI|LO))$", re.IGNORECASE)


def _normalize_line(raw_line: str) -> str:
    return " ".join(raw_line.split())


def _section_scope(line: str, current: ObservationScope) -> ObservationScope:
    """Track major vendor-document address spaces using explicit section headings."""

    if _TABLE_ROW_RE.match(line):
        return current

    lowered = line.casefold().strip(" :-\t")
    if not lowered or len(lowered) > 96:
        return current

    if lowered == "ram" or lowered.startswith("ram registers"):
        return "runtime"
    if lowered == "eeprom" or lowered.startswith("eeprom "):
        return "configuration"
    if lowered in {"logged data", "logger"} or lowered.startswith("logged data "):
        return "log"
    if lowered in {"coil", "coils"} or lowered.startswith("coil address"):
        return "control"
    if lowered.startswith("discrete input"):
        return "control"
    if lowered in {"example", "examples"} or lowered.startswith("examples "):
        return "example"
    return current


def _row_scope(
    *,
    section_scope: ObservationScope,
    address: int,
    label: str,
    line: str,
) -> ObservationScope:
    lowered = line.casefold()

    if label.casefold() == "reserved":
        return "reserved"
    if 0x8000 <= address <= 0x8FFF:
        return "log"
    if address >= 0xE000:
        return "configuration"
    if "float32" in lowered and _FLOAT32_PART_RE.search(label):
        return "alternate_encoding"
    if (
        section_scope == "control"
        or "set only" in lowered
        or "write only" in lowered
        or "write-only" in lowered
        or _CONTROL_LABEL_RE.search(label)
    ):
        return "control"
    return section_scope


def _confidence_for_table_label(label: str) -> float:
    # A label in an anchored vendor table row is strong evidence even when it is camel-case
    # rather than underscore-separated. Keep a small distinction for machine-like identifiers.
    if "_" in label or "[" in label or any(character.isdigit() for character in label):
        return 0.95
    return 0.85


def parse_register_observations(
    source_id: str,
    pages: tuple[str, ...],
) -> tuple[RegisterObservation, ...]:
    """Extract canonical table rows without treating every hexadecimal mention as a register."""

    observations: dict[tuple[str, int, str], RegisterObservation] = {}
    section_scope: ObservationScope = "runtime"

    for page_number, text in enumerate(pages, start=1):
        for raw_line in text.splitlines():
            line = _normalize_line(raw_line)
            if not line:
                continue

            section_scope = _section_scope(line, section_scope)
            match = _TABLE_ROW_RE.match(line)
            if match is None:
                continue

            label = match.group("label")
            if label.casefold() in _WEAK_LABELS:
                continue

            address = int(match.group("address"), 16)
            scope = _row_scope(
                section_scope=section_scope,
                address=address,
                label=label,
                line=line,
            )
            observation = RegisterObservation(
                source_id=source_id,
                address=address,
                label=label,
                page=page_number,
                source_text=line[:300],
                confidence=_confidence_for_table_label(label),
                scope=scope,
            )
            key = (scope, address, label.casefold())
            existing = observations.get(key)
            if existing is None or observation.confidence > existing.confidence:
                observations[key] = observation

    return tuple(
        sorted(
            observations.values(),
            key=lambda item: (
                item.address,
                item.scope,
                -item.confidence,
                item.label.casefold(),
            ),
        )
    )
