# src/morningstar_modbus/api.py
"""FastAPI application exposing stored telemetry and Morningstar device intelligence."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from morningstar_modbus import __version__
from morningstar_modbus.catalog import catalog_detail, catalog_summary
from morningstar_modbus.storage import TelemetryStore

LOGGER = logging.getLogger(__name__)


def create_app(store: TelemetryStore) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await store.initialize()
        yield

    app = FastAPI(
        title="Morningstar Modbus API",
        version=__version__,
        description="Read-only API for persisted Morningstar Modbus telemetry.",
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

    @app.get("/v1/devices/samples")
    async def samples(
        device_id: str = Query(...),
        limit: int = Query(100, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        return await store.samples(device_id, limit=limit)

    @app.get("/v1/devices/registers/{name}/history")
    async def register_history(
        name: str,
        device_id: str = Query(...),
        limit: int = Query(1000, ge=1, le=10000),
    ) -> list[dict[str, object]]:
        return await store.register_history(device_id, name, limit=limit)

    @app.get("/v1/devices/{device_id:path}")
    async def device(device_id: str) -> dict[str, object]:
        record = await store.get_device(device_id)
        if record is None:
            raise HTTPException(status_code=404, detail="device not found")
        return record

    return app
