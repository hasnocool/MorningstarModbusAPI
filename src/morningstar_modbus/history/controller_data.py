"""Controller-scoped read model over authoritative device-owned telemetry tables."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite

from morningstar_modbus.controllers.scope import ControllerRegistry, ControllerScope
from morningstar_modbus.history import HistoryQueryTooLarge
from morningstar_modbus.polling import PollPerformanceSample, summarize_performance


def _order_sql(order: str) -> str:
    return "ASC" if order.lower() == "asc" else "DESC"


def _database_size(path: str) -> int:
    db_path = Path(path).expanduser()
    return db_path.stat().st_size if db_path.exists() else 0


class ControllerNotFoundError(LookupError):
    """Raised when a controller UID/alias cannot be resolved."""


class ControllerDataRepository:
    """Query one physical controller across all historical device IDs.

    Raw rows stay in their original device-owned tables. This repository only
    resolves a physical controller to ``controller_device_members`` and applies
    that scope to reads, preserving ``source_device_id`` on raw observations.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.registry = ControllerRegistry(path)

    async def initialize(self) -> None:
        await self.registry.initialize()

    async def scope(self, identifier: str) -> ControllerScope:
        scope = await self.registry.resolve(identifier)
        if scope is None:
            raise ControllerNotFoundError(identifier)
        return scope

    async def list_controllers(self) -> list[dict[str, object]]:
        return await self.registry.list_controllers()

    async def controller(self, identifier: str) -> dict[str, object] | None:
        return await self.registry.get_controller(identifier)

    @staticmethod
    def _ids_clause(scope: ControllerScope, column: str) -> tuple[str, tuple[object, ...]]:
        ids = scope.history_device_ids
        placeholders = ",".join("?" for _ in ids)
        return f"{column} IN ({placeholders})", tuple(ids)

    @classmethod
    def _sample_filter(
        cls,
        scope: ControllerScope,
        *,
        start: str | None,
        end: str | None,
        alias: str = "s",
    ) -> tuple[str, tuple[object, ...]]:
        ids_clause, ids_params = cls._ids_clause(scope, f"{alias}.device_id")
        clauses = [ids_clause]
        params: list[object] = list(ids_params)
        if start is not None:
            clauses.append(f"{alias}.observed_at>=?")
            params.append(start)
        if end is not None:
            clauses.append(f"{alias}.observed_at<?")
            params.append(end)
        return " AND ".join(clauses), tuple(params)

    @classmethod
    def _history_filter(
        cls,
        scope: ControllerScope,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
    ) -> tuple[str, tuple[object, ...]]:
        sample_where, sample_params = cls._sample_filter(scope, start=start, end=end, alias="s")
        clauses = [sample_where]
        params: list[object] = list(sample_params)
        if names:
            placeholders = ",".join("?" for _ in names)
            clauses.append(f"v.register_name IN ({placeholders})")
            params.extend(names)
        return " AND ".join(clauses), tuple(params)

    async def latest(self, identifier: str) -> dict[str, object] | None:
        scope = await self.scope(identifier)
        where, params = self._sample_filter(scope, start=None, end=None)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            sample_row = await (
                await db.execute(
                    f"""
                    SELECT * FROM poll_samples s
                    WHERE {where}
                    ORDER BY s.observed_at DESC, s.id DESC
                    LIMIT 1
                    """,
                    params,
                )
            ).fetchone()
            if sample_row is None:
                return None
            sample = dict(sample_row)
            values = [
                dict(row)
                for row in await (
                    await db.execute(
                        """
                        SELECT register_name, address, function, raw_json,
                               numeric_value, text_value, unit
                        FROM register_values
                        WHERE sample_id=?
                        ORDER BY address, register_name
                        """,
                        (sample["id"],),
                    )
                ).fetchall()
            ]
        for value in values:
            self._normalize_raw_value(value)
        source_device_id = str(sample.pop("device_id"))
        sample.update(scope.to_dict())
        sample["source_device_id"] = source_device_id
        sample["values"] = values
        return sample

    async def samples(
        self,
        identifier: str,
        *,
        limit: int = 100,
        start: str | None = None,
        end: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, object]]:
        scope = await self.scope(identifier)
        where, params = self._sample_filter(scope, start=start, end=end)
        direction = _order_sql(order)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = [
                dict(row)
                for row in await (
                    await db.execute(
                        f"""
                        SELECT s.* FROM poll_samples s
                        WHERE {where}
                        ORDER BY s.observed_at {direction}, s.id {direction}
                        LIMIT ?
                        """,
                        (*params, max(1, min(limit, 5000))),
                    )
                ).fetchall()
            ]
        for row in rows:
            row["source_device_id"] = row.pop("device_id")
            row["controller_uid"] = scope.controller_uid
        return rows

    async def register_history(
        self,
        identifier: str,
        name: str,
        *,
        limit: int = 1000,
        start: str | None = None,
        end: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, object]]:
        scope = await self.scope(identifier)
        rows = await self._raw_history_rows(
            scope,
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
        identifier: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        bucket_seconds: int | None,
        max_points: int,
    ) -> tuple[ControllerScope, list[dict[str, Any]]]:
        scope = await self.scope(identifier)
        limit = max_points + 1
        if bucket_seconds is None:
            rows = await self._raw_history_rows(
                scope,
                names,
                start=start,
                end=end,
                order=order,
                limit=limit,
            )
        else:
            sql, params = self._aggregated_history_sql(
                scope,
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
        return scope, rows

    async def _raw_history_rows(
        self,
        scope: ControllerScope,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        where, params = self._history_filter(scope, names, start=start, end=end)
        direction = _order_sql(order)
        rows = await self._query_all(
            f"""
            SELECT s.device_id AS source_device_id, s.observed_at, s.id AS sample_id,
                   v.register_name, v.address, v.function, v.raw_json,
                   v.numeric_value, v.text_value, v.unit
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
        scope: ControllerScope,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        bucket_seconds: int,
        limit: int | None,
    ) -> tuple[str, tuple[object, ...]]:
        where, params = self._history_filter(scope, names, start=start, end=end)
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
        identifier: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
    ) -> tuple[ControllerScope, list[dict[str, object]]]:
        scope = await self.scope(identifier)
        where, params = self._history_filter(scope, names, start=start, end=end)
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
            FROM ranked GROUP BY register_name ORDER BY register_name
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
                   SUM(CASE WHEN previous_text IS NOT NULL AND previous_text != text_value THEN 1 ELSE 0 END)
                       AS transitions,
                   MAX(epoch) - MIN(epoch) AS duration_seconds
            FROM ranked GROUP BY register_name ORDER BY register_name
            """,
            params,
        )
        states = await self._query_all(
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
        for row in states:
            state_counts.setdefault(str(row["register_name"]), {})[str(row["state"])] = int(row["count"])
        for row in text:
            row["state_counts"] = state_counts.get(str(row["register_name"]), {})
        rows = sorted([*numeric, *text], key=lambda row: (str(row["register_name"]), str(row["kind"])))
        return scope, rows

    async def history_summary(
        self,
        identifier: str,
        *,
        start: str | None,
        end: str | None,
    ) -> dict[str, object]:
        scope = await self.scope(identifier)
        sample_where, sample_params = self._sample_filter(scope, start=start, end=end, alias="s")
        history_where, history_params = self._history_filter(scope, (), start=start, end=end)
        error_ids, error_params = self._ids_clause(scope, "device_id")
        error_clauses = [error_ids]
        params: list[object] = list(error_params)
        if start is not None:
            error_clauses.append("observed_at>=?")
            params.append(start)
        if end is not None:
            error_clauses.append("observed_at<?")
            params.append(end)
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
        error_rows = await self._query_all(
            f"SELECT COUNT(*) AS error_count FROM poll_errors WHERE {' AND '.join(error_clauses)}",
            tuple(params),
        )
        return {
            **scope.to_dict(),
            "from": start,
            "to": end,
            **sample_rows[0],
            **register_rows[0],
            **error_rows[0],
            "database_bytes": await asyncio.to_thread(_database_size, self.path),
        }

    async def controller_daily_history(
        self,
        identifier: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        scope = await self.scope(identifier)
        ids_clause, ids_params = self._ids_clause(scope, "device_id")
        clauses = [ids_clause]
        params: list[object] = list(ids_params)
        if start is not None:
            clauses.append("controller_day>=?")
            params.append(start)
        if end is not None:
            clauses.append("controller_day<?")
            params.append(end)
        params.append(max(1, min(limit, 500)))
        rows = await self._query_all(
            f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY controller_day
                    ORDER BY retrieved_at DESC, device_id
                ) AS rn
                FROM controller_daily_history
                WHERE {' AND '.join(clauses)}
            )
            SELECT * FROM ranked
            WHERE rn=1
            ORDER BY controller_day DESC
            LIMIT ?
            """,
            tuple(params),
        )
        for row in rows:
            row.pop("rn", None)
            row["source_device_id"] = row.pop("device_id")
            row["controller_uid"] = scope.controller_uid
            row["is_complete"] = bool(row["is_complete"])
            row["fills_full_day_gap"] = bool(row["is_complete"]) and int(row["live_sample_count"]) == 0
            row["raw"] = json.loads(str(row.pop("raw_json")))
        return rows

    async def controller_daily_summary(self, identifier: str) -> dict[str, object]:
        scope = await self.scope(identifier)
        ids_clause, ids_params = self._ids_clause(scope, "device_id")
        summary = await self._query_all(
            f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY controller_day
                    ORDER BY retrieved_at DESC, device_id
                ) AS rn
                FROM controller_daily_history
                WHERE {ids_clause}
            )
            SELECT COUNT(*) AS record_count,
                   COALESCE(SUM(CASE WHEN is_complete=1 THEN 1 ELSE 0 END), 0) AS complete_days,
                   COALESCE(SUM(CASE WHEN is_complete=1 AND live_sample_count=0 THEN 1 ELSE 0 END), 0)
                       AS full_day_gaps_filled,
                   MIN(controller_day) AS oldest_day,
                   MAX(controller_day) AS newest_day,
                   MAX(retrieved_at) AS last_retrieved_at
            FROM ranked WHERE rn=1
            """,
            ids_params,
        )
        sync_ids, sync_params = self._ids_clause(scope, "device_id")
        sync_rows = await self._query_all(
            f"""
            SELECT device_id AS source_device_id, attempted_at, status,
                   records_seen, records_written, error
            FROM controller_history_syncs
            WHERE {sync_ids}
            ORDER BY attempted_at DESC, id DESC
            LIMIT 1
            """,
            sync_params,
        )
        return {
            **scope.to_dict(),
            **summary[0],
            "last_sync": sync_rows[0] if sync_rows else None,
        }

    async def polling_history(
        self,
        identifier: str,
        *,
        limit: int = 300,
        mode: str | None = "watch",
    ) -> list[dict[str, Any]]:
        scope = await self.scope(identifier)
        ids_clause, ids_params = self._ids_clause(scope, "device_id")
        clauses = [ids_clause]
        params: list[object] = list(ids_params)
        if mode is not None:
            clauses.append("mode=?")
            params.append(mode)
        params.append(max(1, min(limit, 5000)))
        rows = await self._query_all(
            f"""
            SELECT * FROM poll_performance_samples
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        )
        for row in rows:
            row["source_device_id"] = row.pop("device_id")
            row["controller_uid"] = scope.controller_uid
            row["deadline_missed"] = bool(row["deadline_missed"])
            row["success"] = bool(row["success"])
            row["total_bytes"] = int(row["request_bytes"]) + int(row["response_bytes"])
        return rows

    async def polling_summary(
        self,
        identifier: str,
        *,
        window: int = 300,
        mode: str | None = "watch",
    ) -> dict[str, Any]:
        scope = await self.scope(identifier)
        rows = await self.polling_history(identifier, limit=window, mode=mode)
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
                **scope.to_dict(),
                "mode": mode or "all",
                "window": window,
                "configured_interval_seconds": (
                    samples[-1].configured_interval_seconds if samples else None
                ),
                "transport": samples[-1].transport if samples else None,
            }
        )
        return summary

    async def iter_history_export(
        self,
        identifier: str,
        names: tuple[str, ...],
        *,
        start: str | None,
        end: str | None,
        order: str,
        bucket_seconds: int | None,
        batch_size: int = 500,
    ) -> AsyncIterator[dict[str, object]]:
        scope = await self.scope(identifier)
        if bucket_seconds is None:
            where, params = self._history_filter(scope, names, start=start, end=end)
            direction = _order_sql(order)
            sql = f"""
                SELECT s.device_id AS source_device_id, s.observed_at,
                       v.register_name, v.address, v.function, v.raw_json,
                       v.numeric_value, v.text_value, v.unit
                FROM register_values v
                JOIN poll_samples s ON s.id=v.sample_id
                WHERE {where}
                ORDER BY s.observed_at {direction}, s.id {direction}, v.register_name {direction}
            """
        else:
            sql, params = self._aggregated_history_sql(
                scope,
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
                    row["controller_uid"] = scope.controller_uid
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
            return [dict(row) for row in await cursor.fetchall()]
