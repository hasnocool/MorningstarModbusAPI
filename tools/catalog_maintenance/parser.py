# tools/catalog_maintenance/parser.py
"""Conservative extraction of register observations from vendor document text."""

from __future__ import annotations

import re

from tools.catalog_maintenance.models import RegisterObservation

_ADDRESS_RE = re.compile(r"\b0[xX]([0-9A-Fa-f]{4})\b")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]{2,}\b")
_STOPWORDS = {
    "address",
    "register",
    "registers",
    "modbus",
    "holding",
    "input",
    "read",
    "write",
    "description",
    "units",
    "unit",
    "value",
    "values",
    "default",
    "reserved",
}


def _label_from_line(line: str, address_match: re.Match[str]) -> tuple[str, float]:
    trailing = line[address_match.end() :].strip(" :-\t")
    identifiers = _IDENTIFIER_RE.findall(trailing)
    for identifier in identifiers:
        if "_" in identifier and identifier.casefold() not in _STOPWORDS:
            return identifier, 0.90
    for identifier in identifiers:
        if identifier.casefold() not in _STOPWORDS:
            return identifier, 0.60
    return "", 0.35


def parse_register_observations(
    source_id: str,
    pages: tuple[str, ...],
) -> tuple[RegisterObservation, ...]:
    observations: dict[tuple[int, str], RegisterObservation] = {}
    for page_number, text in enumerate(pages, start=1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            for address_match in _ADDRESS_RE.finditer(line):
                address = int(address_match.group(1), 16)
                label, confidence = _label_from_line(line, address_match)
                observation = RegisterObservation(
                    source_id=source_id,
                    address=address,
                    label=label,
                    page=page_number,
                    source_text=line[:300],
                    confidence=confidence,
                )
                key = (address, label.casefold())
                existing = observations.get(key)
                if existing is None or observation.confidence > existing.confidence:
                    observations[key] = observation
    return tuple(
        sorted(
            observations.values(),
            key=lambda item: (item.address, -item.confidence, item.label.casefold()),
        )
    )
