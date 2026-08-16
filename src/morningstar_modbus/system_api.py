# src/morningstar_modbus/system_api.py
"""FastAPI routes for system/site aggregation, topology, events, and SSE."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from morningstar_modbus.history import HistoryQueryError, normalize_time_range
from morningstar_modbus.system_data import SystemDataRepository, SystemNotFoundError
from morningstar_modbus.system_semantics import system_metric_catalog


def _not_found(exc: SystemNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=f"system not found: {exc}")


def _range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    try:
        return normalize_time_range(start, end)
    except HistoryQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sse(event: str, data: object, *, event_id: str | None = None) -> str:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    parts.append(f"data: {payload}")
    return "\n".join(parts) + "\n\n"


def attach_system_routes(app: FastAPI, data: SystemDataRepository) -> None:
    """Attach the read-only system/site API to an existing FastAPI application."""

    @app.get("/v1/systems/metrics/catalog")
    async def system_metric_definitions() -> list[dict[str, object]]:
        return system_metric_catalog()

    @app.get("/v1/systems")
    async def systems() -> list[dict[str, object]]:
        return await data.list_systems()

    @app.get("/v1/systems/{system_uid}")
    async def system(system_uid: str) -> dict[str, object]:
        try:
            return await data.system(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/controllers")
    async def system_controllers(system_uid: str) -> list[dict[str, object]]:
        try:
            return await data.controllers(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/latest")
    async def system_latest(system_uid: str) -> dict[str, object]:
        try:
            return await data.latest(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/energy")
    async def system_energy(system_uid: str) -> dict[str, object]:
        try:
            return await data.energy(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/health")
    async def system_health(system_uid: str) -> dict[str, object]:
        try:
            return await data.health(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/topology")
    async def system_topology(system_uid: str) -> dict[str, object]:
        try:
            return await data.topology(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/events")
    async def system_events(
        system_uid: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        limit: int = Query(500, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        start, end = _range(from_, to)
        try:
            return await data.events(system_uid, start=start, end=end, limit=limit)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

    @app.get("/v1/systems/{system_uid}/history")
    async def system_history(
        system_uid: str,
        metric: str = Query(...),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        resolution: str = Query("5m"),
        max_points: int = Query(20_000, ge=1, le=20_000),
    ) -> dict[str, object]:
        start, end = _range(from_, to)
        try:
            return await data.history(
                system_uid,
                metric,
                start=start,
                end=end,
                resolution=resolution,
                max_points=max_points,
            )
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc
        except ValueError as exc:
            status_code = 413 if "exceeds" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/v1/systems/{system_uid}/stream")
    async def system_stream(
        request: Request,
        system_uid: str,
        interval: float = Query(1.0, ge=0.25, le=60.0),
        heartbeat: float = Query(15.0, ge=5.0, le=120.0),
    ) -> StreamingResponse:
        try:
            await data.system(system_uid)
        except SystemNotFoundError as exc:
            raise _not_found(exc) from exc

        async def stream() -> AsyncIterator[str]:
            previous_snapshot = ""
            seen_events: set[str] = set()
            last_heartbeat = time.monotonic()
            while not await request.is_disconnected():
                snapshot = await data.latest(system_uid)
                fingerprint = json.dumps(snapshot, separators=(",", ":"), sort_keys=True, default=str)
                if fingerprint != previous_snapshot:
                    previous_snapshot = fingerprint
                    yield _sse("telemetry", snapshot)

                recent = await data.events(system_uid, limit=100)
                for event in reversed(recent):
                    event_id = str(event.get("id") or "")
                    if not event_id or event_id in seen_events:
                        continue
                    seen_events.add(event_id)
                    if len(seen_events) > 2000:
                        seen_events = set(list(seen_events)[-1000:])
                    yield _sse("system_event", event, event_id=event_id)

                now = time.monotonic()
                if now - last_heartbeat >= heartbeat:
                    last_heartbeat = now
                    yield ": heartbeat\n\n"
                await asyncio.sleep(interval)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
