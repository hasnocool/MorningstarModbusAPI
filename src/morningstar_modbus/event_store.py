# src/morningstar_modbus/event_store.py
"""Persistent read-only-observation event store used by system/site APIs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite

_EVENT_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS controller_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    controller_uid TEXT,
    observed_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_host TEXT,
    dedupe_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_controller_events_controller_time
    ON controller_events(controller_uid, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_controller_events_time
    ON controller_events(observed_at DESC);
"""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class EventStore:
    """Store internally observed events without adding any HTTP mutation surface."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_EVENT_SCHEMA)
            await db.commit()

    async def record(
        self,
        event_type: str,
        *,
        controller_uid: str | None = None,
        severity: str = "info",
        source: str = "runtime",
        message: str = "",
        payload: dict[str, Any] | None = None,
        source_host: str | None = None,
        observed_at: str | None = None,
        dedupe_key: str | None = None,
    ) -> int | None:
        await self.initialize()
        timestamp = observed_at or _utcnow()
        serialized = json.dumps(payload or {}, separators=(",", ":"), sort_keys=True)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO controller_events(
                    controller_uid, observed_at, event_type, severity, source,
                    message, payload_json, source_host, dedupe_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (
                    controller_uid,
                    timestamp,
                    event_type,
                    severity,
                    source,
                    message,
                    serialized,
                    source_host,
                    dedupe_key,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid) if cursor.rowcount else None

    async def recent(
        self,
        controller_uids: tuple[str, ...],
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 500,
        include_unassigned: bool = False,
    ) -> list[dict[str, object]]:
        await self.initialize()
        clauses: list[str] = []
        params: list[object] = []
        if controller_uids:
            placeholders = ",".join("?" for _ in controller_uids)
            if include_unassigned:
                clauses.append(f"(controller_uid IN ({placeholders}) OR controller_uid IS NULL)")
            else:
                clauses.append(f"controller_uid IN ({placeholders})")
            params.extend(controller_uids)
        elif not include_unassigned:
            return []
        if start is not None:
            clauses.append("observed_at>=?")
            params.append(start)
        if end is not None:
            clauses.append("observed_at<?")
            params.append(end)
        where = " AND ".join(clauses) if clauses else "1=1"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    f"""
                    SELECT id, controller_uid, observed_at, event_type, severity,
                           source, message, payload_json, source_host
                    FROM controller_events
                    WHERE {where}
                    ORDER BY observed_at DESC, id DESC
                    LIMIT ?
                    """,
                    (*params, max(1, min(limit, 5000))),
                )
            ).fetchall()
        output: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(str(item.pop("payload_json")))
            output.append(item)
        return output
