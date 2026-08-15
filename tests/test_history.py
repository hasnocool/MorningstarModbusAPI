import json
from pathlib import Path

import httpx
import pytest

import morningstar_modbus.storage as storage_module
from morningstar_modbus.api import create_app
from morningstar_modbus.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    PollResult,
    RegisterValue,
)
from morningstar_modbus.storage import TelemetryStore


async def _seed_history(tmp_path: Path, monkeypatch) -> tuple[TelemetryStore, str]:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    endpoint = Endpoint("tcp", "127.0.0.1", 1, port=502)
    identity = DeviceIdentification("Morningstar", "TriStar MPPT", "1.0")
    device_id = await store.upsert_device(
        DiscoveredDevice(endpoint, identity, 1.0, "tristar_mppt")
    )
    timestamps = iter(
        (
            "2026-08-14T00:00:00+00:00",
            "2026-08-14T00:02:00+00:00",
            "2026-08-14T00:07:00+00:00",
        )
    )
    monkeypatch.setattr(storage_module, "utcnow", lambda: next(timestamps))
    observations = ((12.0, "MPPT"), (14.0, "ABSORPTION"), (13.0, "FLOAT"))
    for voltage, state in observations:
        await store.save_poll(
            device_id,
            PollResult(
                endpoint,
                identity,
                "tristar_mppt",
                2.0,
                (
                    RegisterValue(
                        "battery_voltage",
                        0x18,
                        "holding",
                        (int(voltage * 10),),
                        voltage,
                        "V",
                    ),
                    RegisterValue(
                        "charge_state",
                        0x32,
                        "holding",
                        (5,),
                        state,
                        None,
                    ),
                ),
            ),
        )
    return store, device_id


@pytest.mark.asyncio
async def test_raw_range_and_backward_compatible_history(tmp_path: Path, monkeypatch) -> None:
    store, device_id = await _seed_history(tmp_path, monkeypatch)
    rows = await store.register_history(
        device_id,
        "battery_voltage",
        start="2026-08-14T00:01:00+00:00",
        end="2026-08-14T00:08:00+00:00",
        order="asc",
    )
    assert [row["value"] for row in rows] == [14.0, 13.0]
    assert rows[0]["raw"] == [140]


@pytest.mark.asyncio
async def test_five_minute_numeric_and_state_aggregation(tmp_path: Path, monkeypatch) -> None:
    store, device_id = await _seed_history(tmp_path, monkeypatch)
    rows = await store.multi_register_history(
        device_id,
        ("battery_voltage", "charge_state"),
        start=None,
        end=None,
        order="asc",
        bucket_seconds=300,
        max_points=100,
    )
    voltage = [row for row in rows if row["register_name"] == "battery_voltage"]
    state = [row for row in rows if row["register_name"] == "charge_state"]

    assert voltage[0]["bucket_start"] == "2026-08-14T00:00:00Z"
    assert voltage[0]["count"] == 2
    assert voltage[0]["min_value"] == 12.0
    assert voltage[0]["max_value"] == 14.0
    assert voltage[0]["avg_value"] == 13.0
    assert voltage[0]["first_value"] == 12.0
    assert voltage[0]["last_value"] == 14.0
    assert voltage[1]["bucket_start"] == "2026-08-14T00:05:00Z"
    assert voltage[1]["first_value"] == 13.0

    assert state[0]["first_value"] == "MPPT"
    assert state[0]["last_value"] == "ABSORPTION"
    assert state[0]["transitions"] == 1
    assert state[1]["first_value"] == "FLOAT"
    assert state[1]["transitions"] == 1


@pytest.mark.asyncio
async def test_stats_and_history_summary(tmp_path: Path, monkeypatch) -> None:
    store, device_id = await _seed_history(tmp_path, monkeypatch)
    stats = await store.register_stats(
        device_id,
        ("battery_voltage", "charge_state"),
        start=None,
        end=None,
    )
    voltage = next(row for row in stats if row["register_name"] == "battery_voltage")
    state = next(row for row in stats if row["register_name"] == "charge_state")

    assert voltage["count"] == 3
    assert voltage["min"] == 12.0
    assert voltage["max"] == 14.0
    assert voltage["avg"] == 13.0
    assert voltage["first"] == 12.0
    assert voltage["last"] == 13.0
    assert voltage["delta"] == 1.0
    assert state["transitions"] == 2
    assert state["state_counts"] == {"ABSORPTION": 1, "FLOAT": 1, "MPPT": 1}

    summary = await store.history_summary(device_id, start=None, end=None)
    assert summary["sample_count"] == 3
    assert summary["register_observation_count"] == 6
    assert summary["distinct_register_count"] == 2
    assert summary["error_count"] == 0
    assert summary["observed_duration_seconds"] == 420
    assert int(summary["database_bytes"]) > 0


@pytest.mark.asyncio
async def test_history_api_aggregation_guardrails_and_exports(tmp_path: Path, monkeypatch) -> None:
    store, device_id = await _seed_history(tmp_path, monkeypatch)
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        params = [
            ("device_id", device_id),
            ("name", "battery_voltage"),
            ("name", "charge_state"),
            ("resolution", "5m"),
        ]
        response = await client.get("/v1/devices/registers/history", params=params)
        assert response.status_code == 200
        body = response.json()
        assert body["resolution"] == "5m"
        assert {series["name"] for series in body["series"]} == {
            "battery_voltage",
            "charge_state",
        }

        stats = await client.get(
            "/v1/devices/registers/stats",
            params=[
                ("device_id", device_id),
                ("name", "battery_voltage"),
                ("name", "charge_state"),
            ],
        )
        assert stats.status_code == 200
        assert len(stats.json()["registers"]) == 2

        summary = await client.get(
            "/v1/devices/history/summary",
            params={"device_id": device_id},
        )
        assert summary.json()["sample_count"] == 3

        too_large = await client.get(
            "/v1/devices/registers/history",
            params=[
                ("device_id", device_id),
                ("name", "battery_voltage"),
                ("resolution", "raw"),
                ("max_points", "1"),
            ],
        )
        assert too_large.status_code == 413

        invalid_range = await client.get(
            "/v1/devices/registers/battery_voltage/history",
            params={
                "device_id": device_id,
                "from": "2026-08-15T00:00:00Z",
                "to": "2026-08-14T00:00:00Z",
            },
        )
        assert invalid_range.status_code == 400

        csv_export = await client.get(
            "/v1/devices/history/export",
            params=[
                ("device_id", device_id),
                ("name", "battery_voltage"),
                ("format", "csv"),
            ],
        )
        assert csv_export.status_code == 200
        assert csv_export.text.startswith("observed_at,device_id,register_name")
        assert "battery_voltage" in csv_export.text

        jsonl_export = await client.get(
            "/v1/devices/history/export",
            params=[
                ("device_id", device_id),
                ("name", "charge_state"),
                ("format", "jsonl"),
                ("resolution", "5m"),
            ],
        )
        assert jsonl_export.status_code == 200
        lines = [json.loads(line) for line in jsonl_export.text.splitlines()]
        assert lines[0]["register_name"] == "charge_state"
        assert lines[0]["kind"] == "text"
