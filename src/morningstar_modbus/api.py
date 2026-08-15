"""FastAPI application exposing stored telemetry and Morningstar device intelligence."""

from __future__ import annotations

import csv
import io
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from morningstar_modbus import __version__
from morningstar_modbus.catalog import catalog_detail, catalog_summary
from morningstar_modbus.controller_history import ControllerHistoryRepository
from morningstar_modbus.history import (
    MAX_JSON_POINTS,
    HistoryQueryError,
    HistoryQueryTooLarge,
    build_history_response,
    normalize_names,
    normalize_time_range,
    validate_order,
    validate_resolution,
)
from morningstar_modbus.intelligence import effective_register_map
from morningstar_modbus.polling_storage import PollingPerformanceStore
from morningstar_modbus.storage import TelemetryStore

LOGGER = logging.getLogger(__name__)


def _history_error(exc: HistoryQueryError) -> HTTPException:
    status_code = 413 if isinstance(exc, HistoryQueryTooLarge) else 400
    return HTTPException(status_code=status_code, detail=str(exc))


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


def create_app(store: TelemetryStore) -> FastAPI:
    controller_history = ControllerHistoryRepository(store.path)
    performance_store = PollingPerformanceStore(store.path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.initialize()
        await controller_history.initialize()
        await performance_store.initialize()
        yield

    app = FastAPI(
        title="Morningstar Modbus API",
        version=__version__,
        description="Read-only API for persisted Morningstar Modbus telemetry and device intelligence.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/catalog")
    async def catalog() -> list[dict[str, object]]:
        return catalog_summary()

    @app.get("/v1/catalog/{profile_name}")
    async def catalog_profile(profile_name: str) -> dict[str, object]:
        profile = catalog_detail(profile_name)
        if profile is None:
            raise HTTPException(status_code=404, detail="catalog profile not found")
        return profile

    @app.get("/v1/devices")
    async def devices() -> list[dict[str, object]]:
        return await store.list_devices()

    @app.get("/v1/devices/latest")
    async def latest(device_id: str = Query(...)) -> dict[str, object]:
        LOGGER.info("looking up latest telemetry device=%r", device_id)
        record = await store.latest(device_id)
        if record is None:
            raise HTTPException(status_code=404, detail="no samples for device")
        return record

    @app.get("/v1/devices/intelligence")
    async def device_intelligence(device_id: str = Query(...)) -> dict[str, object]:
        record = await store.get_device_intelligence(device_id)
        if record is None:
            raise HTTPException(status_code=404, detail="device intelligence not found")
        return record

    @app.get("/v1/devices/register-map")
    async def device_register_map(device_id: str = Query(...)) -> dict[str, object]:
        intelligence = await store.get_device_intelligence(device_id)
        if intelligence is None:
            raise HTTPException(status_code=404, detail="device intelligence not found")
        register_map = effective_register_map(
            str(intelligence["profile"]),
            intelligence.get("firmware", ""),
        )
        if register_map is None:
            raise HTTPException(status_code=404, detail="catalog profile not found")
        return register_map

    @app.get("/v1/devices/profile/validation")
    async def device_profile_validation(device_id: str = Query(...)) -> dict[str, object]:
        intelligence = await store.get_device_intelligence(device_id)
        if intelligence is None:
            raise HTTPException(status_code=404, detail="device intelligence not found")
        return {
            "profile": intelligence["profile"],
            "confidence": intelligence["confidence"],
            "status": intelligence["intelligence_status"],
            "evidence": intelligence["evidence"],
            "warnings": intelligence["warnings"],
        }

    @app.get("/v1/devices/samples")
    async def samples(
        device_id: str = Query(...),
        limit: int = Query(100, ge=1, le=5000),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        order: str = Query("desc"),
    ) -> list[dict[str, object]]:
        start, end, normalized_order = _range_and_order(from_, to, order)
        return await store.samples(
            device_id,
            limit=limit,
            start=start,
            end=end,
            order=normalized_order,
        )

    @app.get("/v1/devices/registers/{name}/history")
    async def register_history(
        name: str,
        device_id: str = Query(...),
        limit: int = Query(1000, ge=1, le=10000),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        order: str = Query("desc"),
    ) -> list[dict[str, object]]:
        start, end, normalized_order = _range_and_order(from_, to, order)
        return await store.register_history(
            device_id,
            name,
            limit=limit,
            start=start,
            end=end,
            order=normalized_order,
        )

    @app.get("/v1/devices/registers/history")
    async def registers_history(
        name: Annotated[list[str], Query()],
        device_id: str = Query(...),
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
            rows = await store.multi_register_history(
                device_id,
                names,
                start=start,
                end=end,
                order=normalized_order,
                bucket_seconds=bucket_seconds,
                max_points=max_points,
            )
        except HistoryQueryError as exc:
            raise _history_error(exc) from exc
        return build_history_response(
            device_id=device_id,
            start=start,
            end=end,
            resolution=normalized_resolution,
            rows=rows,
        )

    @app.get("/v1/devices/registers/stats")
    async def register_stats(
        name: Annotated[list[str], Query()],
        device_id: str = Query(...),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ) -> dict[str, object]:
        start, end, _ = _range_and_order(from_, to, "asc")
        try:
            names = normalize_names(name)
        except HistoryQueryError as exc:
            raise _history_error(exc) from exc
        return {
            "device_id": device_id,
            "from": start,
            "to": end,
            "registers": await store.register_stats(device_id, names, start=start, end=end),
        }

    @app.get("/v1/devices/history/summary")
    async def history_summary(
        device_id: str = Query(...),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
    ) -> dict[str, object]:
        start, end, _ = _range_and_order(from_, to, "asc")
        return await store.history_summary(device_id, start=start, end=end)

    @app.get("/v1/devices/history/controller-daily")
    async def controller_daily_history(
        device_id: str = Query(...),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        limit: int = Query(200, ge=1, le=500),
    ) -> list[dict[str, object]]:
        start, end = _daily_range(from_, to)
        return await controller_history.list(device_id, start=start, end=end, limit=limit)

    @app.get("/v1/devices/history/controller-daily/summary")
    async def controller_daily_history_summary(device_id: str = Query(...)) -> dict[str, object]:
        return await controller_history.summary(device_id)

    @app.get("/v1/devices/history/export")
    async def history_export(
        device_id: str = Query(...),
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
        except HistoryQueryError as exc:
            raise _history_error(exc) from exc
        export_format = format_.strip().lower()
        if export_format not in {"csv", "jsonl"}:
            raise HTTPException(status_code=400, detail="format must be csv or jsonl")

        rows = store.iter_history_export(
            device_id,
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
            headers={"Content-Disposition": f'attachment; filename="telemetry-history.{suffix}"'},
        )

    @app.get("/v1/devices/polling/performance")
    async def polling_performance(
        device_id: str = Query(...),
        window: int = Query(300, ge=3, le=5000),
        mode: str = Query("watch"),
    ) -> dict[str, object]:
        return await performance_store.summary(
            device_id,
            window=window,
            mode=_polling_mode(mode),
        )

    @app.get("/v1/devices/polling/history")
    async def polling_history(
        device_id: str = Query(...),
        limit: int = Query(300, ge=1, le=5000),
        mode: str = Query("watch"),
    ) -> list[dict[str, object]]:
        return await performance_store.recent(
            device_id,
            limit=limit,
            mode=_polling_mode(mode),
        )

    @app.get("/v1/devices/{device_id:path}")
    async def device(device_id: str) -> dict[str, object]:
        record = await store.get_device(device_id)
        if record is None:
            raise HTTPException(status_code=404, detail="device not found")
        return record

    return app


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
            "device_id",
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
            "device_id",
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