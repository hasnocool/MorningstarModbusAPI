# src/morningstar_modbus/intelligence/confidence.py
"""Confidence scoring for identity and profile validation evidence."""

from morningstar_modbus.intelligence.models import IntelligenceEvidence


def score(evidence: tuple[IntelligenceEvidence, ...]) -> float:
    positive = sum(item.weight for item in evidence if item.passed)
    negative = sum(abs(item.weight) for item in evidence if not item.passed)
    return max(0.0, min(1.0, positive - negative))
