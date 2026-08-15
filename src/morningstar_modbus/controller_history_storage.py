"""SQLite storage for provenance-aware controller-retained daily history."""

from __future__ import annotations

import json

import aiosqlite

from morningstar_modbus.controller_history_types import LIVEVIEW_SOURCE, ControllerDailyRecord

_HISTORY_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS controller_daily_history (
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    controller_day TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    source TEXT NOT NULL,
    source_path TEXT NOT NULL,
    day_offset INTEGER NOT NULL,
    is_complete INTEGER NOT NULL,
    day_start_utc TEXT NOT NULL,
    day_end_utc TEXT NOT NULL,
    live_sample_count INTEGER NOT NULL DEFAULT 0,
    hourmeter_hours REAL,
    event_count INTEGER,
    battery_voltage_min REAL,
    battery_voltage_max REAL,
    array_voltage_max REAL,
    output_power_max REAL,
    charge_ah REAL,
    charge_wh REAL,
    battery_temp_min REAL,
    battery_temp_max REAL,
    absorption_minutes REAL,
    float_minutes REAL,
    equalize_minutes REAL,
    faults TEXT,
    alarms TEXT,
    raw_json TEXT NOT NULL,
    PRIMARY KEY(device_id, controller_day)
);
CREATE INDEX IF NOT EXISTS idx_controller_daily_history_device_day
    ON controller_daily_history(device_id, controller_day DESC);
CREATE TABLE IF NOT EXISTS controller_history_syncs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    attempted_at TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_written INTEGER NOT NULL DEFAULT 0,
    oldest_day TEXT,
    newest_day TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_controller_history_syncs_device_time
    ON controller_history_syncs(device_id, attempted_at DESC);
"""


class ControllerHistoryRepository:
    """Persist daily controller history separately from immutable raw poll samples."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_HISTORY_SCHEMA)
            await db.commit()

    async def upsert(self, device_id: str, records: list[ControllerDailyRecord]) -> int:
        if not records:
            return 0
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            live_counts = await self._live_sample_counts(db, device_id, records)
            await db.executemany(
                """
                INSERT INTO controller_daily_history (
                    device_id, controller_day, retrieved_at, source, source_path, day_offset,
                    is_complete, day_start_utc, day_end_utc, live_sample_count,
                    hourmeter_hours, event_count, battery_voltage_min, battery_voltage_max,
                    array_voltage_max, output_power_max, charge_ah, charge_wh,
                    battery_temp_min, battery_temp_max, absorption_minutes, float_minutes,
                    equalize_minutes, faults, alarms, raw_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(device_id, controller_day) DO UPDATE SET
                    retrieved_at=excluded.retrieved_at,
                    source=excluded.source,
                    source_path=excluded.source_path,
                    day_offset=excluded.day_offset,
                    is_complete=excluded.is_complete,
                    day_start_utc=excluded.day_start_utc,
                    day_end_utc=excluded.day_end_utc,
                    live_sample_count=excluded.live_sample_count,
                    hourmeter_hours=excluded.hourmeter_hours,
                    event_count=excluded.event_count,
                    battery_voltage_min=excluded.battery_voltage_min,
                    battery_voltage_max=excluded.battery_voltage_max,
                    array_voltage_max=excluded.array_voltage_max,
                    output_power_max=excluded.output_power_max,
                    charge_ah=excluded.charge_ah,
                    charge_wh=excluded.charge_wh,
                    battery_temp_min=excluded.battery_temp_min,
                    battery_temp_max=excluded.battery_temp_max,
                    absorption_minutes=excluded.absorption_minutes,
                    float_minutes=excluded.float_minutes,
                    equalize_minutes=excluded.equalize_minutes,
                    faults=excluded.faults,
                    alarms=excluded.alarms,
                    raw_json=excluded.raw_json
                """,
                [self._record_row(device_id, record, live_counts) for record in records],
            )
            await db.commit()
        return len(records)

    @staticmethod
    def _record_row(
        device_id: str,
        record: ControllerDailyRecord,
        live_counts: dict[str, int],
    ) -> tuple[object, ...]:
        return (
            device_id,
            record.controller_day.isoformat(),
            record.retrieved_at,
            record.source,
            record.source_path,
            record.day_offset,
            int(record.is_complete),
            record.day_start_utc,
            record.day_end_utc,
            live_counts.get(record.controller_day.isoformat(), 0),
            record.hourmeter_hours,
            record.event_count,
            record.battery_voltage_min,
            record.battery_voltage_max,
            record.array_voltage_max,
            record.output_power_max,
            record.charge_ah,
            record.charge_wh,
            record.battery_temp_min,
            record.battery_temp_max,
            record.absorption_minutes,
            record.float_minutes,
            record.equalize_minutes,
            record.faults,
            record.alarms,
            json.dumps(record.raw or {}, separators=(",", ":"), sort_keys=True),
        )

    @staticmethod
    async def _live_sample_counts(
        db: aiosqlite.Connection,
        device_id: str,
        records: list[ControllerDailyRecord],
    ) -> dict[str, int]:
        values = ",".join("(?, ?, ?)" for _ in records)
        params: list[object] = []
        for record in records:
            params.extend((record.controller_day.isoformat(), record.day_start_utc, record.day_end_utc))
        cursor = await db.execute(
            f"""
            WITH day_ranges(controller_day, day_start_utc, day_end_utc) AS (VALUES {values})
            SELECT d.controller_day, COUNT(p.id)
            FROM day_ranges d
            LEFT JOIN poll_samples p
              ON p.device_id=?
             AND p.observed_at>=d.day_start_utc
             AND p.observed_at<d.day_end_utc
            GROUP BY d.controller_day
            """,
            (*params, device_id),
        )
        rows = await cursor.fetchall()
        return {str(day): int(count) for day, count in rows}

    async def record_sync(
        self,
        device_id: str,
        *,
        attempted_at: str,
        status: str,
        records_seen: int,
        records_written: int,
        oldest_day: str | None,
        newest_day: str | None,
        error: str | None = None,
    ) -> None:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO controller_history_syncs (
                    device_id, attempted_at, source, status, records_seen, records_written,
                    oldest_day, newest_day, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    attempted_at,
                    LIVEVIEW_SOURCE,
                    status,
                    records_seen,
                    records_written,
                    oldest_day,
                    newest_day,
                    error[:1000] if error else None,
                ),
            )
            await db.commit()

    async def list(
        self,
        device_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        await self.initialize()
        clauses = ["device_id=?"]
        params: list[object] = [device_id]
        if start is not None:
            clauses.append("controller_day>=?")
            params.append(start)
        if end is not None:
            clauses.append("controller_day<?")
            params.append(end)
        params.append(max(1, min(limit, 500)))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM controller_daily_history
                WHERE {' AND '.join(clauses)}
                ORDER BY controller_day DESC
                LIMIT ?
                """,
                tuple(params),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            row["is_complete"] = bool(row["is_complete"])
            row["fills_full_day_gap"] = (
                bool(row["is_complete"]) and int(row["live_sample_count"]) == 0
            )
            row["raw"] = json.loads(str(row.pop("raw_json")))
        return rows

    async def summary(self, device_id: str) -> dict[str, object]:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT COUNT(*) AS record_count,
                       COALESCE(SUM(CASE WHEN is_complete=1 THEN 1 ELSE 0 END), 0) AS complete_days,
                       COALESCE(
                           SUM(CASE WHEN is_complete=1 AND live_sample_count=0 THEN 1 ELSE 0 END),
                           0
                       ) AS full_day_gaps_filled,
                       MIN(controller_day) AS oldest_day,
                       MAX(controller_day) AS newest_day,
                       MAX(retrieved_at) AS last_retrieved_at
                FROM controller_daily_history
                WHERE device_id=?
                """,
                (device_id,),
            )
            summary_row = dict(await cursor.fetchone())
            sync_cursor = await db.execute(
                """
                SELECT attempted_at, status, records_seen, records_written, error
                FROM controller_history_syncs
                WHERE device_id=?
                ORDER BY attempted_at DESC, id DESC
                LIMIT 1
                """,
                (device_id,),
            )
            sync_row = await sync_cursor.fetchone()
        return {
            "device_id": device_id,
            **summary_row,
            "last_sync": dict(sync_row) if sync_row is not None else None,
        }
