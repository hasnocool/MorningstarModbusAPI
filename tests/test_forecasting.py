from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.forecasting import ForecastPolicy, ForecastService
from morningstar_modbus.persistence.store import TelemetryStore


class _FakeControllerData:
    def __init__(self, now: datetime) -> None:
        self.now = now

    async def controller(self, controller_uid: str) -> dict[str, object] | None:
        if controller_uid != "ctrl-1":
            return None
        return {"controller_uid": controller_uid}

    async def latest(self, controller_uid: str) -> dict[str, object] | None:
        if controller_uid != "ctrl-1":
            return None
        return {
            "observed_at": self.now.isoformat(),
            "values": [
                {
                    "register_name": "charge_state",
                    "value": "MPPT",
                    "unit": None,
                }
            ],
        }

    async def register_history(
        self,
        controller_uid: str,
        name: str,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        if controller_uid != "ctrl-1" or name != "charge_state":
            return []
        rows: list[dict[str, object]] = []
        for days_ago in range(1, 7):
            day = self.now - timedelta(days=days_ago)
            states = [(8, "MPPT"), (12, "ABSORPTION")]
            if days_ago % 2 == 0:
                states.append((14, "FLOAT"))
            else:
                states.append((16, "MPPT"))
            for hour, state in states:
                rows.append(
                    {
                        "observed_at": day.replace(
                            hour=hour,
                            minute=0,
                            second=0,
                            microsecond=0,
                        ).isoformat(),
                        "value": state,
                    }
                )
        return sorted(rows, key=lambda row: str(row["observed_at"]))


class _FakeSystems:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.controllers_data = _FakeControllerData(now)

    async def controllers(self, system_uid: str) -> list[dict[str, object]]:
        assert system_uid == "sys_default"
        return [{"controller_uid": "ctrl-1"}]

    async def latest(self, system_uid: str) -> dict[str, object]:
        assert system_uid == "sys_default"
        return {
            "system_uid": system_uid,
            "observed_at": self.now.isoformat(),
            "metrics": {
                "solar_input_power_w": {
                    "value": 400.0,
                    "unit": "W",
                    "quality": "complete",
                }
            },
        }

    async def history(
        self,
        system_uid: str,
        metric: str,
        **kwargs: object,
    ) -> dict[str, object]:
        assert system_uid == "sys_default"
        assert metric == "solar_input_power_w"
        end = datetime.fromisoformat(str(kwargs["end"]))
        points: list[dict[str, object]] = []
        start_day = end.replace(hour=0, minute=0, second=0, microsecond=0)
        for days_ago in range(1, 13):
            day = start_day - timedelta(days=days_ago)
            for minute in range(6 * 60, 18 * 60, 15):
                points.append(
                    {
                        "bucket_start": day.replace(
                            hour=minute // 60,
                            minute=minute % 60,
                        ).isoformat(),
                        "value": 400.0,
                    }
                )
        if end.date() == self.now.date() and end > start_day:
            for minute in range(6 * 60, 12 * 60 + 1, 15):
                points.append(
                    {
                        "bucket_start": start_day.replace(
                            hour=minute // 60,
                            minute=minute % 60,
                        ).isoformat(),
                        "value": 400.0,
                    }
                )
        return {
            "system_uid": system_uid,
            "metric": {"name": metric},
            "resolution": "15m",
            "points": points,
        }


@pytest.mark.asyncio
async def test_forecast_service_builds_offline_energy_outlook_and_charge_probability() -> None:
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    service = ForecastService(
        _FakeSystems(now),  # type: ignore[arg-type]
        policy=ForecastPolicy(minimum_training_days=5),
    )

    payload = await service.system_forecast("sys_default", now=now)
    solar = payload["solar"]
    assert solar["status"] == "ready"
    assert solar["training_days"] == 12
    assert solar["provenance"]["weather_used"] is False
    assert solar["provenance"]["internet_required"] is False
    assert solar["energy"]["remaining_p50_wh"] > 2000
    assert solar["energy"]["eod_p10_wh"] == pytest.approx(
        solar["energy"]["eod_p90_wh"]
    )

    charge = payload["charge"]["controllers"][0]
    assert charge["status"] == "ready"
    assert charge["float_probability"] == pytest.approx(0.5)
    assert charge["expected_float_at"].endswith("14:00:00+00:00")
    assert payload["model"]["offline"] is True


@pytest.mark.asyncio
async def test_forecast_accuracy_uses_only_completed_prior_days() -> None:
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    service = ForecastService(
        _FakeSystems(now),  # type: ignore[arg-type]
        policy=ForecastPolicy(minimum_training_days=5),
    )

    accuracy = await service.forecast_accuracy("sys_default", now=now)
    assert accuracy["status"] == "ready"
    assert accuracy["evaluated_days"] >= 5
    assert accuracy["median_absolute_error_percent"] == pytest.approx(0.0)
    assert accuracy["p10_p90_interval_coverage"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_forecast_api_is_read_only_and_handles_empty_history(tmp_path: Path) -> None:
    store = TelemetryStore(str(tmp_path / "forecast.sqlite3"))
    await store.initialize()
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        forecast = await client.get("/v1/systems/sys_default/forecast")
        assert forecast.status_code == 200
        payload = forecast.json()
        assert payload["status"] == "insufficient_evidence"
        assert payload["model"]["offline"] is True
        assert payload["model"]["weather_used"] is False

        accuracy = await client.get("/v1/systems/sys_default/forecast/accuracy")
        assert accuracy.status_code == 200
        assert accuracy.json()["status"] == "insufficient_evidence"
