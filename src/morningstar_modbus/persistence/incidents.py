# src/morningstar_modbus/persistence/incidents.py
"""Persistent lifecycle store for evidence-backed site intelligence incidents."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

import aiosqlite

_INCIDENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS intelligence_incidents (
    incident_uid TEXT PRIMARY KEY,
    system_uid TEXT NOT NULL,
    controller_uid TEXT,
    detector TEXT NOT NULL,
    evaluation_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    state TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    observed_value REAL,
    expected_low REAL,
    expected_high REAL,
    unit TEXT,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    opened_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_intelligence_incidents_active_fingerprint
    ON intelligence_incidents(fingerprint)
    WHERE state='active';
CREATE INDEX IF NOT EXISTS idx_intelligence_incidents_system_state_time
    ON intelligence_incidents(system_uid, state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_incidents_controller_state_time
    ON intelligence_incidents(controller_uid, state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_incidents_evaluation
    ON intelligence_incidents(system_uid, evaluation_key, state);
"""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _incident_uid() -> str:
    return f"inc_{uuid.uuid4().hex[:16]}"


class IncidentStore:
    """Maintain incident state without exposing a mutation API to clients."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_INCIDENT_SCHEMA)
            await db.commit()

    @staticmethod
    def _decode(row: aiosqlite.Row | Mapping[str, Any]) -> dict[str, object]:
        item = dict(row)
        item["evidence"] = json.loads(str(item.pop("evidence_json") or "[]"))
        return item

    async def get(self, incident_uid: str) -> dict[str, object] | None:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT * FROM intelligence_incidents WHERE incident_uid=?",
                    (incident_uid,),
                )
            ).fetchone()
        return self._decode(row) if row is not None else None

    async def list(
        self,
        *,
        system_uid: str | None = None,
        controller_uid: str | None = None,
        state: str | None = None,
        severity: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, object]]:
        await self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        if system_uid is not None:
            clauses.append("system_uid=?")
            params.append(system_uid)
        if controller_uid is not None:
            clauses.append("controller_uid=?")
            params.append(controller_uid)
        if state is not None:
            clauses.append("state=?")
            params.append(state)
        if severity is not None:
            clauses.append("severity=?")
            params.append(severity)
        where = " AND ".join(clauses) if clauses else "1=1"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    f"""
                    SELECT * FROM intelligence_incidents
                    WHERE {where}
                    ORDER BY CASE state WHEN 'active' THEN 0 ELSE 1 END,
                             updated_at DESC, opened_at DESC
                    LIMIT ?
                    """,
                    (*params, max(1, min(limit, 5000))),
                )
            ).fetchall()
        return [self._decode(row) for row in rows]

    async def reconcile(
        self,
        system_uid: str,
        findings: Iterable[Mapping[str, object]],
        *,
        evaluated_keys: set[str],
        observed_at: str | None = None,
    ) -> list[dict[str, object]]:
        """Apply one scan and return only lifecycle transitions worth emitting as events."""
        await self.initialize()
        timestamp = observed_at or _utcnow()
        finding_list = list(findings)
        present = {str(item["fingerprint"]) for item in finding_list}
        transitions: list[dict[str, object]] = []

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            active_rows = await (
                await db.execute(
                    "SELECT * FROM intelligence_incidents WHERE system_uid=? AND state='active'",
                    (system_uid,),
                )
            ).fetchall()
            active = {str(row["fingerprint"]): row for row in active_rows}

            for finding in finding_list:
                fingerprint = str(finding["fingerprint"])
                evidence_json = json.dumps(
                    finding.get("evidence") or [], separators=(",", ":"), sort_keys=True
                )
                previous = active.get(fingerprint)
                if previous is None:
                    uid = _incident_uid()
                    await db.execute(
                        """
                        INSERT INTO intelligence_incidents(
                            incident_uid, system_uid, controller_uid, detector, evaluation_key,
                            fingerprint, category, severity, confidence, state, title, summary,
                            observed_value, expected_low, expected_high, unit, evidence_json,
                            opened_at, last_observed_at, updated_at, occurrence_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            uid,
                            system_uid,
                            finding.get("controller_uid"),
                            finding["detector"],
                            finding["evaluation_key"],
                            fingerprint,
                            finding["category"],
                            finding["severity"],
                            finding["confidence"],
                            finding["title"],
                            finding["summary"],
                            finding.get("observed_value"),
                            finding.get("expected_low"),
                            finding.get("expected_high"),
                            finding.get("unit"),
                            evidence_json,
                            timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )
                    inserted = await (
                        await db.execute(
                            "SELECT * FROM intelligence_incidents WHERE incident_uid=?", (uid,)
                        )
                    ).fetchone()
                    if inserted is not None:
                        transitions.append({"transition": "opened", **self._decode(inserted)})
                    continue

                changed = any(
                    str(previous[field] or "") != str(finding.get(field) or "")
                    for field in ("severity", "confidence", "title", "summary")
                )
                await db.execute(
                    """
                    UPDATE intelligence_incidents
                    SET category=?, severity=?, confidence=?, title=?, summary=?,
                        observed_value=?, expected_low=?, expected_high=?, unit=?, evidence_json=?,
                        last_observed_at=?, updated_at=?, occurrence_count=occurrence_count+1
                    WHERE incident_uid=?
                    """,
                    (
                        finding["category"],
                        finding["severity"],
                        finding["confidence"],
                        finding["title"],
                        finding["summary"],
                        finding.get("observed_value"),
                        finding.get("expected_low"),
                        finding.get("expected_high"),
                        finding.get("unit"),
                        evidence_json,
                        timestamp,
                        timestamp,
                        previous["incident_uid"],
                    ),
                )
                if changed:
                    updated = await (
                        await db.execute(
                            "SELECT * FROM intelligence_incidents WHERE incident_uid=?",
                            (previous["incident_uid"],),
                        )
                    ).fetchone()
                    if updated is not None:
                        transitions.append({"transition": "updated", **self._decode(updated)})

            for fingerprint, row in active.items():
                if fingerprint in present:
                    continue
                if str(row["evaluation_key"]) not in evaluated_keys:
                    continue
                await db.execute(
                    """
                    UPDATE intelligence_incidents
                    SET state='resolved', resolved_at=?, updated_at=?
                    WHERE incident_uid=? AND state='active'
                    """,
                    (timestamp, timestamp, row["incident_uid"]),
                )
                resolved = await (
                    await db.execute(
                        "SELECT * FROM intelligence_incidents WHERE incident_uid=?",
                        (row["incident_uid"],),
                    )
                ).fetchone()
                if resolved is not None:
                    transitions.append({"transition": "resolved", **self._decode(resolved)})
            await db.commit()
        return transitions
