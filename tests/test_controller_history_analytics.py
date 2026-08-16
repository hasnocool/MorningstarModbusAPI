# tests/test_controller_history_analytics.py
from datetime import UTC, date, datetime

import aiosqlite
import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.domain.models import DeviceIdentification, DiscoveredDevice, Endpoint
from morningstar_modbus.history.analytics import ControllerHistoryAnalytics
from morningstar_modbus.history.retained.storage import ControllerHistoryRepository
from morningstar_modbus.history.retained.types import ControllerDailyRecord, LIVEVIEW_SOURCE
from morningstar_modbus.persistence.store import TelemetryStore


async def _seed_controller(path: str) -> tuple[TelemetryStore, str, str]:
    store = TelemetryStore(path)
    await store.initialize()
    registry = ControllerRegistry(path)
    endpoint = Endpoint("tcp", "192.0.2.10", 1, port=502)
    device = DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        1.0,
        "tristar_mppt",
    )
    controller_uid, device_id = await registry.register_observation(device)
    return store, controller_uid, device_id


async def _insert_power_sample(path: str, device_id: str, observed_at: str, watts: float) -> None:
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            """
            INSERT INTO poll_samples(device_id, observed_at, latency_ms, profile)
            VALUES (?, ?, 10.0, 'tristar_mppt')
            """,
            (device_id, observed_at),
        )
        sample_id = int(cursor.lastrowid or 0)
        await db.execute(
            """
            INSERT INTO register_values(
                sample_id, register_name, address, function, raw_json,
                numeric_value, text_value, unit
            ) VALUES (?, 'output_power', 58, 'holding', '[0]', ?, NULL, 'W')
            """,
            (sample_id, watts),
        )
        await db.commit()


async def _insert_recovered_day(path: str, device_id: str) -> None:
    repository = ControllerHistoryRepository(path)
    await repository.upsert(
        device_id,
        [
            ControllerDailyRecord(
                controller_day=date(2026, 8, 14),
                retrieved_at="2026-08-16T00:01:00+00:00",
                day_offset=-2,
                is_complete=True,
                day_start_utc="2026-08-14T00:00:00+00:00",
                day_end_utc="2026-08-15T00:00:00+00:00",
                source=LIVEVIEW_SOURCE,
                source_path="/datalog.html",
                battery_voltage_min=12.2,
                battery_voltage_max=14.4,
                array_voltage_max=81.5,
                output_power_max=575.0,
                charge_ah=150.0,
                charge_wh=2100.0,
                absorption_minutes=80.0,
                float_minutes=110.0,
                equalize_minutes=0.0,
                faults="None",
                alarms="None",
                raw={"Watt hours": "2100 Wh"},
            )
        ],
    )


@pytest.mark.asyncio
async def test_coverage_distinguishes_live_days_recovered_days_and_missing_days(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    _store, controller_uid, device_id = await _seed_controller(path)
    await _insert_recovered_day(path, device_id)
    await _insert_power_sample(path, device_id, "2026-08-15T12:00:00+00:00", 600.0)
    await _insert_power_sample(path, device_id, "2026-08-15T12:05:00+00:00", 600.0)

    analytics = ControllerHistoryAnalytics(path)
    coverage = await analytics.coverage(
        controller_uid,
        start="2026-08-14",
        end="2026-08-17",
    )

    assert coverage["realtime"]["days_with_samples"] == 1
    assert coverage["realtime"]["coverage_percent"] == 33.33
    assert coverage["daily_evidence"]["covered_days"] == 2
    assert coverage["daily_evidence"]["coverage_percent"] == 66.67
    assert coverage["daily_evidence"]["recovered_days"] == 1
    assert coverage["daily_evidence"]["missing_days"] == 1

    gaps = await analytics.gaps(
        controller_uid,
        start="2026-08-14",
        end="2026-08-17",
    )
    assert gaps["gaps"] == [
        {
            "from": "2026-08-14",
            "to": "2026-08-15",
            "duration_days": 1,
            "status": "recovered",
            "recoverability": "controller_daily",
            "controller_record_count": 1,
        },
        {
            "from": "2026-08-16",
            "to": "2026-08-17",
            "duration_days": 1,
            "status": "missing",
            "recoverability": "none",
            "controller_record_count": 0,
        },
    ]


@pytest.mark.asyncio
async def test_energy_daily_preserves_controller_and_poll_provenance(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    _store, controller_uid, device_id = await _seed_controller(path)
    await _insert_recovered_day(path, device_id)
    await _insert_power_sample(path, device_id, "2026-08-15T12:00:00+00:00", 600.0)
    await _insert_power_sample(path, device_id, "2026-08-15T12:05:00+00:00", 600.0)

    analytics = ControllerHistoryAnalytics(path)
    result = await analytics.energy_daily(
        controller_uid,
        start="2026-08-14",
        end="2026-08-16",
        max_gap_seconds=300,
    )
    by_day = {row["date"]: row for row in result["days"]}

    recovered = by_day["2026-08-14"]
    assert recovered["energy"]["controller_reported_wh"] == 2100.0
    assert recovered["energy"]["integrated_output_wh"] is None
    assert recovered["quality"]["provenance"] == ["controller_internal_logger"]

    live = by_day["2026-08-15"]
    assert live["energy"]["controller_reported_wh"] is None
    assert live["energy"]["integrated_output_wh"] == 50.0
    assert live["quality"]["integrated_seconds"] == 300.0
    assert live["quality"]["provenance"] == ["live_poll"]


@pytest.mark.asyncio
async def test_controller_history_analytics_routes(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    store, controller_uid, device_id = await _seed_controller(path)
    await _insert_recovered_day(path, device_id)
    await _insert_power_sample(path, device_id, "2026-08-15T12:00:00+00:00", 600.0)
    await _insert_power_sample(path, device_id, "2026-08-15T12:05:00+00:00", 600.0)

    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/v1/controllers/{controller_uid}/history/coverage",
            params={"from": "2026-08-14", "to": "2026-08-16"},
        )
        assert response.status_code == 200
        assert response.json()["daily_evidence"]["coverage_percent"] == 100.0

        response = await client.get(
            f"/v1/controllers/{controller_uid}/history/gaps",
            params={"from": "2026-08-14", "to": "2026-08-16"},
        )
        assert response.status_code == 200
        assert response.json()["gaps"][0]["status"] == "recovered"

        response = await client.get(
            f"/v1/controllers/{controller_uid}/energy/daily",
            params={"from": "2026-08-14", "to": "2026-08-16", "max_gap_seconds": 300},
        )
        assert response.status_code == 200
        assert len(response.json()["days"]) == 2

        response = await client.get(
            f"/v1/controllers/{controller_uid}/energy/summary",
            params={"from": "2026-08-14", "to": "2026-08-16", "max_gap_seconds": 300},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["energy"]["controller_reported_wh"] == 2100.0
        assert payload["energy"]["integrated_output_wh"] == 50.0
