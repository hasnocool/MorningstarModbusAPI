# src/morningstar_modbus/storage.py
"""Async SQLite persistence layer."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from morningstar_modbus.models import DiscoveredDevice, PollResult

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    transport TEXT NOT NULL,
    target TEXT NOT NULL,
    port INTEGER,
    unit_id INTEGER NOT NULL,
    usb_serial TEXT,
    usb_vid INTEGER,
    usb_pid INTEGER,
    vendor_name TEXT NOT NULL DEFAULT '',
    product_code TEXT NOT NULL DEFAULT '',
    revision TEXT NOT NULL DEFAULT '',
    profile TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS poll_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    profile TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_poll_samples_device_time ON poll_samples(device_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS register_values (
    sample_id INTEGER NOT NULL REFERENCES poll_samples(id) ON DELETE CASCADE,
    register_name TEXT NOT NULL,
    address INTEGER NOT NULL,
    function TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    numeric_value REAL,
    text_value TEXT,
    unit TEXT,
    PRIMARY KEY(sample_id, register_name)
);
CREATE INDEX IF NOT EXISTS idx_register_values_name ON register_values(register_name, sample_id DESC);
CREATE TABLE IF NOT EXISTS poll_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    error TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class TelemetryStore:
    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        parent = await asyncio.to_thread(lambda: Path(self.path).expanduser().resolve().parent)
        await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def upsert_device(self, device: DiscoveredDevice) -> str:
        endpoint = device.endpoint
        device_id = endpoint.stable_key
        now = utcnow()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO devices (
                    id, stable_key, transport, target, port, unit_id, usb_serial, usb_vid, usb_pid,
                    vendor_name, product_code, revision, profile, status, first_seen, last_seen, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'online', ?, ?, NULL)
                ON CONFLICT(stable_key) DO UPDATE SET
                    transport=excluded.transport, target=excluded.target, port=excluded.port,
                    unit_id=excluded.unit_id, usb_serial=excluded.usb_serial,
                    usb_vid=excluded.usb_vid, usb_pid=excluded.usb_pid,
                    vendor_name=excluded.vendor_name, product_code=excluded.product_code,
                    revision=excluded.revision, profile=excluded.profile,
                    status='online', last_seen=excluded.last_seen, last_error=NULL
                """,
                (
                    device_id,
                    endpoint.stable_key,
                    endpoint.transport,
                    endpoint.target,
                    endpoint.port,
                    endpoint.unit_id,
                    endpoint.usb_serial,
                    endpoint.usb_vid,
                    endpoint.usb_pid,
                    device.identification.vendor_name,
                    device.identification.product_code,
                    device.identification.major_minor_revision,
                    device.profile,
                    now,
                    now,
                ),
            )
            await db.commit()
        return device_id

    async def save_poll(self, device_id: str, result: PollResult) -> int:
        now = utcnow()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO poll_samples(device_id, observed_at, latency_ms, profile) VALUES (?, ?, ?, ?)",
                (device_id, now, result.latency_ms, result.profile),
            )
            sample_id = int(cursor.lastrowid or 0)
            rows = []
            for value in result.values:
                numeric: float | None = None
                text: str | None = None
                if isinstance(value.value, (int, float)) and not isinstance(value.value, bool):
                    numeric = float(value.value)
                elif value.value is not None:
                    text = str(value.value)
                rows.append(
                    (
                        sample_id,
                        value.name,
                        value.address,
                        value.function,
                        json.dumps(value.raw),
                        numeric,
                        text,
                        value.unit,
                    )
                )
            await db.executemany(
                """
                INSERT INTO register_values(
                    sample_id, register_name, address, function, raw_json, numeric_value, text_value, unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await db.execute(
                "UPDATE devices SET status='online', last_seen=?, last_error=NULL WHERE id=?",
                (now, device_id),
            )
            await db.commit()
            return sample_id

    async def save_error(self, device_id: str, error: str) -> None:
        now = utcnow()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO poll_errors(device_id, observed_at, error) VALUES (?, ?, ?)",
                (device_id, now, error),
            )
            await db.execute(
                "UPDATE devices SET status='error', last_error=? WHERE id=?",
                (error[:1000], device_id),
            )
            await db.commit()

    async def list_devices(self) -> list[dict[str, object]]:
        return await self._query_all("SELECT * FROM devices ORDER BY last_seen DESC")

    async def get_device(self, device_id: str) -> dict[str, object] | None:
        rows = await self._query_all("SELECT * FROM devices WHERE id=?", (device_id,))
        return rows[0] if rows else None

    async def latest(self, device_id: str) -> dict[str, object] | None:
        samples = await self._query_all(
            "SELECT * FROM poll_samples WHERE device_id=? ORDER BY observed_at DESC LIMIT 1",
            (device_id,),
        )
        if not samples:
            return None
        sample = samples[0]
        values = await self._query_all(
            """
            SELECT register_name, address, function, raw_json, numeric_value, text_value, unit
            FROM register_values WHERE sample_id=? ORDER BY address, register_name
            """,
            (sample["id"],),
        )
        for value in values:
            value["raw"] = json.loads(str(value.pop("raw_json")))
            value["value"] = value.pop("numeric_value")
            if value["value"] is None:
                value["value"] = value.pop("text_value")
            else:
                value.pop("text_value")
        sample["values"] = values
        return sample

    async def samples(self, device_id: str, *, limit: int = 100) -> list[dict[str, object]]:
        return await self._query_all(
            "SELECT * FROM poll_samples WHERE device_id=? ORDER BY observed_at DESC LIMIT ?",
            (device_id, max(1, min(limit, 5000))),
        )

    async def register_history(
        self,
        device_id: str,
        name: str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        rows = await self._query_all(
            """
            SELECT s.observed_at, v.address, v.function, v.raw_json,
                   v.numeric_value, v.text_value, v.unit
            FROM register_values v
            JOIN poll_samples s ON s.id=v.sample_id
            WHERE s.device_id=? AND v.register_name=?
            ORDER BY s.observed_at DESC LIMIT ?
            """,
            (device_id, name, max(1, min(limit, 10000))),
        )
        for row in rows:
            row["raw"] = json.loads(str(row.pop("raw_json")))
            numeric = row.pop("numeric_value")
            text = row.pop("text_value")
            row["value"] = numeric if numeric is not None else text
        return rows

    async def _query_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
