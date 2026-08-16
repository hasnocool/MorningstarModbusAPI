"""FastAPI routes for immutable physical-controller scoped data."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from morningstar_modbus.history import (
    MAX_JSON_POINTS,
    HistoryQueryError,
    HistoryQueryTooLarge,
    normalize_names,
    normalize_time_range,
    validate_order,
    validate_resolution,
)
from morningstar_modbus.history.controller_data import ControllerDataRepository, ControllerNotFoundError


def _history_error(exc: HistoryQueryError) -> HTTPException:
    return HTTPException(
        status_code=413 if isinstance(exc, HistoryQueryTooLarge) else 400,
        detail=str(exc),
    )


def _range_and_order(
    start: str | None,
    end: str | None,
    order: str,
) -> tuple[str | None, str | None, str]:
    try:
        normalized_start, normalized_end = normalize_time_range(start, end)
        normalized_order = validate_order(order)
    except HistoryQueryError as exc:
        raise _history_error(exc) from exc
    return normalized_start, normalized_end, normalized_order


def _daily_range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    try:
        normalized_start = date.fromisoformat(start).isoformat() if start else None
        normalized_end = date.fromisoformat(end).isoformat() if end else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="daily history dates must use YYYY-MM-DD") from exc
    if normalized_start is not None and normalized_end is not None and normalized_start >= normalized_end:
        raise HTTPException(status_code=400, detail="from must be earlier than to")
    return normalized_start, normalized_end


def _polling_mode(value: str) -> str | None:
    normalized = value.strip().lower()
    if normalized == "all":
        return None
    if normalized not in {"watch", "benchmark"}:
        raise HTTPException(status_code=400, detail="mode must be watch, benchmark, or all")
    return normalized


async def _controller_call(awaitable: Any) -> Any:
    try:
        return await awaitable
    except ControllerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="controller not found") from exc


def _build_history_response(
    *,
    scope: dict[str, object],
    start: str | None,
    end: str | None,
    resolution: str,
    rows: list[dict[str, Any]],
) -> dict[str, object]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row["register_name"])
        series = grouped.setdefault(
            name,
            {
                "name": name,
                "unit": row.get("unit"),
                "kind": row.get("kind", "unknown"),
                "points": [],
            },
        )
        kind = str(row.get("kind", "unknown"))
        if series["kind"] != kind:
            series["kind"] = "mixed"
        if series["unit"] is None and row.get("unit") is not None:
            series["unit"] = row["unit"]

        if resolution == "raw":
            point = {
                "observed_at": row["observed_at"],
                "source_device_id": row["source_device_id"],
                "address": row["address"],
                "function": row["function"],
                "raw": row["raw"],
                "value": row["value"],
            }
        elif kind == "numeric":
            point = {
                "bucket_start": row["bucket_start"],
                "count": row["count"],
                "min": row["min_value"],
                "max": row["max_value"],
                "avg": row["avg_value"],
                "first": row["first_value"],
                "last": row["last_value"],
            }
        else:
            point = {
                "bucket_start": row["bucket_start"],
                "samples": row["count"],
                "first": row["first_value"],
                "last": row["last_value"],
                "transitions": row["transitions"],
            }
        series["points"].append(point)

    return {
        **scope,
        "from": start,
        "to": end,
        "resolution": resolution,
        "series": list(grouped.values()),
    }


def attach_controller_routes(app: FastAPI, data: ControllerDataRepository) -> None:
    """Attach controller-first API routes while leaving legacy device routes intact."""

    @app.get("/v1/controllers/{controller_uid}/latest")
    async def controller_latest(controller_uid: str) -> dict[str, object]:
        record = await _controller_call(data.latest(controller_uid))
        if record is None:
            raise HTTPException(status_code=404, detail="no samples for controller")
        return record

    @app.get("/v1/controllers/{controller_uid}/samples")
    async def controller_samples(
        controller_uid: str,
        limit: int = Query(100, ge=1, le=5000),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        order: str = Query("desc"),
    ) -> list[dict[str, object]]:
        start, end, normalized_order = _range_and_order(from_, to, order)
        return await _controller_call(
            data.samples(
                controller_uid,
                limit=limit,
                start=start,
                end=end,
                order=normalized_order,
            )
        )

    @app.get("/v1/controllers/{controller_uid}/registers/{name}/history")
    async def controller_register_history(
        controller_uid: str,
        name: str,
        limit: int = Query(1000, ge=1, le=10000),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        order: str = Query("desc"),
    ) -> list[dict[str, object]]:
        start, end, normalized_order = _range_and_order(from_, to, order)
        return await _controller_call(
            data.register_history(
                controller_uid,
                name,
                limit=limit,
                start=start,
                end=end,
                order=normalized_order,
            )
        )

    @app.get("/v1/controllers/{controller_uid}/registers/history")
    async def controller_registers_history(
        controller_uid: str,
        name: Annotated[list[str], Query()],
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        resolution: str = Query("raw"),
        order: str = Query("asc"),
        max_points: int = Query(MAX_JSON_POINTS, ge=1, le=MAX_JSON_POINTS),
    ) -> dict[str, object]:
        start, end, normalized_order = _range_and_order(from_, to, order)
        try:
            names = normalize_names(name)
            normalized_resolution, bucket_seconds = validate_resolution(resolution)
            scope, rows = await data.multi_register_history(
                controller_uid,
                names,
                start=start,
                end=end,
                order=normalized_order,
                bucket_seconds=bucket_seconds,
                max_points=max_points,
            )
        except ControllerNotFoundError as exc:
            raise HTTPException(status_code=404, detail="controller not found") from exc
        except HistoryQueryError as exc:
            raise _history_error(exc) from exc
        return _build_history_response(
            scope=scope.to_dict(),
            start=start,
            end=end,
            resolution=normalized_resolution,
            rows=rows,
        )

    @app.get("/v1/controllers/{controller_uid}/registers/stats")
    async def controller_register_stats(
        controller_uid: str,
        name: Annotated[list[str], Query()],
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ) -> dict[str, object]:
        start, end, _ = _range_and_order(from_, to, "asc")
        try:
            names = normalize_names(name)
            scope, rows = await data.register_stats(
                controller_uid,
                names,
                start=start,
                end=end,
            )
        except ControllerNotFoundError as exc:
            raise HTTPException(status_code=404, detail="controller not found") from exc
        except HistoryQueryError as exc:
            raise _history_error(exc) from exc
        return {
            **scope.to_dict(),
            "from": start,
            "to": end,
            "registers": rows,
        }

    @app.get("/v1/controllers/{controller_uid}/history/summary")
    async def controller_history_summary(
        controller_uid: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ) -> dict[str, object]:
        start, end, _ = _range_and_order(from_, to, "asc")
        return await _controller_call(
            data.history_summary(controller_uid, start=start, end=end)
        )

    @app.get("/v1/controllers/{controller_uid}/history/controller-daily")
    async def controller_daily_history(
        controller_uid: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        limit: int = Query(200, ge=1, le=500),
    ) -> list[dict[str, object]]:
        start, end = _daily_range(from_, to)
        return await _controller_call(
            data.controller_daily_history(
                controller_uid,
                start=start,
                end=end,
                limit=limit,
            )
        )

    @app.get("/v1/controllers/{controller_uid}/history/controller-daily/summary")
    async def controller_daily_history_summary(controller_uid: str) -> dict[str, object]:
        return await _controller_call(data.controller_daily_summary(controller_uid))

    @app.get("/v1/controllers/{controller_uid}/history/export")
    async def controller_history_export(
        controller_uid: str,
        name: Annotated[list[str] | None, Query()] = None,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        resolution: str = Query("raw"),
        order: str = Query("asc"),
        format_: str = Query("csv", alias="format"),
    ) -> StreamingResponse:
        start, end, normalized_order = _range_and_order(from_, to, order)
        try:
            names = normalize_names(name) if name else ()
            normalized_resolution, bucket_seconds = validate_resolution(resolution)
            await data.scope(controller_uid)
        except ControllerNotFoundError as exc:
            raise HTTPException(status_code=404, detail="controller not found") from exc
        except HistoryQueryError as exc:
            raise _history_error(exc) from exc
        export_format = format_.strip().lower()
        if export_format not in {"csv", "jsonl"}:
            raise HTTPException(status_code=400, detail="format must be csv or jsonl")
        rows = data.iter_history_export(
            controller_uid,
            names,
            start=start,
            end=end,
            order=normalized_order,
            bucket_seconds=bucket_seconds,
        )
        if export_format == "jsonl":
            stream = _jsonl_stream(rows)
            media_type = "application/x-ndjson"
            suffix = "jsonl"
        else:
            stream = _csv_stream(rows, resolution=normalized_resolution)
            media_type = "text/csv"
            suffix = "csv"
        return StreamingResponse(
            stream,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="controller-history.{suffix}"'},
        )

    @app.get("/v1/controllers/{controller_uid}/polling/performance")
    async def controller_polling_performance(
        controller_uid: str,
        window: int = Query(300, ge=3, le=5000),
        mode: str = Query("watch"),
    ) -> dict[str, object]:
        return await _controller_call(
            data.polling_summary(
                controller_uid,
                window=window,
                mode=_polling_mode(mode),
            )
        )

    @app.get("/v1/controllers/{controller_uid}/polling/history")
    async def controller_polling_history(
        controller_uid: str,
        limit: int = Query(300, ge=1, le=5000),
        mode: str = Query("watch"),
    ) -> list[dict[str, object]]:
        return await _controller_call(
            data.polling_history(
                controller_uid,
                limit=limit,
                mode=_polling_mode(mode),
            )
        )

    @app.get("/v1/controllers/{controller_uid}")
    async def controller_detail(controller_uid: str) -> dict[str, object]:
        record = await data.controller(controller_uid)
        if record is None:
            raise HTTPException(status_code=404, detail="controller not found")
        return record


async def _jsonl_stream(rows: AsyncIterator[dict[str, object]]) -> AsyncIterator[str]:
    async for row in rows:
        yield json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"


async def _csv_stream(
    rows: AsyncIterator[dict[str, object]],
    *,
    resolution: str,
) -> AsyncIterator[str]:
    if resolution == "raw":
        fields = [
            "observed_at",
            "controller_uid",
            "source_device_id",
            "register_name",
            "address",
            "function",
            "raw",
            "value",
            "unit",
            "kind",
        ]
    else:
        fields = [
            "bucket_start",
            "controller_uid",
            "register_name",
            "address",
            "function",
            "unit",
            "kind",
            "count",
            "min_value",
            "max_value",
            "avg_value",
            "first_value",
            "last_value",
            "transitions",
        ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    async for row in rows:
        output = dict(row)
        if "raw" in output:
            output["raw"] = json.dumps(output["raw"], separators=(",", ":"))
        writer.writerow(output)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
