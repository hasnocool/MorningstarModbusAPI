# tests/test_site_intelligence.py
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.domain.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    PollResult,
    RegisterValue,
)
from morningstar_modbus.intelligence.incidents import SiteIntelligenceService
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.persistence.incidents import IncidentStore
from morningstar_modbus.persistence.store import TelemetryStore
from morningstar_modbus.systems.data import SystemDataRepository


def _finding(*, severity: str = "warning") -> dict[str, object]:
    return {
        "detector": "test_detector",
        "evaluation_key": "test_detector|sys_default",
        "fingerprint": "test_detector|sys_default",
        "category": "data_integrity",
        "severity": severity,
        "confidence": "high",
        "title": "Test incident",
        "summary": "Synthetic regression evidence.",
        "controller_uid": None,
        "observed_value": 1.0,
        "expected_low": 0.0,
        "expected_high": 0.5,
        "unit": "count",
        "evidence": [
            {
                "code": "test",
                "message": "test evidence",
                "value": 1,
            }
        ],
    }


def _device() -> DiscoveredDevice:
    endpoint = Endpoint("tcp", "192.0.2.50", 1, port=502)
    intelligence = DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        serial_number="TS-INTELLIGENCE",
        firmware="29",
        confidence=1.0,
        status="verified",
    )
    return DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        1.0,
        "tristar_mppt",
        intelligence,
    )


def _poll(
    device: DiscoveredDevice,
    *,
    terminal_v: float,
    sense_v: float,
    input_w: float,
    output_w: float,
) -> PollResult:
    values = (
        RegisterValue("battery_voltage", 0x0018, "holding", (0,), terminal_v, "V"),
        RegisterValue("battery_sense_voltage", 0x001A, "holding", (0,), sense_v, "V"),
        RegisterValue("battery_charge_current", 0x001C, "holding", (0,), 20.0, "A"),
        RegisterValue("faults", 0x002C, "holding", (0,), 0),
        RegisterValue("alarms", 0x002E, "holding", (0, 0), 0),
        RegisterValue("charge_state", 0x0032, "holding", (0,), "MPPT"),
        RegisterValue("output_power", 0x003A, "holding", (0,), output_w, "W"),
        RegisterValue("input_power_reported", 0x003B, "holding", (0,), input_w, "W"),
        RegisterValue("daily_charge_wh", 0x0044, "holding", (0,), 1200.0, "Wh"),
    )
    return PollResult(
        device.endpoint,
        device.identification,
        device.profile,
        5.0,
        values,
    )


@pytest.mark.asyncio
async def test_incident_store_opens_updates_and_resolves_only_evaluated_detectors(
    tmp_path: Path,
) -> None:
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    key = "test_detector|sys_default"

    opened = await store.reconcile("sys_default", [_finding()], evaluated_keys={key})
    assert [item["transition"] for item in opened] == ["opened"]
    incident_uid = str(opened[0]["incident_uid"])

    unchanged = await store.reconcile("sys_default", [_finding()], evaluated_keys={key})
    assert unchanged == []
    active = await store.get(incident_uid)
    assert active is not None
    assert active["state"] == "active"
    assert active["occurrence_count"] == 2

    not_evaluated = await store.reconcile("sys_default", [], evaluated_keys=set())
    assert not_evaluated == []
    active = await store.get(incident_uid)
    assert active is not None
    assert active["state"] == "active"

    resolved = await store.reconcile("sys_default", [], evaluated_keys={key})
    assert [item["transition"] for item in resolved] == ["resolved"]
    assert resolved[0]["state"] == "resolved"


@pytest.mark.asyncio
async def test_site_intelligence_detects_and_resolves_electrical_anomalies(
    tmp_path: Path,
) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    registry = ControllerRegistry(store.path)
    device = _device()
    controller_uid, device_id = await registry.register_observation(device)

    await store.save_poll(
        device_id,
        _poll(
            device,
            terminal_v=14.4,
            sense_v=13.9,
            input_w=400.0,
            output_w=260.0,
        ),
    )
    systems = SystemDataRepository(store.path)
    service = SiteIntelligenceService(store.path, systems)
    incidents = await service.scan("sys_default")
    active_detectors = {
        str(item["detector"])
        for item in incidents
        if item["state"] == "active" and item.get("controller_uid") == controller_uid
    }
    assert "battery_sense_divergence" in active_detectors
    assert "controller_efficiency" in active_detectors

    await store.save_poll(
        device_id,
        _poll(
            device,
            terminal_v=14.2,
            sense_v=14.18,
            input_w=400.0,
            output_w=380.0,
        ),
    )
    incidents = await service.scan("sys_default")
    latest_by_detector = {
        str(item["detector"]): item
        for item in incidents
        if item.get("controller_uid") == controller_uid
    }
    assert latest_by_detector["battery_sense_divergence"]["state"] == "resolved"
    assert latest_by_detector["controller_efficiency"]["state"] == "resolved"

    events = await systems.events("sys_default", limit=100)
    event_types = {str(item["event_type"]) for item in events}
    assert "INCIDENT_OPENED" in event_types
    assert "INCIDENT_RESOLVED" in event_types


@pytest.mark.asyncio
async def test_site_intelligence_api_exposes_baselines_incidents_and_transparent_score(
    tmp_path: Path,
) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        incidents = await client.get("/v1/incidents")
        assert incidents.status_code == 200
        assert incidents.json() == []

        baselines = await client.get("/v1/systems/sys_default/baselines")
        assert baselines.status_code == 200
        solar = baselines.json()["solar_input_power"]
        assert solar["status"] == "insufficient_evidence"
        assert "no weather dependency" in solar["provenance"]

        score = await client.get("/v1/systems/sys_default/health-score")
        assert score.status_code == 200
        payload = score.json()
        assert payload["score"] == 100
        assert payload["components"] == {
            "production": 20,
            "charging": 20,
            "battery": 20,
            "communications": 20,
            "data_integrity": 20,
        }
        assert payload["penalties"] == []
