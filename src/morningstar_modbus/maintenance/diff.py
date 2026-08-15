# src/morningstar_modbus/maintenance/diff.py
"""Compare extracted source observations with checked-in family definitions."""

from __future__ import annotations

from collections import Counter

from morningstar_modbus.catalog.registry import PROFILES
from morningstar_modbus.maintenance.models import (
    CatalogComparison,
    ProposedChange,
    RegisterObservation,
)


def _registers_covering(profile: object, address: int) -> tuple[object, ...]:
    return tuple(
        register
        for register in profile.registers
        if register.address <= address < register.address + register.words
    )


def _blocks_covering(profile: object, address: int) -> tuple[object, ...]:
    return tuple(
        block
        for block in profile.blocks
        if block.address <= address < block.address + block.count
    )


def _change(
    *,
    profile: object,
    observation: RegisterObservation,
    change_type: str,
    declared_names: tuple[str, ...],
    confidence: float,
) -> ProposedChange:
    return ProposedChange(
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


def compare_observations(
    observations: tuple[RegisterObservation, ...],
) -> CatalogComparison:
    """Separate true conflicts from optional vendor-map coverage opportunities.

    A vendor label is not required to match the public API name. Existing multi-word register
    spans and raw read blocks count as declared coverage. Non-runtime spaces such as EEPROM,
    coils, logs, examples, and alternate encodings are excluded from runtime discrepancies.
    """

    profiles_by_source: dict[str, list[object]] = {}
    for profile in PROFILES:
        if profile.source_id:
            profiles_by_source.setdefault(profile.source_id, []).append(profile)

    actionable: dict[tuple[str, str, int, str], ProposedChange] = {}
    coverage: dict[tuple[str, str, int, str], ProposedChange] = {}
    ignored = Counter[str]()

    for observation in observations:
        profiles = profiles_by_source.get(observation.source_id, ())
        if not profiles:
            ignored["unmapped_source"] += 1
            continue

        for profile in profiles:
            registers = _registers_covering(profile, observation.address)
            declared_names = tuple(sorted({register.name for register in registers}))

            if observation.scope == "reserved":
                if registers:
                    change = _change(
                        profile=profile,
                        observation=observation,
                        change_type="declared_register_overlaps_reserved_vendor_row",
                        declared_names=declared_names,
                        confidence=0.95,
                    )
                    key = (
                        change.profile,
                        change.change_type,
                        change.address,
                        change.observed_label.casefold(),
                    )
                    actionable[key] = change
                else:
                    ignored["reserved"] += 1
                continue

            if observation.scope != "runtime":
                ignored[observation.scope] += 1
                continue

            if registers:
                # Vendor names such as VBTERM_F256 and semantic API names such as
                # battery_terminal_voltage are aliases for the same declared field.
                ignored["covered_named_register"] += 1
                continue

            blocks = _blocks_covering(profile, observation.address)
            if blocks:
                change_type = "unnamed_field_in_read_block"
                confidence = min(observation.confidence, 0.70)
            else:
                change_type = "runtime_address_outside_read_blocks"
                confidence = min(observation.confidence, 0.90)

            change = _change(
                profile=profile,
                observation=observation,
                change_type=change_type,
                declared_names=(),
                confidence=confidence,
            )
            key = (
                change.profile,
                change.change_type,
                change.address,
                change.observed_label.casefold(),
            )
            coverage[key] = change

    return CatalogComparison(
        actionable=tuple(
            sorted(
                actionable.values(),
                key=lambda item: (
                    item.profile,
                    item.address,
                    item.change_type,
                    item.observed_label.casefold(),
                ),
            )
        ),
        coverage_candidates=tuple(
            sorted(
                coverage.values(),
                key=lambda item: (
                    item.profile,
                    item.address,
                    item.change_type,
                    item.observed_label.casefold(),
                ),
            )
        ),
        ignored_counts=tuple(sorted(ignored.items())),
    )
