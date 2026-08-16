"""Time-series history validation and response shaping helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

RESOLUTIONS: dict[str, int | None] = {
    "raw": None,
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "1d": 24 * 60 * 60,
}
ORDERS = {"asc", "desc"}
MAX_REGISTER_NAMES = 50
MAX_JSON_POINTS = 20_000


class HistoryQueryError(ValueError):
    """Invalid history query parameters."""


class HistoryQueryTooLarge(HistoryQueryError):
    """A JSON history query would return too many points."""


def _parse_timestamp(value: str, *, field: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise HistoryQueryError(f"{field} must be an RFC 3339 / ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoryQueryError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def normalize_time_range(
    start: str | None,
    end: str | None,
) -> tuple[str | None, str | None]:
    """Normalize an inclusive start / exclusive end range to UTC ISO timestamps."""

    start_dt = _parse_timestamp(start, field="from") if start else None
    end_dt = _parse_timestamp(end, field="to") if end else None
    if start_dt is not None and end_dt is not None and start_dt >= end_dt:
        raise HistoryQueryError("from must be earlier than to")
    return (
        start_dt.isoformat() if start_dt is not None else None,
        end_dt.isoformat() if end_dt is not None else None,
    )


def validate_resolution(value: str) -> tuple[str, int | None]:
    normalized = value.strip().lower()
    if normalized not in RESOLUTIONS:
        allowed = ", ".join(RESOLUTIONS)
        raise HistoryQueryError(f"resolution must be one of: {allowed}")
    return normalized, RESOLUTIONS[normalized]


def validate_order(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ORDERS:
        raise HistoryQueryError("order must be asc or desc")
    return normalized


def normalize_names(names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(dict.fromkeys(name.strip() for name in names if name.strip()))
    if not cleaned:
        raise HistoryQueryError("at least one register name is required")
    if len(cleaned) > MAX_REGISTER_NAMES:
        raise HistoryQueryError(f"at most {MAX_REGISTER_NAMES} register names may be requested")
    return cleaned


def build_history_response(
    *,
    device_id: str,
    start: str | None,
    end: str | None,
    resolution: str,
    rows: list[dict[str, Any]],
) -> dict[str, object]:
    """Group flat storage rows into chart-friendly register series."""

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row["register_name"])
        series = grouped.setdefault(
            name,
            {
                "name": name,
                "unit": row.get("unit"),
                "kind": row.get("kind", "unknown"),
                "points": [],
            },
        )
        kind = str(row.get("kind", "unknown"))
        if series["kind"] != kind:
            series["kind"] = "mixed"
        if series["unit"] is None and row.get("unit") is not None:
            series["unit"] = row["unit"]

        if resolution == "raw":
            point = {
                "observed_at": row["observed_at"],
                "address": row["address"],
                "function": row["function"],
                "raw": row["raw"],
                "value": row["value"],
            }
        elif kind == "numeric":
            point = {
                "bucket_start": row["bucket_start"],
                "count": row["count"],
                "min": row["min_value"],
                "max": row["max_value"],
                "avg": row["avg_value"],
                "first": row["first_value"],
                "last": row["last_value"],
            }
        else:
            point = {
                "bucket_start": row["bucket_start"],
                "samples": row["count"],
                "first": row["first_value"],
                "last": row["last_value"],
                "transitions": row["transitions"],
            }
        series["points"].append(point)

    return {
        "device_id": device_id,
        "from": start,
        "to": end,
        "resolution": resolution,
        "series": list(grouped.values()),
    }
