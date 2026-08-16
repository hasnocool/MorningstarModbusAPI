# src/morningstar_modbus/api/routers/incidents.py
"""Read-only routes for proactive site intelligence, baselines, incidents, and health scoring."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from morningstar_modbus.history.controller_data import ControllerNotFoundError
from morningstar_modbus.intelligence.incidents import SiteIntelligenceService
from morningstar_modbus.systems.data import SystemNotFoundError


def _state(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"active", "resolved"}:
        raise HTTPException(status_code=400, detail="state must be active or resolved")
    return normalized


def _severity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=400, detail="severity must be info, warning, or critical")
    return normalized


async def _system_for_controller(service: SiteIntelligenceService, controller_uid: str) -> str:
    controller = await service.systems.controllers_data.controller(controller_uid)
    if controller is None:
        raise ControllerNotFoundError(controller_uid)
    systems = await service.systems.list_systems()
    for system in systems:
        system_uid = str(system.get("system_uid") or "")
        if not system_uid:
            continue
        controllers = await service.systems.controllers(system_uid)
        if any(str(item.get("controller_uid")) == controller_uid for item in controllers):
            return system_uid
    raise SystemNotFoundError(f"no system contains controller {controller_uid}")


def attach_incident_routes(app: FastAPI, service: SiteIntelligenceService) -> None:
    """Attach evidence-backed intelligence routes without adding control-plane writes."""

    @app.get("/v1/incidents")
    async def incidents(
        state: str | None = Query(None),
        severity: str | None = Query(None),
        limit: int = Query(500, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        await service.scan_all()
        return await service.incidents(
            state=_state(state), severity=_severity(severity), limit=limit
        )

    @app.get("/v1/incidents/{incident_uid}")
    async def incident(incident_uid: str) -> dict[str, object]:
        record = await service.store.get(incident_uid)
        if record is None:
            raise HTTPException(status_code=404, detail="incident not found")
        return record

    @app.get("/v1/systems/{system_uid}/incidents")
    async def system_incidents(
        system_uid: str,
        state: str | None = Query(None),
        severity: str | None = Query(None),
        limit: int = Query(500, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        try:
            await service.systems.system(system_uid)
            return await service.incidents(
                system_uid=system_uid,
                state=_state(state),
                severity=_severity(severity),
                limit=limit,
                scan=True,
            )
        except SystemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"system not found: {exc}") from exc

    @app.get("/v1/systems/{system_uid}/baselines")
    async def system_baselines(system_uid: str) -> dict[str, object]:
        try:
            return await service.baselines(system_uid)
        except SystemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"system not found: {exc}") from exc

    @app.get("/v1/systems/{system_uid}/health-score")
    async def system_health_score(system_uid: str) -> dict[str, object]:
        try:
            return await service.health_score(system_uid)
        except SystemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"system not found: {exc}") from exc

    @app.get("/v1/controllers/{controller_uid}/incidents")
    async def controller_incidents(
        controller_uid: str,
        state: str | None = Query(None),
        severity: str | None = Query(None),
        limit: int = Query(500, ge=1, le=5000),
    ) -> list[dict[str, object]]:
        try:
            system_uid = await _system_for_controller(service, controller_uid)
            await service.scan(system_uid)
        except ControllerNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"controller not found: {exc}") from exc
        except SystemNotFoundError:
            pass
        return await service.incidents(
            controller_uid=controller_uid,
            state=_state(state),
            severity=_severity(severity),
            limit=limit,
        )

    @app.get("/v1/controllers/{controller_uid}/health-score")
    async def controller_health_score(controller_uid: str) -> dict[str, object]:
        try:
            system_uid = await _system_for_controller(service, controller_uid)
            return await service.health_score(system_uid, controller_uid=controller_uid)
        except ControllerNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"controller not found: {exc}") from exc
        except SystemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/controllers/{controller_uid}/charge-cycle")
    async def controller_charge_cycle(controller_uid: str) -> dict[str, object]:
        try:
            await service.systems.controllers_data.scope(controller_uid)
            return await service.charge_cycle_summary(controller_uid)
        except ControllerNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"controller not found: {exc}") from exc
