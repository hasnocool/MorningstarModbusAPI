# src/morningstar_modbus/intelligence/validation.py
"""Read-only plausibility checks used to validate selected catalog profiles."""

from __future__ import annotations

import math

from morningstar_modbus.catalog.types import DeviceProfileSpec
from morningstar_modbus.domain.models import RegisterValue
from morningstar_modbus.intelligence.models import IntelligenceEvidence, ValidationIssue


def validate_values(
    spec: DeviceProfileSpec,
    values: tuple[RegisterValue, ...],
) -> tuple[tuple[IntelligenceEvidence, ...], tuple[ValidationIssue, ...]]:
    evidence: list[IntelligenceEvidence] = []
    issues: list[ValidationIssue] = []
    named = [value for value in values if not value.name.startswith(("holding_0x", "input_0x"))]
    if named:
        evidence.append(IntelligenceEvidence("named-registers", "named catalog registers decoded", 0.08))

    invalid = 0
    for value in named:
        decoded = value.value
        if isinstance(decoded, float) and not math.isfinite(decoded):
            invalid += 1
            issues.append(
                ValidationIssue(
                    "non-finite",
                    f"{value.name} decoded to a non-finite value",
                    "error",
                )
            )
            continue
        if not isinstance(decoded, (int, float)) or isinstance(decoded, bool):
            continue
        if value.unit == "V" and not -1.0 <= float(decoded) <= 1000.0:
            invalid += 1
        elif value.unit == "A" and not -1000.0 <= float(decoded) <= 1000.0:
            invalid += 1
        elif value.unit == "C" and not -80.0 <= float(decoded) <= 180.0:
            invalid += 1
        elif value.unit == "%" and not -1.0 <= float(decoded) <= 101.0:
            invalid += 1
        elif value.unit == "Hz" and not 0.0 <= float(decoded) <= 1000.0:
            invalid += 1
        if invalid and (not issues or issues[-1].code != "implausible-value"):
            issues.append(
                ValidationIssue(
                    "implausible-value",
                    f"{value.name} is outside a broad physical plausibility envelope",
                    "error",
                )
            )

    if invalid:
        evidence.append(
            IntelligenceEvidence(
                "telemetry-plausibility",
                f"{invalid} decoded value(s) failed plausibility checks",
                0.30,
                passed=False,
            )
        )
    elif named:
        evidence.append(IntelligenceEvidence("telemetry-plausibility", "decoded values are plausible", 0.12))
    return tuple(evidence), tuple(issues)
