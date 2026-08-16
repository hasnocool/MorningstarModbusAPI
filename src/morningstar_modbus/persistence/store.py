"""Async SQLite persistence and time-series query layer."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from morningstar_modbus.domain.models import DiscoveredDevice, PollResult
from morningstar_modbus.history import HistoryQueryTooLarge
from morningstar_modbus.intelligence.models import DeviceIntelligence

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
CREATE TABLE IF NOT EXISTS device_intelligence (
    device_id TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    family TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '',
    firmware TEXT NOT NULL DEFAULT '',
    hardware_revision TEXT NOT NULL DEFAULT '',
    catalog_revision TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL,
    intelligence_status TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    network_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS poll_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    profile TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_poll_samples_device_time
    ON poll_samples(device_id, observed_at DESC);
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
CREATE INDEX IF NOT EXISTS idx_register_values_name
    ON register_values(register_name, sample_id DESC);
CREATE TABLE IF NOT EXISTS poll_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    error TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_poll_errors_device_time
    ON poll_errors(device_id, observed_at DESC);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _order_sql(order: str) -> str:
    return "ASC" if order.lower() == "asc" else "DESC"


def _database_size(path: str) -> int:
    db_path = Path(path).expanduser()
    return db_path.stat().st_size if db_path.exists() else 0


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
        if device.intelligence is not None:
            await self.save_device_intelligence(device_id, device.intelligence)
        return device_id

    async def save_device_intelligence(
        self,
        device_id: str,
        intelligence: DeviceIntelligence,
    ) -> None:
        now = utcnow()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO device_intelligence (
                    device_id, profile, family, model, serial_number, firmware, hardware_revision,
                    catalog_revision, confidence, intelligence_status, capabilities_json, network_json,
                    evidence_json, warnings_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    profile=excluded.profile, family=excluded.family, model=excluded.model,
                    serial_number=excluded.serial_number, firmware=excluded.firmware,
                    hardware_revision=excluded.hardware_revision,
                    catalog_revision=excluded.catalog_revision, confidence=excluded.confidence,
                    intelligence_status=excluded.intelligence_status,
                    capabilities_json=excluded.capabilities_json, network_json=excluded.network_json,
                    evidence_json=excluded.evidence_json, warnings_json=excluded.warnings_json,
                    metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
                """,
                (
                    device_id,
                    intelligence.profile,
                    intelligence.family,
                    intelligence.model,
                    intelligence.serial_number,
                    intelligence.firmware,
                    intelligence.hardware_revision,
                    intelligence.catalog_revision,
                    intelligence.confidence,
                    intelligence.status,
                    json.dumps(list(intelligence.capabilities)),
                    json.dumps(dict(intelligence.network)),
                    json.dumps([item.to_dict() for item in intelligence.evidence]),
                    json.dumps([item.to_dict() for item in intelligence.warnings]),
                    json.dumps(dict(intelligence.metadata)),
                    now,
                ),
            )
            await db.commit()

    async def get_device_intelligence(self, device_id: str) -> dict[str, object] | None:
        rows = await self._query_all(
            "SELECT * FROM device_intelligence WHERE device_id=?",
            (device_id,),
        )
        if not rows:
            return None
        row = rows[0]
        row["capabilities"] = json.loads(str(row.pop("capabilities_json")))
        row["network"] = json.loads(str(row.pop("network_json")))
        row["evidence"] = json.loads(str(row.pop("evidence_json")))
        row["warnings"] = json.loads(str(row.pop("warnings_json")))
        row["metadata"] = json.loads(str(row.pop("metadata_json")))
        return row

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
            self._normalize_raw_value(value)
        sample["values"] = values
        return sample

    @staticmethod
    def _sample_filter(
        device_id: str,
        *,
        start: str | None,
        end: str | None,
        alias: str = "poll_samples",
    ) -> tuple[str, tuple[object, ...]]:
        clauses = [f"{alias}.device_id=?"]
        params: list[object] = [device_id]
        if start is not None:
            clauses.append(f"{alias}.observed_at>=?")
            params.append(start)
        if end is not None:
            clauses.append(f"{alias}.observed_at<?")
            params.append(end)
        return " AND ".join(clauses), tuple(params)

    @staticmethod
    def _history_filter(
        device_id: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
    ) -> tuple[str, tuple[object, ...]]:
        clauses = ["s.device_id=?"]
        params: list[object] = [device_id]
        if names:
            placeholders = ",".join("?" for _ in names)
            clauses.append(f"v.register_name IN ({placeholders})")
            params.extend(names)
        if start is not None:
            clauses.append("s.observed_at>=?")
            params.append(start)
        if end is not None:
            clauses.append("s.observed_at<?")
            params.append(end)
        return " AND ".join(clauses), tuple(params)

    async def samples(
        self,
        device_id: str,
        *,
        limit: int = 100,
        start: str | None = None,
        end: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, object]]:
        where, params = self._sample_filter(
            device_id,
            start=start,
            end=end,
            alias="poll_samples",
        )
        direction = _order_sql(order)
        return await self._query_all(
            f"""
            SELECT * FROM poll_samples
            WHERE {where}
            ORDER BY observed_at {direction}, id {direction}
            LIMIT ?
            """,
            (*params, max(1, min(limit, 5000))),
        )

    async def register_history(
        self,
        device_id: str,
        name: str,
        *,
        limit: int = 1000,
        start: str | None = None,
        end: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, object]]:
        rows = await self._raw_history_rows(
            device_id,
            (name,),
            start=start,
            end=end,
            order=order,
            limit=max(1, min(limit, 10000)),
        )
        for row in rows:
            row.pop("register_name", None)
            row.pop("sample_id", None)
            row.pop("kind", None)
        return rows

    async def multi_register_history(
        self,
        device_id: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        bucket_seconds: int | None,
        max_points: int,
    ) -> list[dict[str, Any]]:
        limit = max_points + 1
        if bucket_seconds is None:
            rows = await self._raw_history_rows(
                device_id,
                names,
                start=start,
                end=end,
                order=order,
                limit=limit,
            )
        else:
            sql, params = self._aggregated_history_sql(
                device_id,
                names,
                start=start,
                end=end,
                order=order,
                bucket_seconds=bucket_seconds,
                limit=limit,
            )
            rows = await self._query_all(sql, params)
        if len(rows) > max_points:
            raise HistoryQueryTooLarge(
                f"query exceeds {max_points} response points; narrow the time range, "
                "request fewer registers, or use a coarser resolution/export"
            )
        return rows

    async def _raw_history_rows(
        self,
        device_id: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        where, params = self._history_filter(device_id, names, start=start, end=end)
        direction = _order_sql(order)
        rows = await self._query_all(
            f"""
            SELECT s.observed_at, s.id AS sample_id, v.register_name, v.address, v.function,
                   v.raw_json, v.numeric_value, v.text_value, v.unit
            FROM register_values v
            JOIN poll_samples s ON s.id=v.sample_id
            WHERE {where}
            ORDER BY s.observed_at {direction}, s.id {direction}, v.register_name {direction}
            LIMIT ?
            """,
            (*params, limit),
        )
        for row in rows:
            self._normalize_raw_value(row)
        return rows

    def _aggregated_history_sql(
        self,
        device_id: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        bucket_seconds: int,
        limit: int | None,
    ) -> tuple[str, tuple[object, ...]]:
        where, params = self._history_filter(device_id, names, start=start, end=end)
        direction = _order_sql(order)
        sql = f"""
        WITH filtered AS (
            SELECT s.id AS sample_id, s.observed_at, v.register_name, v.address, v.function,
                   v.numeric_value, v.text_value, v.unit,
                   CAST(strftime('%s', s.observed_at) AS INTEGER) AS epoch
            FROM register_values v
            JOIN poll_samples s ON s.id=v.sample_id
            WHERE {where}
        ),
        bucketed AS (
            SELECT *, (epoch / ?) * ? AS bucket_epoch
            FROM filtered
        ),
        numeric_ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY register_name, bucket_epoch
                       ORDER BY observed_at, sample_id
                   ) AS rn_first,
                   ROW_NUMBER() OVER (
                       PARTITION BY register_name, bucket_epoch
                       ORDER BY observed_at DESC, sample_id DESC
                   ) AS rn_last
            FROM bucketed
            WHERE numeric_value IS NOT NULL
        ),
        text_with_previous AS (
            SELECT *,
                   LAG(text_value) OVER (
                       PARTITION BY register_name ORDER BY observed_at, sample_id
                   ) AS previous_text
            FROM bucketed
            WHERE text_value IS NOT NULL
        ),
        text_ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY register_name, bucket_epoch
                       ORDER BY observed_at, sample_id
                   ) AS rn_first,
                   ROW_NUMBER() OVER (
                       PARTITION BY register_name, bucket_epoch
                       ORDER BY observed_at DESC, sample_id DESC
                   ) AS rn_last
            FROM text_with_previous
        )
        SELECT register_name, MIN(address) AS address, MIN(function) AS function,
               MAX(unit) AS unit, 'numeric' AS kind,
               strftime('%Y-%m-%dT%H:%M:%SZ', bucket_epoch, 'unixepoch') AS bucket_start,
               COUNT(*) AS count, MIN(numeric_value) AS min_value,
               MAX(numeric_value) AS max_value, AVG(numeric_value) AS avg_value,
               MAX(CASE WHEN rn_first=1 THEN numeric_value END) AS first_value,
               MAX(CASE WHEN rn_last=1 THEN numeric_value END) AS last_value,
               NULL AS transitions
        FROM numeric_ranked
        GROUP BY register_name, bucket_epoch
        UNION ALL
        SELECT register_name, MIN(address) AS address, MIN(function) AS function,
               MAX(unit) AS unit, 'text' AS kind,
               strftime('%Y-%m-%dT%H:%M:%SZ', bucket_epoch, 'unixepoch') AS bucket_start,
               COUNT(*) AS count, NULL AS min_value, NULL AS max_value, NULL AS avg_value,
               MAX(CASE WHEN rn_first=1 THEN text_value END) AS first_value,
               MAX(CASE WHEN rn_last=1 THEN text_value END) AS last_value,
               SUM(CASE
                   WHEN previous_text IS NOT NULL AND previous_text != text_value THEN 1
                   ELSE 0
               END) AS transitions
        FROM text_ranked
        GROUP BY register_name, bucket_epoch
        ORDER BY bucket_start {direction}, register_name {direction}
        """
        query_params: tuple[object, ...] = (*params, bucket_seconds, bucket_seconds)
        if limit is not None:
            sql += " LIMIT ?"
            query_params = (*query_params, limit)
        return sql, query_params

    async def register_stats(
        self,
        device_id: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
    ) -> list[dict[str, object]]:
        where, params = self._history_filter(device_id, names, start=start, end=end)
        base = f"""
        SELECT s.id AS sample_id, s.observed_at, v.register_name, v.numeric_value,
               v.text_value, v.unit, CAST(strftime('%s', s.observed_at) AS INTEGER) AS epoch
        FROM register_values v
        JOIN poll_samples s ON s.id=v.sample_id
        WHERE {where}
        """
        numeric = await self._query_all(
            f"""
            WITH filtered AS ({base}),
            ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY register_name ORDER BY observed_at, sample_id
                       ) AS rn_first,
                       ROW_NUMBER() OVER (
                           PARTITION BY register_name ORDER BY observed_at DESC, sample_id DESC
                       ) AS rn_last,
                       ROW_NUMBER() OVER (
                           PARTITION BY register_name ORDER BY numeric_value, observed_at, sample_id
                       ) AS rn_min,
                       ROW_NUMBER() OVER (
                           PARTITION BY register_name ORDER BY numeric_value DESC, observed_at, sample_id
                       ) AS rn_max
                FROM filtered WHERE numeric_value IS NOT NULL
            )
            SELECT register_name, MAX(unit) AS unit, 'numeric' AS kind, COUNT(*) AS count,
                   MIN(numeric_value) AS min, MAX(numeric_value) AS max, AVG(numeric_value) AS avg,
                   MAX(CASE WHEN rn_first=1 THEN numeric_value END) AS first,
                   MAX(CASE WHEN rn_last=1 THEN numeric_value END) AS last,
                   MAX(CASE WHEN rn_first=1 THEN observed_at END) AS first_at,
                   MAX(CASE WHEN rn_last=1 THEN observed_at END) AS last_at,
                   MAX(CASE WHEN rn_min=1 THEN observed_at END) AS min_at,
                   MAX(CASE WHEN rn_max=1 THEN observed_at END) AS max_at,
                   MAX(epoch) - MIN(epoch) AS duration_seconds
            FROM ranked GROUP BY register_name
            ORDER BY register_name
            """,
            params,
        )
        for row in numeric:
            first = row.get("first")
            last = row.get("last")
            row["delta"] = (
                float(last) - float(first)
                if isinstance(first, (int, float)) and isinstance(last, (int, float))
                else None
            )

        text = await self._query_all(
            f"""
            WITH filtered AS ({base}),
            text_previous AS (
                SELECT *,
                       LAG(text_value) OVER (
                           PARTITION BY register_name ORDER BY observed_at, sample_id
                       ) AS previous_text
                FROM filtered WHERE text_value IS NOT NULL
            ),
            ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY register_name ORDER BY observed_at, sample_id
                       ) AS rn_first,
                       ROW_NUMBER() OVER (
                           PARTITION BY register_name ORDER BY observed_at DESC, sample_id DESC
                       ) AS rn_last
                FROM text_previous
            )
            SELECT register_name, MAX(unit) AS unit, 'text' AS kind, COUNT(*) AS count,
                   MAX(CASE WHEN rn_first=1 THEN text_value END) AS first,
                   MAX(CASE WHEN rn_last=1 THEN text_value END) AS last,
                   MAX(CASE WHEN rn_first=1 THEN observed_at END) AS first_at,
                   MAX(CASE WHEN rn_last=1 THEN observed_at END) AS last_at,
                   SUM(CASE
                       WHEN previous_text IS NOT NULL AND previous_text != text_value THEN 1
                       ELSE 0
                   END) AS transitions,
                   MAX(epoch) - MIN(epoch) AS duration_seconds
            FROM ranked GROUP BY register_name
            ORDER BY register_name
            """,
            params,
        )
        state_rows = await self._query_all(
            f"""
            WITH filtered AS ({base})
            SELECT register_name, text_value AS state, COUNT(*) AS count
            FROM filtered WHERE text_value IS NOT NULL
            GROUP BY register_name, text_value
            ORDER BY register_name, count DESC, text_value
            """,
            params,
        )
        state_counts: dict[str, dict[str, int]] = {}
        for row in state_rows:
            state_counts.setdefault(str(row["register_name"]), {})[str(row["state"])] = int(row["count"])
        for row in text:
            row["state_counts"] = state_counts.get(str(row["register_name"]), {})
        return sorted([*numeric, *text], key=lambda row: (str(row["register_name"]), str(row["kind"])))

    async def history_summary(
        self,
        device_id: str,
        *,
        start: str | None,
        end: str | None,
    ) -> dict[str, object]:
        sample_where, sample_params = self._sample_filter(
            device_id,
            start=start,
            end=end,
            alias="s",
        )
        sample_rows = await self._query_all(
            f"""
            SELECT MIN(s.observed_at) AS first_observation,
                   MAX(s.observed_at) AS last_observation,
                   COUNT(*) AS sample_count,
                   MIN(s.latency_ms) AS min_latency_ms,
                   MAX(s.latency_ms) AS max_latency_ms,
                   AVG(s.latency_ms) AS avg_latency_ms,
                   MAX(CAST(strftime('%s', s.observed_at) AS INTEGER))
                     - MIN(CAST(strftime('%s', s.observed_at) AS INTEGER)) AS observed_duration_seconds
            FROM poll_samples s WHERE {sample_where}
            """,
            sample_params,
        )
        history_where, history_params = self._history_filter(
            device_id,
            (),
            start=start,
            end=end,
        )
        register_rows = await self._query_all(
            f"""
            SELECT COUNT(*) AS register_observation_count,
                   COUNT(DISTINCT v.register_name) AS distinct_register_count
            FROM register_values v
            JOIN poll_samples s ON s.id=v.sample_id
            WHERE {history_where}
            """,
            history_params,
        )
        error_clauses = ["device_id=?"]
        error_params: list[object] = [device_id]
        if start is not None:
            error_clauses.append("observed_at>=?")
            error_params.append(start)
        if end is not None:
            error_clauses.append("observed_at<?")
            error_params.append(end)
        error_rows = await self._query_all(
            f"SELECT COUNT(*) AS error_count FROM poll_errors WHERE {' AND '.join(error_clauses)}",
            tuple(error_params),
        )
        database_bytes = await asyncio.to_thread(_database_size, self.path)
        return {
            "device_id": device_id,
            "from": start,
            "to": end,
            **sample_rows[0],
            **register_rows[0],
            **error_rows[0],
            "database_bytes": database_bytes,
        }

    async def iter_history_export(
        self,
        device_id: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        bucket_seconds: int | None,
        batch_size: int = 500,
    ) -> AsyncIterator[dict[str, object]]:
        if bucket_seconds is None:
            where, params = self._history_filter(device_id, names, start=start, end=end)
            direction = _order_sql(order)
            sql = f"""
                SELECT s.observed_at, v.register_name, v.address, v.function, v.raw_json,
                       v.numeric_value, v.text_value, v.unit
                FROM register_values v
                JOIN poll_samples s ON s.id=v.sample_id
                WHERE {where}
                ORDER BY s.observed_at {direction}, s.id {direction}, v.register_name {direction}
            """
        else:
            sql, params = self._aggregated_history_sql(
                device_id,
                names,
                start=start,
                end=end,
                order=order,
                bucket_seconds=bucket_seconds,
                limit=None,
            )

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            while True:
                batch = await cursor.fetchmany(batch_size)
                if not batch:
                    break
                for sqlite_row in batch:
                    row = dict(sqlite_row)
                    if bucket_seconds is None:
                        self._normalize_raw_value(row)
                    row["device_id"] = device_id
                    yield row

    @staticmethod
    def _normalize_raw_value(row: dict[str, Any]) -> None:
        row["raw"] = json.loads(str(row.pop("raw_json")))
        numeric = row.pop("numeric_value")
        text = row.pop("text_value")
        row["value"] = numeric if numeric is not None else text
        row["kind"] = "numeric" if numeric is not None else ("text" if text is not None else "null")

    async def _query_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
