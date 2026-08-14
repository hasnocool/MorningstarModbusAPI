# tools/catalog_maintenance/diff.py
"""Compare extracted source observations with checked-in family definitions."""

from __future__ import annotations

import re

from morningstar_modbus.catalog.registry import PROFILES
from tools.catalog_maintenance.models import ProposedChange, RegisterObservation

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize(value: str) -> str:
    return _NORMALIZE_RE.sub("", value.casefold())


def compare_observations(
    observations: tuple[RegisterObservation, ...],
) -> tuple[ProposedChange, ...]:
    profiles_by_source: dict[str, list[object]] = {}
    for profile in PROFILES:
        if profile.source_id:
            profiles_by_source.setdefault(profile.source_id, []).append(profile)

    proposed: dict[tuple[str, str, int, str], ProposedChange] = {}
    for observation in observations:
        for profile in profiles_by_source.get(observation.source_id, []):
            registers_at_address = tuple(
                register for register in profile.registers if register.address == observation.address
            )
            declared_names = tuple(sorted(register.name for register in registers_at_address))
            if not registers_at_address:
                change_type = "observed_address_not_declared"
                confidence = observation.confidence
            elif not observation.label:
                continue
            elif any(
                _normalize(observation.label) == _normalize(register.name)
                for register in registers_at_address
            ):
                continue
            else:
                change_type = "observed_label_differs"
                confidence = min(observation.confidence, 0.70)

            change = ProposedChange(
                profile=profile.name,
                source_id=observation.source_id,
                change_type=change_type,
                address=observation.address,
                observed_label=observation.label,
                declared_names=declared_names,
                confidence=confidence,
                page=observation.page,
                source_text=observation.source_text,
            )
            key = (
                change.profile,
                change.change_type,
                change.address,
                change.observed_label.casefold(),
            )
            proposed[key] = change

    return tuple(
        sorted(
            proposed.values(),
            key=lambda item: (
                item.profile,
                item.address,
                item.change_type,
                item.observed_label.casefold(),
            ),
        )
    )
