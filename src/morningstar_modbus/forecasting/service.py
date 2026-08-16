"""Offline-first predictive operations over normalized system history."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median

from morningstar_modbus.history.controller_data import ControllerNotFoundError
from morningstar_modbus.systems.data import SystemDataRepository

_BUCKET_MINUTES = 15
_BUCKET_HOURS = _BUCKET_MINUTES / 60.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _minute_of_day(value: datetime) -> int:
    return value.hour * 60 + value.minute


def _bucket_floor_minutes(value: datetime) -> int:
    minute = _minute_of_day(value)
    return minute - (minute % _BUCKET_MINUTES)


def _at_minute(day: datetime, minute: int) -> datetime:
    return day.replace(
        hour=minute // 60,
        minute=minute % 60,
        second=0,
        microsecond=0,
    )


def _confidence(days: int, coverage: float | None = None) -> str:
    if days >= 14 and (coverage is None or coverage >= 0.8):
        return "high"
    if days >= 7 and (coverage is None or coverage >= 0.5):
        return "medium"
    return "low"


@dataclass(frozen=True, slots=True)
class ForecastPolicy:
    """Conservative defaults for local predictive operations."""

    history_days: int = 28
    minimum_training_days: int = 5
    minimum_daily_samples: int = 16
    productive_power_w: float = 25.0
    backtest_days: int = 14
    max_history_points: int = 20_000


class ForecastService:
    """Produce explainable forecasts without cloud or weather dependencies."""

    model_name = "local-time-of-day-percentile-v1"

    def __init__(
        self,
        systems: SystemDataRepository,
        *,
        policy: ForecastPolicy | None = None,
    ) -> None:
        self.systems = systems
        self.policy = policy or ForecastPolicy()

    async def system_forecast(
        self,
        system_uid: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = (now or _utcnow()).astimezone(UTC)
        solar = await self.solar_forecast(system_uid, now=current)
        controllers = await self.systems.controllers(system_uid)
        charge_forecasts = list(
            await asyncio.gather(
                *(
                    self.controller_charge_forecast(
                        str(controller["controller_uid"]),
                        now=current,
                    )
                    for controller in controllers
                )
            )
        )
        probabilities = [
            float(item["float_probability"])
            for item in charge_forecasts
            if isinstance(item.get("float_probability"), (int, float))
        ]
        expected_times = [
            parsed
            for item in charge_forecasts
            if (parsed := _parse_time(item.get("expected_float_at"))) is not None
        ]
        return {
            "system_uid": system_uid,
            "generated_at": current.isoformat(),
            "status": solar["status"],
            "confidence": solar["confidence"],
            "solar": solar,
            "charge": {
                "controllers": charge_forecasts,
                "all_controllers_float_probability": (
                    min(probabilities) if probabilities else None
                ),
                "expected_all_controllers_float_at": (
                    max(expected_times).isoformat() if expected_times else None
                ),
            },
            "model": {
                "name": self.model_name,
                "version": 1,
                "offline": True,
                "weather_used": False,
            },
            "semantics": (
                "Forecasts are evidence-backed estimates with uncertainty bands, not "
                "controller commands or guaranteed outcomes."
            ),
        }

    async def solar_forecast(
        self,
        system_uid: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = (now or _utcnow()).astimezone(UTC)
        day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        history = await self.systems.bucketed_metric_history(
            system_uid,
            "solar_input_power_w",
            start=(day_start - timedelta(days=self.policy.history_days)).isoformat(),
            end=current.isoformat(),
            resolution="15m",
            max_buckets=self.policy.max_history_points,
        )
        by_day = self._solar_history(history)
        today_key = current.date().isoformat()
        today = by_day.get(today_key, {})
        training = {
            day: curve
            for day, curve in by_day.items()
            if day != today_key and len(curve) >= self.policy.minimum_daily_samples
        }
        training_days = len(training)
        current_bucket = _bucket_floor_minutes(current)

        curve: list[dict[str, object]] = []
        productive_minutes: list[int] = []
        expected_buckets_before_now = 0
        observed_buckets_before_now = 0
        expected_so_far_wh = 0.0
        observed_so_far_wh = 0.0
        remaining = {"p10": 0.0, "p50": 0.0, "p90": 0.0}

        for minute in range(0, 24 * 60, _BUCKET_MINUTES):
            values = [
                curve_values[minute]
                for curve_values in training.values()
                if minute in curve_values
            ]
            p10 = _percentile(values, 0.10)
            p50 = _percentile(values, 0.50)
            p90 = _percentile(values, 0.90)
            observed = today.get(minute)
            if p50 is not None and p50 >= self.policy.productive_power_w:
                productive_minutes.append(minute)
            if (
                minute <= current_bucket
                and p50 is not None
                and p50 >= self.policy.productive_power_w
            ):
                expected_buckets_before_now += 1
                expected_so_far_wh += p50 * _BUCKET_HOURS
                if observed is not None:
                    observed_buckets_before_now += 1
            if minute <= current_bucket and observed is not None:
                observed_so_far_wh += max(0.0, observed) * _BUCKET_HOURS
            if minute > current_bucket:
                if p10 is not None:
                    remaining["p10"] += max(0.0, p10) * _BUCKET_HOURS
                if p50 is not None:
                    remaining["p50"] += max(0.0, p50) * _BUCKET_HOURS
                if p90 is not None:
                    remaining["p90"] += max(0.0, p90) * _BUCKET_HOURS
            if p50 is not None or observed is not None:
                curve.append(
                    {
                        "at": _at_minute(day_start, minute).isoformat(),
                        "minute_of_day": minute,
                        "phase": "observed" if minute <= current_bucket else "forecast",
                        "observed_w": observed,
                        "p10_w": p10,
                        "p50_w": p50,
                        "p90_w": p90,
                        "training_samples": len(values),
                    }
                )

        coverage = (
            observed_buckets_before_now / expected_buckets_before_now
            if expected_buckets_before_now
            else None
        )
        ready = (
            training_days >= self.policy.minimum_training_days
            and bool(productive_minutes)
        )
        progress_ratio = (
            observed_so_far_wh / expected_so_far_wh
            if expected_so_far_wh > 0
            else None
        )
        first_productive = min(productive_minutes) if productive_minutes else None
        last_productive = max(productive_minutes) if productive_minutes else None

        latest = await self.systems.latest(system_uid)
        metrics = latest.get("metrics")
        solar_metric = (
            metrics.get("solar_input_power_w")
            if isinstance(metrics, dict)
            else None
        )
        current_power = (
            _numeric(solar_metric.get("value"))
            if isinstance(solar_metric, dict)
            else None
        )

        return {
            "system_uid": system_uid,
            "metric": "solar_input_power_w",
            "unit": "W",
            "status": "ready" if ready else "insufficient_evidence",
            "generated_at": current.isoformat(),
            "current_power_w": current_power,
            "training_days": training_days,
            "history_days": self.policy.history_days,
            "coverage_fraction_today": coverage,
            "confidence": _confidence(training_days, coverage) if ready else "low",
            "productive_window": {
                "start": (
                    _at_minute(day_start, first_productive).isoformat()
                    if first_productive is not None
                    else None
                ),
                "end": (
                    _at_minute(
                        day_start,
                        last_productive + _BUCKET_MINUTES,
                    ).isoformat()
                    if last_productive is not None
                    and last_productive + _BUCKET_MINUTES < 24 * 60
                    else None
                ),
                "threshold_w": self.policy.productive_power_w,
            },
            "energy": {
                "observed_input_wh": observed_so_far_wh,
                "expected_so_far_p50_wh": expected_so_far_wh,
                "progress_ratio": progress_ratio,
                "remaining_p10_wh": remaining["p10"],
                "remaining_p50_wh": remaining["p50"],
                "remaining_p90_wh": remaining["p90"],
                "eod_p10_wh": observed_so_far_wh + remaining["p10"],
                "eod_p50_wh": observed_so_far_wh + remaining["p50"],
                "eod_p90_wh": observed_so_far_wh + remaining["p90"],
                "integration_semantics": (
                    "15-minute normalized solar-input power buckets integrated locally; "
                    "not a controller energy counter"
                ),
            },
            "curve": curve,
            "provenance": {
                "source": "local normalized system history",
                "model": self.model_name,
                "resolution": "15m",
                "weather_used": False,
                "internet_required": False,
            },
        }

    async def forecast_accuracy(
        self,
        system_uid: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = (now or _utcnow()).astimezone(UTC)
        day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        history_window = self.policy.history_days + self.policy.backtest_days + 2
        history = await self.systems.bucketed_metric_history(
            system_uid,
            "solar_input_power_w",
            start=(day_start - timedelta(days=history_window)).isoformat(),
            end=day_start.isoformat(),
            resolution="15m",
            max_buckets=self.policy.max_history_points,
        )
        by_day = self._solar_history(history)
        daily_energy = {
            day: sum(
                max(0.0, value) * _BUCKET_HOURS
                for value in curve.values()
            )
            for day, curve in by_day.items()
            if len(curve) >= self.policy.minimum_daily_samples
        }
        ordered_days = sorted(daily_energy)
        rows: list[dict[str, object]] = []
        for index, day in enumerate(ordered_days):
            prior_days = ordered_days[
                max(0, index - self.policy.history_days) : index
            ]
            training = [daily_energy[item] for item in prior_days]
            if len(training) < self.policy.minimum_training_days:
                continue
            actual = daily_energy[day]
            p10 = _percentile(training, 0.10)
            p50 = _percentile(training, 0.50)
            p90 = _percentile(training, 0.90)
            if p10 is None or p50 is None or p90 is None:
                continue
            error_percent = (
                abs(actual - p50) / actual * 100.0
                if actual > 0
                else None
            )
            rows.append(
                {
                    "day": day,
                    "actual_wh": actual,
                    "p10_wh": p10,
                    "p50_wh": p50,
                    "p90_wh": p90,
                    "absolute_error_percent": error_percent,
                    "inside_p10_p90": p10 <= actual <= p90,
                    "training_days": len(training),
                }
            )

        rows = rows[-self.policy.backtest_days :]
        selected_errors = [
            float(item["absolute_error_percent"])
            for item in rows
            if isinstance(item.get("absolute_error_percent"), (int, float))
        ]
        selected_inside = sum(bool(item.get("inside_p10_p90")) for item in rows)
        return {
            "system_uid": system_uid,
            "model": self.model_name,
            "status": (
                "ready"
                if len(rows) >= self.policy.minimum_training_days
                else "insufficient_evidence"
            ),
            "evaluated_days": len(rows),
            "median_absolute_error_percent": (
                median(selected_errors) if selected_errors else None
            ),
            "mean_absolute_error_percent": (
                sum(selected_errors) / len(selected_errors)
                if selected_errors
                else None
            ),
            "p90_absolute_error_percent": _percentile(
                selected_errors,
                0.90,
            ),
            "p10_p90_interval_coverage": (
                selected_inside / len(rows) if rows else None
            ),
            "days": rows,
            "methodology": (
                "Completed-day solar-input energy is compared with a percentile "
                "forecast built only from earlier locally observed days."
            ),
        }

    async def controller_charge_forecast(
        self,
        controller_uid: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = (now or _utcnow()).astimezone(UTC)
        controller = await self.systems.controllers_data.controller(controller_uid)
        if controller is None:
            raise ControllerNotFoundError(controller_uid)
        rows = await self.systems.controllers_data.register_history(
            controller_uid,
            "charge_state",
            limit=10_000,
            start=(current - timedelta(days=self.policy.history_days)).isoformat(),
            end=current.isoformat(),
            order="asc",
        )
        states_by_day: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        for row in rows:
            observed_at = _parse_time(row.get("observed_at"))
            state = str(row.get("value") or "").strip().upper()
            if observed_at is None or not state:
                continue
            states_by_day[observed_at.date().isoformat()].append(
                (observed_at, state)
            )

        today_key = current.date().isoformat()
        observed_days = 0
        float_days = 0
        first_float_minutes: list[float] = []
        for day, states in states_by_day.items():
            if day == today_key or len(states) < 3:
                continue
            observed_days += 1
            first_float = next(
                (
                    timestamp
                    for timestamp, state in states
                    if state == "FLOAT"
                ),
                None,
            )
            if first_float is not None:
                float_days += 1
                first_float_minutes.append(float(_minute_of_day(first_float)))

        latest = await self.systems.controllers_data.latest(controller_uid)
        current_state: str | None = None
        if latest is not None:
            for item in latest.get("values", []):
                if (
                    isinstance(item, dict)
                    and str(item.get("register_name")) == "charge_state"
                ):
                    current_state = (
                        str(item.get("value") or "").strip().upper() or None
                    )
                    break

        historical_probability = (
            float_days / observed_days if observed_days else None
        )
        probability = 1.0 if current_state == "FLOAT" else historical_probability
        first_float_median = (
            median(first_float_minutes) if first_float_minutes else None
        )
        expected_float_at = (
            _at_minute(
                current.replace(hour=0, minute=0, second=0, microsecond=0),
                int(first_float_median),
            ).isoformat()
            if first_float_median is not None
            else None
        )
        ready = observed_days >= self.policy.minimum_training_days
        return {
            "controller_uid": controller_uid,
            "status": "ready" if ready else "insufficient_evidence",
            "generated_at": current.isoformat(),
            "current_state": current_state,
            "float_probability": (
                probability if ready or current_state == "FLOAT" else None
            ),
            "historical_float_probability": historical_probability,
            "expected_float_at": expected_float_at if ready else None,
            "training_days": observed_days,
            "float_days": float_days,
            "confidence": _confidence(observed_days) if ready else "low",
            "model": "historical-charge-cycle-frequency-v1",
            "provenance": (
                "controller-scoped source-backed charge_state history; "
                "no controller mutation"
            ),
        }

    @staticmethod
    def _solar_history(
        history: dict[str, object],
    ) -> dict[str, dict[int, float]]:
        by_day: dict[str, dict[int, float]] = defaultdict(dict)
        for point in history.get("points", []):
            if not isinstance(point, dict):
                continue
            observed_at = _parse_time(
                point.get("bucket_start") or point.get("observed_at")
            )
            value = _numeric(point.get("value"))
            if observed_at is None or value is None:
                continue
            minute = _minute_of_day(observed_at)
            by_day[observed_at.date().isoformat()][minute] = value
        return dict(by_day)
