# tests/test_system_live_controller_count.py
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from morningstar_modbus.api.routers.systems import attach_system_routes


class FakeSystemData:
    async def list_systems(self) -> list[dict[str, object]]:
        return [
            {
                "system_uid": "sys_default",
                "name": "default",
                "controller_count": 2,
            }
        ]

    async def system(self, identifier: str) -> dict[str, object]:
        assert identifier == "sys_default"
        return {
            "system_uid": "sys_default",
            "name": "default",
            "controller_count": 2,
        }

    async def controllers(self, identifier: str) -> list[dict[str, object]]:
        assert identifier == "sys_default"
        return [
            {
                "controller_uid": "ctrl_current",
                "status": "online",
            }
        ]


@pytest.mark.asyncio
async def test_system_routes_reconcile_stale_membership_count_from_live_inventory() -> None:
    app = FastAPI()
    attach_system_routes(app, FakeSystemData())  # type: ignore[arg-type]
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        systems = await client.get("/v1/systems")
        system = await client.get("/v1/systems/sys_default")
        controllers = await client.get("/v1/systems/sys_default/controllers")

    assert systems.status_code == 200
    assert systems.json()[0]["controller_count"] == 1
    assert system.status_code == 200
    assert system.json()["controller_count"] == 1
    assert controllers.status_code == 200
    assert len(controllers.json()) == 1
