# src/morningstar_modbus/history/analytics.py
"""Controller-scoped history coverage, gap reconciliation, and energy accounting."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import aiosqlite

from morningstar_modbus.controllers.scope import ControllerScope
from morningstar_modbus.history.controller_data import ControllerDataRepository


def _percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 2)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _day_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days)]


class ControllerHistoryAnalytics:
    """Build truthful day-level continuity and energy views over one controller.

    Raw poll history and controller-retained daily logger rows stay separate. This
    layer joins them only at read time so a recovered daily record can improve
    continuity without ever pretending that missing high-frequency samples exist.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.data = ControllerDataRepository(path)

    @staticmethod
    def _ids_clause(scope: ControllerScope, column: str) -> tuple[str, tuple[object, ...]]:
        placeholders = ",".join("?" for _ in scope.history_device_ids)
        return f"{column} IN ({placeholders})", tuple(scope.history_device_ids)

    async def _query_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            return [dict(row) for row in await cursor.fetchall()]

    async def _resolve_period(
        self,
        scope: ControllerScope,
        start: str | None,
        end: str | None,
    ) -> tuple[date | None, date | None]:
        ids_clause, ids_params = self._ids_clause(scope, "device_id")
        bounds = await self._query_all(
            f"""
            SELECT MIN(day) AS first_day, MAX(day) AS last_day
            FROM (
                SELECT substr(observed_at, 1, 10) AS day
                FROM poll_samples
                WHERE {ids_clause}
                UNION ALL
                SELECT controller_day AS day
                FROM controller_daily_history
                WHERE {ids_clause}
            )
            """,
            (*ids_params, *ids_params),
        )
        first_available = bounds[0]["first_day"] if bounds else None
        last_available = bounds[0]["last_day"] if bounds else None

        start_day = date.fromisoformat(start) if start else (
            date.fromisoformat(str(first_available)) if first_available else None
        )
        end_day = date.fromisoformat(end) if end else (
            date.fromisoformat(str(last_available)) + timedelta(days=1) if last_available else None
        )

        if start_day is None and end_day is not None:
            start_day = end_day - timedelta(days=1)
        if end_day is None and start_day is not None:
            end_day = start_day + timedelta(days=1)
        if start_day is not None and end_day is not None and end_day <= start_day:
            raise ValueError("from must be earlier than to")
        return start_day, end_day

    async def _daily_evidence(
        self,
        scope: ControllerScope,
        start_day: date,
        end_day: date,
    ) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
        ids_clause, ids_params = self._ids_clause(scope, "device_id")
        start = start_day.isoformat()
        end = end_day.isoformat()
        live_rows = await self._query_all(
            f"""
            SELECT substr(observed_at, 1, 10) AS day, COUNT(*) AS sample_count
            FROM poll_samples
            WHERE {ids_clause}
              AND observed_at>=?
              AND observed_at<?
            GROUP BY substr(observed_at, 1, 10)
            """,
            (*ids_params, f"{start}T00:00:00+00:00", f"{end}T00:00:00+00:00"),
        )
        live = {str(row["day"]): int(row["sample_count"]) for row in live_rows}

        retained_rows = await self._query_all(
            f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY controller_day
                    ORDER BY retrieved_at DESC, device_id
                ) AS rn
                FROM controller_daily_history
                WHERE {ids_clause}
                  AND controller_day>=?
                  AND controller_day<?
            )
            SELECT * FROM ranked WHERE rn=1
            """,
            (*ids_params, start, end),
        )
        retained = {str(row["controller_day"]): row for row in retained_rows}
        return live, retained

    async def _last_sync(self, scope: ControllerScope) -> dict[str, Any] | None:
        ids_clause, ids_params = self._ids_clause(scope, "device_id")
        rows = await self._query_all(
            f"""
            SELECT device_id AS source_device_id, attempted_at, source, status,
                   records_seen, records_written, oldest_day, newest_day, error
            FROM controller_history_syncs
            WHERE {ids_clause}
            ORDER BY attempted_at DESC, id DESC
            LIMIT 1
            """,
            ids_params,
        )
        return rows[0] if rows else None

    async def coverage(
        self,
        identifier: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, object]:
        scope = await self.data.scope(identifier)
        start_day, end_day = await self._resolve_period(scope, start, end)
        if start_day is None or end_day is None:
            return {
                **scope.to_dict(),
                "period": {"from": start, "to": end, "day_count": 0},
                "realtime": {"days_with_samples": 0, "sample_count": 0, "coverage_percent": None},
                "daily_evidence": {
                    "covered_days": 0,
                    "coverage_percent": None,
                    "controller_completed_days": 0,
                    "recovered_days": 0,
                    "missing_days": 0,
                },
                "reconciliation": {"last_sync": await self._last_sync(scope)},
            }

        live, retained = await self._daily_evidence(scope, start_day, end_day)
        days = _day_range(start_day, end_day)
        realtime_days = sum(1 for day in days if live.get(day.isoformat(), 0) > 0)
        sample_count = sum(live.values())
        completed_controller_days = sum(
            1
            for day in days
            if (row := retained.get(day.isoformat())) is not None and bool(row["is_complete"])
        )
        recovered_days = sum(
            1
            for day in days
            if live.get(day.isoformat(), 0) == 0
            and (row := retained.get(day.isoformat())) is not None
            and bool(row["is_complete"])
        )
        covered_days = sum(
            1
            for day in days
            if live.get(day.isoformat(), 0) > 0
            or (
                (row := retained.get(day.isoformat())) is not None
                and bool(row["is_complete"])
            )
        )
        total_days = len(days)
        return {
            **scope.to_dict(),
            "period": {
                "from": start_day.isoformat(),
                "to": end_day.isoformat(),
                "day_count": total_days,
                "semantics": "inclusive start, exclusive end; coverage is day-level evidence coverage",
            },
            "realtime": {
                "days_with_samples": realtime_days,
                "sample_count": sample_count,
                "coverage_percent": _percent(realtime_days, total_days),
            },
            "daily_evidence": {
                "covered_days": covered_days,
                "coverage_percent": _percent(covered_days, total_days),
                "controller_completed_days": completed_controller_days,
                "recovered_days": recovered_days,
                "missing_days": total_days - covered_days,
            },
            "reconciliation": {
                "last_sync": await self._last_sync(scope),
                "controller_daily_records": len(retained),
            },
        }

    async def gaps(
        self,
        identifier: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, object]:
        scope = await self.data.scope(identifier)
        start_day, end_day = await self._resolve_period(scope, start, end)
        if start_day is None or end_day is None:
            return {**scope.to_dict(), "from": start, "to": end, "gaps": []}
        live, retained = await self._daily_evidence(scope, start_day, end_day)

        daily_gaps: list[tuple[date, str]] = []
        for day in _day_range(start_day, end_day):
            key = day.isoformat()
            if live.get(key, 0) > 0:
                continue
            record = retained.get(key)
            if record is not None and bool(record["is_complete"]):
                status = "recovered"
            elif record is not None:
                status = "partial"
            else:
                status = "missing"
            daily_gaps.append((day, status))

        grouped: list[dict[str, object]] = []
        for day, status in daily_gaps:
            if grouped:
                previous = grouped[-1]
                previous_end = date.fromisoformat(str(previous["to"]))
                if previous["status"] == status and previous_end == day:
                    previous["to"] = (day + timedelta(days=1)).isoformat()
                    previous["duration_days"] = int(previous["duration_days"]) + 1
                    previous["controller_record_count"] = int(previous["controller_record_count"]) + int(
                        status in {"recovered", "partial"}
                    )
                    continue
            grouped.append(
                {
                    "from": day.isoformat(),
                    "to": (day + timedelta(days=1)).isoformat(),
                    "duration_days": 1,
                    "status": status,
                    "recoverability": "controller_daily" if status in {"recovered", "partial"} else "none",
                    "controller_record_count": int(status in {"recovered", "partial"}),
                }
            )
        return {
            **scope.to_dict(),
            "from": start_day.isoformat(),
            "to": end_day.isoformat(),
            "semantics": "gaps are days with zero persisted poll_samples; recovered means a complete controller daily record exists",
            "gaps": grouped,
        }

    async def energy_daily(
        self,
        identifier: str,
        *,
        start: str | None = None,
        end: str | None = None,
        max_gap_seconds: int = 300,
    ) -> dict[str, object]:
        scope = await self.data.scope(identifier)
        start_day, end_day = await self._resolve_period(scope, start, end)
        if start_day is None or end_day is None:
            return {**scope.to_dict(), "from": start, "to": end, "days": []}
        if (end_day - start_day).days > 366:
            raise ValueError("energy daily range cannot exceed 366 days")

        live, retained = await self._daily_evidence(scope, start_day, end_day)
        ids_clause, ids_params = self._ids_clause(scope, "s.device_id")
        power_rows = await self._query_all(
            f"""
            SELECT s.observed_at, s.device_id AS source_device_id, v.numeric_value AS watts
            FROM register_values v
            JOIN poll_samples s ON s.id=v.sample_id
            WHERE {ids_clause}
              AND v.register_name='output_power'
              AND v.numeric_value IS NOT NULL
              AND s.observed_at>=?
              AND s.observed_at<?
            ORDER BY s.observed_at, s.id
            """,
            (
                *ids_params,
                f"{start_day.isoformat()}T00:00:00+00:00",
                f"{end_day.isoformat()}T00:00:00+00:00",
            ),
        )
        by_day: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for row in power_rows:
            observed = _parse_datetime(str(row["observed_at"]))
            by_day[observed.date().isoformat()].append((observed, float(row["watts"])))

        days: list[dict[str, object]] = []
        for day in _day_range(start_day, end_day):
            key = day.isoformat()
            samples = by_day.get(key, [])
            integrated_wh = 0.0
            integrated_seconds = 0.0
            skipped_seconds = 0.0
            for (left_at, left_w), (right_at, right_w) in zip(samples, samples[1:], strict=False):
                delta = (right_at - left_at).total_seconds()
                if delta <= 0:
                    continue
                if delta > max_gap_seconds:
                    skipped_seconds += delta
                    continue
                integrated_wh += ((left_w + right_w) / 2.0) * (delta / 3600.0)
                integrated_seconds += delta

            retained_row = retained.get(key)
            controller_wh = (
                float(retained_row["charge_wh"])
                if retained_row is not None and retained_row.get("charge_wh") is not None
                else None
            )
            local_wh = round(integrated_wh, 3) if len(samples) >= 2 else None
            difference_wh = (
                round(local_wh - controller_wh, 3)
                if local_wh is not None and controller_wh is not None
                else None
            )
            difference_percent = (
                round((difference_wh / controller_wh) * 100.0, 2)
                if difference_wh is not None and controller_wh not in {None, 0.0}
                else None
            )
            days.append(
                {
                    "date": key,
                    "energy": {
                        "controller_reported_wh": controller_wh,
                        "integrated_output_wh": local_wh,
                        "difference_wh": difference_wh,
                        "difference_percent": difference_percent,
                    },
                    "charge": {
                        "ah": retained_row.get("charge_ah") if retained_row else None,
                        "absorption_minutes": retained_row.get("absorption_minutes") if retained_row else None,
                        "float_minutes": retained_row.get("float_minutes") if retained_row else None,
                        "equalize_minutes": retained_row.get("equalize_minutes") if retained_row else None,
                    },
                    "battery": {
                        "min_v": retained_row.get("battery_voltage_min") if retained_row else None,
                        "max_v": retained_row.get("battery_voltage_max") if retained_row else None,
                    },
                    "pv": {
                        "max_v": retained_row.get("array_voltage_max") if retained_row else None,
                        "max_output_w": retained_row.get("output_power_max") if retained_row else None,
                    },
                    "events": {
                        "faults": retained_row.get("faults") if retained_row else None,
                        "alarms": retained_row.get("alarms") if retained_row else None,
                    },
                    "quality": {
                        "persisted_sample_count": live.get(key, 0),
                        "output_power_sample_count": len(samples),
                        "integrated_seconds": round(integrated_seconds, 3),
                        "skipped_between_samples_seconds": round(skipped_seconds, 3),
                        "max_gap_seconds": max_gap_seconds,
                        "controller_daily_record": retained_row is not None,
                        "controller_daily_complete": bool(retained_row["is_complete"]) if retained_row else False,
                        "provenance": [
                            source
                            for source, available in (
                                ("live_poll", bool(samples)),
                                ("controller_internal_logger", retained_row is not None),
                            )
                            if available
                        ],
                    },
                }
            )
        return {
            **scope.to_dict(),
            "from": start_day.isoformat(),
            "to": end_day.isoformat(),
            "days": days,
        }

    async def energy_summary(
        self,
        identifier: str,
        *,
        start: str | None = None,
        end: str | None = None,
        max_gap_seconds: int = 300,
    ) -> dict[str, object]:
        daily = await self.energy_daily(
            identifier,
            start=start,
            end=end,
            max_gap_seconds=max_gap_seconds,
        )
        rows = list(daily["days"])
        controller_values = [
            float(row["energy"]["controller_reported_wh"])
            for row in rows
            if row["energy"]["controller_reported_wh"] is not None
        ]
        integrated_values = [
            float(row["energy"]["integrated_output_wh"])
            for row in rows
            if row["energy"]["integrated_output_wh"] is not None
        ]
        controller_total = round(sum(controller_values), 3) if controller_values else None
        integrated_total = round(sum(integrated_values), 3) if integrated_values else None
        difference = (
            round(integrated_total - controller_total, 3)
            if integrated_total is not None and controller_total is not None
            else None
        )
        return {
            key: value for key, value in daily.items() if key != "days"
        } | {
            "energy": {
                "controller_reported_wh": controller_total,
                "integrated_output_wh": integrated_total,
                "difference_wh": difference,
                "difference_percent": (
                    round((difference / controller_total) * 100.0, 2)
                    if difference is not None and controller_total not in {None, 0.0}
                    else None
                ),
            },
            "quality": {
                "day_count": len(rows),
                "controller_reported_days": len(controller_values),
                "integrated_days": len(integrated_values),
                "max_gap_seconds": max_gap_seconds,
            },
        }
