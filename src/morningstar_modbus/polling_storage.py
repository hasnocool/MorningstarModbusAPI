"""SQLite persistence for Modbus polling performance telemetry."""

from __future__ import annotations

from typing import Any

import aiosqlite

from morningstar_modbus.polling import PollPerformanceSample, summarize_performance

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS poll_performance_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    sample_id INTEGER REFERENCES poll_samples(id) ON DELETE SET NULL,
    observed_at TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'watch',
    transport TEXT NOT NULL,
    configured_interval_seconds REAL NOT NULL,
    poll_latency_ms REAL NOT NULL,
    request_count INTEGER NOT NULL,
    successful_requests INTEGER NOT NULL,
    failed_requests INTEGER NOT NULL,
    request_bytes INTEGER NOT NULL,
    response_bytes INTEGER NOT NULL,
    estimated_wire_time_ms REAL,
    bus_utilization_percent REAL,
    deadline_missed INTEGER NOT NULL,
    success INTEGER NOT NULL,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_poll_performance_device_time
    ON poll_performance_samples(device_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_poll_performance_device_mode_time
    ON poll_performance_samples(device_id, mode, observed_at DESC);
"""


class PollingPerformanceStore:
    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def save(
        self,
        device_id: str,
        performance: PollPerformanceSample,
        *,
        sample_id: int | None = None,
        mode: str = "watch",
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO poll_performance_samples(
                    device_id, sample_id, observed_at, mode, transport,
                    configured_interval_seconds, poll_latency_ms,
                    request_count, successful_requests, failed_requests,
                    request_bytes, response_bytes, estimated_wire_time_ms,
                    bus_utilization_percent, deadline_missed, success, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    sample_id,
                    performance.observed_at,
                    mode,
                    performance.transport,
                    performance.configured_interval_seconds,
                    performance.poll_latency_ms,
                    performance.request_count,
                    performance.successful_requests,
                    performance.failed_requests,
                    performance.request_bytes,
                    performance.response_bytes,
                    performance.estimated_wire_time_ms,
                    performance.bus_utilization_percent,
                    int(performance.deadline_missed),
                    int(performance.success),
                    performance.error,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def recent(
        self,
        device_id: str,
        *,
        limit: int = 300,
        mode: str | None = "watch",
    ) -> list[dict[str, Any]]:
        clauses = ["device_id=?"]
        params: list[object] = [device_id]
        if mode is not None:
            clauses.append("mode=?")
            params.append(mode)
        params.append(max(1, min(limit, 5000)))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM poll_performance_samples
                WHERE {' AND '.join(clauses)}
                ORDER BY observed_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            row["deadline_missed"] = bool(row["deadline_missed"])
            row["success"] = bool(row["success"])
            row["total_bytes"] = int(row["request_bytes"]) + int(row["response_bytes"])
        return rows

    async def summary(
        self,
        device_id: str,
        *,
        window: int = 300,
        mode: str | None = "watch",
    ) -> dict[str, Any]:
        rows = await self.recent(device_id, limit=window, mode=mode)
        samples = [
            PollPerformanceSample(
                observed_at=str(row["observed_at"]),
                transport=str(row["transport"]),
                configured_interval_seconds=float(row["configured_interval_seconds"]),
                poll_latency_ms=float(row["poll_latency_ms"]),
                request_count=int(row["request_count"]),
                successful_requests=int(row["successful_requests"]),
                failed_requests=int(row["failed_requests"]),
                request_bytes=int(row["request_bytes"]),
                response_bytes=int(row["response_bytes"]),
                estimated_wire_time_ms=(
                    float(row["estimated_wire_time_ms"])
                    if row["estimated_wire_time_ms"] is not None
                    else None
                ),
                bus_utilization_percent=(
                    float(row["bus_utilization_percent"])
                    if row["bus_utilization_percent"] is not None
                    else None
                ),
                deadline_missed=bool(row["deadline_missed"]),
                success=bool(row["success"]),
                error=str(row["error"]),
            )
            for row in reversed(rows)
        ]
        summary = summarize_performance(samples)
        summary.update(
            {
                "device_id": device_id,
                "mode": mode or "all",
                "window": window,
                "configured_interval_seconds": (
                    samples[-1].configured_interval_seconds if samples else None
                ),
                "transport": samples[-1].transport if samples else None,
            }
        )
        return summary
