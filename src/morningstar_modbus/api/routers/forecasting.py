"""Read-only predictive-operations API routes."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from morningstar_modbus.forecasting import ForecastService
from morningstar_modbus.history.controller_data import ControllerNotFoundError
from morningstar_modbus.systems.data import SystemNotFoundError


def attach_forecast_routes(app: FastAPI, forecasts: ForecastService) -> None:
    """Attach offline-first forecast resources to an existing FastAPI app."""

    @app.get("/v1/systems/{system_uid}/forecast")
    async def system_forecast(system_uid: str) -> dict[str, object]:
        try:
            return await forecasts.system_forecast(system_uid)
        except SystemNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"system not found: {exc}",
            ) from exc

    @app.get("/v1/systems/{system_uid}/forecast/accuracy")
    async def system_forecast_accuracy(system_uid: str) -> dict[str, object]:
        try:
            return await forecasts.forecast_accuracy(system_uid)
        except SystemNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"system not found: {exc}",
            ) from exc

    @app.get("/v1/controllers/{controller_uid}/charge-forecast")
    async def controller_charge_forecast(controller_uid: str) -> dict[str, object]:
        try:
            return await forecasts.controller_charge_forecast(controller_uid)
        except ControllerNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"controller not found: {exc}",
            ) from exc
