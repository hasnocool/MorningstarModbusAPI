"""Shared models for controller-retained daily history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

LIVEVIEW_SOURCE = "liveview-http"


class ControllerHistoryError(RuntimeError):
    """Raised when controller-retained history cannot be fetched or parsed."""


@dataclass(frozen=True, slots=True)
class ControllerDailyRecord:
    controller_day: date
    retrieved_at: str
    day_offset: int
    is_complete: bool
    day_start_utc: str
    day_end_utc: str
    source: str
    source_path: str
    hourmeter_hours: float | None = None
    event_count: int | None = None
    battery_voltage_min: float | None = None
    battery_voltage_max: float | None = None
    array_voltage_max: float | None = None
    output_power_max: float | None = None
    charge_ah: float | None = None
    charge_wh: float | None = None
    battery_temp_min: float | None = None
    battery_temp_max: float | None = None
    absorption_minutes: float | None = None
    float_minutes: float | None = None
    equalize_minutes: float | None = None
    faults: str | None = None
    alarms: str | None = None
    raw: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class BackfillResult:
    status: str
    records_seen: int = 0
    records_written: int = 0
    oldest_day: str | None = None
    newest_day: str | None = None
