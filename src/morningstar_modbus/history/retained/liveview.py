"""TriStar MPPT LiveView daily-history parser, HTTP reader, and backfill service."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta, tzinfo
from datetime import time as datetime_time
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from morningstar_modbus.config import HistoryBackfillConfig
from morningstar_modbus.domain.models import DiscoveredDevice
from morningstar_modbus.history.retained.storage import ControllerHistoryRepository
from morningstar_modbus.history.retained.types import (
    LIVEVIEW_SOURCE,
    BackfillResult,
    ControllerDailyRecord,
    ControllerHistoryError,
)

_NUMERIC_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_HOURMETER_RE = re.compile(r"(?:(?P<days>\d+)\s*d)?\s*(?:(?P<hours>\d+(?:\.\d+)?)\s*h)?", re.I)

_FIELD_ALIASES = {
    "events": "event_count",
    "event": "event_count",
    "hourmeter": "hourmeter_hours",
    "hour meter": "hourmeter_hours",
    "max battery voltage": "battery_voltage_max",
    "maximum battery voltage": "battery_voltage_max",
    "min battery voltage": "battery_voltage_min",
    "minimum battery voltage": "battery_voltage_min",
    "max array voltage": "array_voltage_max",
    "maximum array voltage": "array_voltage_max",
    "max input voltage": "array_voltage_max",
    "max output power": "output_power_max",
    "maximum output power": "output_power_max",
    "amp hours": "charge_ah",
    "ah": "charge_ah",
    "watt hours": "charge_wh",
    "wh": "charge_wh",
    "max battery temp": "battery_temp_max",
    "max battery temperature": "battery_temp_max",
    "maximum battery temperature": "battery_temp_max",
    "min battery temp": "battery_temp_min",
    "min battery temperature": "battery_temp_min",
    "minimum battery temperature": "battery_temp_min",
    "absorption timer": "absorption_minutes",
    "absorption time": "absorption_minutes",
    "float timer": "float_minutes",
    "float time": "float_minutes",
    "equalize timer": "equalize_minutes",
    "equalization timer": "equalize_minutes",
    "equalize time": "equalize_minutes",
    "faults": "faults",
    "fault": "faults",
    "alarms": "alarms",
    "alarm": "alarms",
}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table":
            if self._table_depth == 0:
                self._table = []
            self._table_depth += 1
        elif tag == "tr" and self._table_depth == 1:
            self._row = []
        elif tag in {"td", "th"} and self._table_depth == 1 and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._table is not None:
                if self._table:
                    self.tables.append(self._table)
                self._table = None


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _label_key(value: str) -> str:
    normalized = _clean_text(value).lower().rstrip(":")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _parse_number(value: str) -> float | None:
    match = _NUMERIC_RE.search(value.replace(",", ""))
    return float(match.group(0)) if match else None


def _parse_hourmeter(value: str) -> float | None:
    compact = _clean_text(value)
    match = _HOURMETER_RE.fullmatch(compact)
    if match and (match.group("days") or match.group("hours")):
        days = float(match.group("days") or 0)
        hours = float(match.group("hours") or 0)
        return days * 24.0 + hours
    return _parse_number(compact)


def _parse_int(value: str) -> int | None:
    number = _parse_number(value)
    return int(number) if number is not None else None


def _parse_day_offset(value: str) -> int | None:
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def _record_from_column(
    rows: list[list[str]],
    column: int,
    day_offset: int,
    *,
    retrieved_at: datetime,
    calendar_timezone: tzinfo,
    source_path: str,
) -> ControllerDailyRecord:
    raw: dict[str, str] = {}
    values: dict[str, Any] = {}
    for row in rows:
        if not row or column >= len(row):
            continue
        label = _label_key(row[0])
        if label == "day":
            continue
        raw_value = _clean_text(row[column])
        if not raw_value:
            continue
        raw[row[0]] = raw_value
        field = _FIELD_ALIASES.get(label)
        if field is None:
            continue
        if field == "hourmeter_hours":
            values[field] = _parse_hourmeter(raw_value)
        elif field == "event_count":
            values[field] = _parse_int(raw_value)
        elif field in {"faults", "alarms"}:
            values[field] = raw_value
        else:
            values[field] = _parse_number(raw_value)
    local_reference = retrieved_at.astimezone(calendar_timezone)
    controller_day = local_reference.date() + timedelta(days=day_offset)
    day_start = datetime.combine(controller_day, datetime_time.min, tzinfo=calendar_timezone)
    day_end = datetime.combine(
        controller_day + timedelta(days=1),
        datetime_time.min,
        tzinfo=calendar_timezone,
    )
    return ControllerDailyRecord(
        controller_day=controller_day,
        retrieved_at=retrieved_at.astimezone(UTC).isoformat(),
        day_offset=day_offset,
        is_complete=day_offset < 0,
        day_start_utc=day_start.astimezone(UTC).isoformat(),
        day_end_utc=day_end.astimezone(UTC).isoformat(),
        source=LIVEVIEW_SOURCE,
        source_path=source_path,
        raw=raw,
        **values,
    )


def parse_liveview_datalog(
    html: str,
    *,
    retrieved_at: datetime | None = None,
    source_path: str = "/datalog.html",
    max_days: int = 200,
    calendar_timezone: tzinfo | None = None,
) -> list[ControllerDailyRecord]:
    """Parse the built-in LiveView datalog table into provenance-aware daily records."""
    parser = _TableParser()
    parser.feed(html)
    timestamp = retrieved_at or datetime.now().astimezone()
    if timestamp.tzinfo is None:
        raise ControllerHistoryError("retrieved_at must include a timezone")
    effective_timezone = calendar_timezone or timestamp.tzinfo
    for table in parser.tables:
        day_row = next((row for row in table if row and _label_key(row[0]) == "day"), None)
        if day_row is None or len(day_row) < 2:
            continue
        records: list[ControllerDailyRecord] = []
        for column, cell in enumerate(day_row[1:], start=1):
            offset = _parse_day_offset(cell)
            if offset is None or offset > 0 or abs(offset) > max_days:
                continue
            records.append(
                _record_from_column(
                    table,
                    column,
                    offset,
                    retrieved_at=timestamp,
                    calendar_timezone=effective_timezone,
                    source_path=source_path,
                )
            )
        if records:
            return sorted(records, key=lambda item: item.controller_day, reverse=True)
    raise ControllerHistoryError("LiveView response did not contain a recognizable datalog table")


async def _fetch_http_text(
    host: str,
    *,
    port: int,
    path: str,
    timeout_seconds: float,
    max_bytes: int,
) -> str:
    writer: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            reader, writer = await asyncio.open_connection(host, port)
            request = (
                f"GET {path} HTTP/1.0\r\n"
                f"Host: {host}\r\n"
                "Accept: text/html\r\n"
                "Accept-Encoding: identity\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(request)
            await writer.drain()
            payload = bytearray()
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > max_bytes:
                    raise ControllerHistoryError(
                        f"LiveView response exceeded configured maximum of {max_bytes} bytes"
                    )
    except (TimeoutError, OSError) as exc:
        raise ControllerHistoryError(f"LiveView HTTP request failed: {exc}") from exc
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
    header, separator, body = bytes(payload).partition(b"\r\n\r\n")
    if not separator:
        raise ControllerHistoryError("LiveView returned an invalid HTTP response")
    status_line = header.splitlines()[0].decode("ascii", errors="replace") if header else ""
    parts = status_line.split()
    if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) != 200:
        raise ControllerHistoryError(f"LiveView returned HTTP status {status_line or 'unknown'}")
    return body.decode("utf-8", errors="replace")


def _resolve_calendar_timezone(name: str) -> tzinfo:
    normalized = name.strip()
    if normalized.lower() == "local":
        return datetime.now().astimezone().tzinfo or UTC
    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ControllerHistoryError(f"unknown backfill calendar timezone: {name}") from exc


class ControllerHistoryBackfiller:
    """Fetch LiveView daily history and upsert it without altering raw poll samples."""

    def __init__(self, database_path: str, config: HistoryBackfillConfig) -> None:
        self.config = config
        self.repository = ControllerHistoryRepository(database_path)
        self._calendar_timezone = _resolve_calendar_timezone(config.calendar_timezone)

    async def initialize(self) -> None:
        await self.repository.initialize()

    def supports(self, device: DiscoveredDevice) -> bool:
        return (
            self.config.enabled
            and device.profile == "tristar_mppt"
            and device.endpoint.transport == "tcp"
        )

    async def sync(self, device_id: str, device: DiscoveredDevice) -> BackfillResult:
        if not self.supports(device):
            return BackfillResult(status="unsupported")
        attempted_at = datetime.now(UTC).isoformat()
        try:
            html = await _fetch_http_text(
                device.endpoint.target,
                port=self.config.http_port,
                path=self.config.http_path,
                timeout_seconds=self.config.timeout_seconds,
                max_bytes=self.config.max_response_bytes,
            )
            records = parse_liveview_datalog(
                html,
                retrieved_at=datetime.now().astimezone(),
                source_path=self.config.http_path,
                max_days=self.config.max_days,
                calendar_timezone=self._calendar_timezone,
            )
            written = await self.repository.upsert(device_id, records)
            oldest = min((item.controller_day for item in records), default=None)
            newest = max((item.controller_day for item in records), default=None)
            result = BackfillResult(
                status="ok",
                records_seen=len(records),
                records_written=written,
                oldest_day=oldest.isoformat() if oldest else None,
                newest_day=newest.isoformat() if newest else None,
            )
            await self.repository.record_sync(
                device_id,
                attempted_at=attempted_at,
                status=result.status,
                records_seen=result.records_seen,
                records_written=result.records_written,
                oldest_day=result.oldest_day,
                newest_day=result.newest_day,
            )
            return result
        except Exception as exc:
            await self.repository.record_sync(
                device_id,
                attempted_at=attempted_at,
                status="error",
                records_seen=0,
                records_written=0,
                oldest_day=None,
                newest_day=None,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
