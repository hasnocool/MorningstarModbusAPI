from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

import morningstar_modbus.controller_history_liveview as liveview_module
import morningstar_modbus.storage as storage_module
from morningstar_modbus.api import create_app
from morningstar_modbus.config import HistoryBackfillConfig
from morningstar_modbus.controller_history import (
    ControllerHistoryBackfiller,
    ControllerHistoryRepository,
    parse_liveview_datalog,
)
from morningstar_modbus.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    PollResult,
    RegisterValue,
)
from morningstar_modbus.storage import TelemetryStore

LIVEVIEW_HTML = """
<html><body><table>
<tr><th>Day</th><td>0</td><td>-1</td><td>-2</td></tr>
<tr><th>Events</th><td>1</td><td>2</td><td>0</td></tr>
<tr><th>Hourmeter</th><td>100d 2h</td><td>99d 2h</td><td>98d 2h</td></tr>
<tr><th>Max. Battery Voltage</th><td>14.5 V</td><td>14.4 V</td><td>14.3 V</td></tr>
<tr><th>Min. Battery Voltage</th><td>12.5 V</td><td>12.2 V</td><td>12.1 V</td></tr>
<tr><th>Max. Array Voltage</th><td>82.1 V</td><td>81.5 V</td><td>80.4 V</td></tr>
<tr><th>Max. Output Power</th><td>600 W</td><td>575 W</td><td>540 W</td></tr>
<tr><th>Amp hours</th><td>160 Ah</td><td>150 Ah</td><td>140 Ah</td></tr>
<tr><th>Watt hours</th><td>2200 Wh</td><td>2100 Wh</td><td>1900 Wh</td></tr>
<tr><th>Max. Battery Temp.</th><td>29 C</td><td>28 C</td><td>27 C</td></tr>
<tr><th>Min. Battery Temp.</th><td>18 C</td><td>17 C</td><td>16 C</td></tr>
<tr><th>Absorption timer</th><td>90 min</td><td>80 min</td><td>70 min</td></tr>
<tr><th>Float timer</th><td>120 min</td><td>110 min</td><td>100 min</td></tr>
<tr><th>Equalize timer</th><td>0 min</td><td>0 min</td><td>0 min</td></tr>
<tr><th>Faults</th><td>None</td><td>None</td><td>None</td></tr>
<tr><th>Alarms</th><td>None</td><td>RTS open</td><td>None</td></tr>
</table></body></html>
"""


async def _seed_device(tmp_path: Path) -> tuple[TelemetryStore, str, DiscoveredDevice]:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    endpoint = Endpoint("tcp", "192.0.2.10", 1, port=502)
    identity = DeviceIdentification("Morningstar", "TriStar MPPT", "1.0")
    device = DiscoveredDevice(endpoint, identity, 1.0, "tristar_mppt")
    device_id = await store.upsert_device(device)
    return store, device_id, device


def test_liveview_parser_preserves_daily_provenance() -> None:
    records = parse_liveview_datalog(
        LIVEVIEW_HTML,
        retrieved_at=datetime(2026, 8, 15, 2, 30, tzinfo=UTC),
    )
    assert [record.day_offset for record in records] == [0, -1, -2]
    assert records[0].controller_day.isoformat() == "2026-08-15"
    assert records[1].controller_day.isoformat() == "2026-08-14"
    assert records[1].is_complete is True
    assert records[0].is_complete is False
    assert records[1].battery_voltage_min == 12.2
    assert records[1].battery_voltage_max == 14.4
    assert records[1].charge_wh == 2100.0
    assert records[1].absorption_minutes == 80.0
    assert records[1].hourmeter_hours == 2378.0
    assert records[1].alarms == "RTS open"
    assert records[1].source == "liveview-http"
    assert records[1].day_start_utc == "2026-08-14T00:00:00+00:00"
    assert records[1].day_end_utc == "2026-08-15T00:00:00+00:00"
    assert records[1].raw is not None
    assert records[1].raw["Max. Battery Voltage"] == "14.4 V"


@pytest.mark.asyncio
async def test_repository_marks_days_with_no_live_samples_as_filled_gaps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, device_id, device = await _seed_device(tmp_path)
    timestamps = iter(("2026-08-14T12:00:00+00:00",))
    monkeypatch.setattr(storage_module, "utcnow", lambda: next(timestamps))
    await store.save_poll(
        device_id,
        PollResult(
            device.endpoint,
            device.identification,
            device.profile,
            1.0,
            (RegisterValue("battery_voltage", 0x18, "holding", (100,), 13.0, "V"),),
        ),
    )
    records = parse_liveview_datalog(
        LIVEVIEW_HTML,
        retrieved_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )
    repository = ControllerHistoryRepository(store.path)
    assert await repository.upsert(device_id, records) == 3

    rows = await repository.list(device_id)
    by_day = {row["controller_day"]: row for row in rows}
    assert by_day["2026-08-14"]["live_sample_count"] == 1
    assert by_day["2026-08-14"]["fills_full_day_gap"] is False
    assert by_day["2026-08-13"]["fills_full_day_gap"] is True
    assert by_day["2026-08-13"]["source"] == "liveview-http"

    summary = await repository.summary(device_id)
    assert summary["record_count"] == 3
    assert summary["complete_days"] == 2
    assert summary["full_day_gaps_filled"] == 1


@pytest.mark.asyncio
async def test_backfiller_fetches_liveview_without_touching_raw_poll_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, device_id, device = await _seed_device(tmp_path)

    async def fake_fetch(*_args, **_kwargs) -> str:
        return LIVEVIEW_HTML

    monkeypatch.setattr(liveview_module, "_fetch_http_text", fake_fetch)
    backfiller = ControllerHistoryBackfiller(store.path, HistoryBackfillConfig())
    result = await backfiller.sync(device_id, device)

    assert result.status == "ok"
    assert result.records_seen == 3
    assert result.records_written == 3
    assert await store.samples(device_id) == []
    summary = await backfiller.repository.summary(device_id)
    assert summary["last_sync"]["status"] == "ok"


@pytest.mark.asyncio
async def test_controller_daily_api_exposes_backfilled_records(tmp_path: Path) -> None:
    store, device_id, _device = await _seed_device(tmp_path)
    repository = ControllerHistoryRepository(store.path)
    records = parse_liveview_datalog(
        LIVEVIEW_HTML,
        retrieved_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )
    await repository.upsert(device_id, records)

    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/devices/history/controller-daily",
            params={"device_id": device_id, "from": "2026-08-13", "to": "2026-08-15"},
        )
        assert response.status_code == 200
        body = response.json()
        assert [row["controller_day"] for row in body] == ["2026-08-14", "2026-08-13"]
        assert all(row["source"] == "liveview-http" for row in body)

        summary = await client.get(
            "/v1/devices/history/controller-daily/summary",
            params={"device_id": device_id},
        )
        assert summary.status_code == 200
        assert summary.json()["record_count"] == 3
