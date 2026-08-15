"""Physical-controller inventory over persisted Modbus endpoint records."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import aiosqlite

ONLINE_GRACE_SECONDS = 120.0


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_fresh(value: object, *, now: datetime, grace_seconds: float) -> bool:
    parsed = _parse_time(value)
    if parsed is None:
        return False
    return max(0.0, (now - parsed).total_seconds()) <= grace_seconds


def _signature(row: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(row.get("vendor_name") or "").strip().lower(),
        str(row.get("product_code") or "").strip().lower(),
        str(row.get("profile") or "").strip().lower(),
        int(row.get("unit_id") or 0),
    )


def _connection_payload(row: dict[str, Any]) -> dict[str, object]:
    return {
        "device_id": row["id"],
        "stable_key": row["stable_key"],
        "transport": row["transport"],
        "target": row["target"],
        "port": row.get("port"),
        "unit_id": row["unit_id"],
        "usb_serial": row.get("usb_serial"),
        "usb_vid": row.get("usb_vid"),
        "usb_pid": row.get("usb_pid"),
        "status": row["status"],
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "last_error": row.get("last_error"),
    }


class ControllerInventoryRepository:
    """Group connection records into physical Morningstar controllers.

    The controller's own serial number is the strongest identity. USB serial
    identity is used only when controller metadata is unavailable. Endpoint
    keys remain the final fallback so ambiguous identical controllers are not
    accidentally merged.
    """

    def __init__(self, path: str, *, online_grace_seconds: float = ONLINE_GRACE_SECONDS) -> None:
        self.path = path
        self.online_grace_seconds = online_grace_seconds

    async def initialize(self) -> None:
        # No schema migration is required; this repository derives controller
        # identity from the existing endpoint and intelligence tables.
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys=ON")

    async def mark_all_offline(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE devices SET status='offline' WHERE status='online'")
            await db.commit()

    async def mark_device_offline(self, device_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE devices SET status='offline' WHERE id=? AND status!='error'",
                (device_id,),
            )
            await db.commit()

    async def list_controllers(self) -> list[dict[str, object]]:
        rows = await self._rows()
        if not rows:
            return []

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        signature_to_serial_keys: dict[tuple[str, str, str, int], set[str]] = defaultdict(set)

        for row in rows:
            serial = str(row.get("serial_number") or "").strip()
            if not serial:
                continue
            key = f"morningstar:{str(row.get('profile') or '').lower()}:{serial.lower()}"
            groups[key].append(row)
            signature_to_serial_keys[_signature(row)].add(key)

        for row in rows:
            serial = str(row.get("serial_number") or "").strip()
            if serial:
                continue

            serial_candidates = signature_to_serial_keys.get(_signature(row), set())
            if len(serial_candidates) == 1:
                groups[next(iter(serial_candidates))].append(row)
                continue

            usb_serial = str(row.get("usb_serial") or "").strip()
            if usb_serial:
                key = f"usb:{usb_serial.lower()}:unit:{int(row.get('unit_id') or 0)}"
            else:
                key = f"endpoint:{row['stable_key']}"
            groups[key].append(row)

        now = datetime.now(UTC)
        controllers = [self._group_payload(key, group, now=now) for key, group in groups.items()]
        controllers.sort(key=lambda item: str(item.get("last_seen") or ""), reverse=True)
        return controllers

    def _group_payload(
        self,
        controller_id: str,
        rows: list[dict[str, Any]],
        *,
        now: datetime,
    ) -> dict[str, object]:
        ordered = sorted(rows, key=lambda row: str(row.get("last_seen") or ""), reverse=True)
        current = ordered[0]
        current_fresh = _is_fresh(
            current.get("last_seen"),
            now=now,
            grace_seconds=self.online_grace_seconds,
        )
        raw_status = str(current.get("status") or "offline").lower()
        status = raw_status if current_fresh and raw_status in {"online", "error"} else "offline"

        serial_number = str(current.get("serial_number") or "").strip()
        identity_source = "controller_serial" if serial_number else "endpoint"
        if not serial_number and any(str(row.get("usb_serial") or "").strip() for row in ordered):
            identity_source = "usb_serial"

        connections: list[dict[str, object]] = []
        for index, row in enumerate(ordered):
            connection = _connection_payload(row)
            fresh = _is_fresh(
                row.get("last_seen"),
                now=now,
                grace_seconds=self.online_grace_seconds,
            )
            if index == 0:
                connection["role"] = "current"
                connection["status"] = (
                    str(row.get("status") or "offline").lower()
                    if fresh
                    else "offline"
                )
            else:
                connection["role"] = "previous"
                connection["status"] = "offline"
            connections.append(connection)

        first_seen_values = [str(row.get("first_seen") or "") for row in ordered if row.get("first_seen")]
        model = str(current.get("model") or current.get("product_code") or current.get("profile") or "")
        return {
            "controller_id": controller_id,
            "identity_source": identity_source,
            "current_device_id": current["id"],
            "status": status,
            "vendor_name": current.get("vendor_name") or "Morningstar",
            "product_code": current.get("product_code") or "",
            "profile": current.get("profile") or "",
            "family": current.get("family") or "",
            "model": model,
            "serial_number": serial_number,
            "firmware": current.get("firmware") or "",
            "hardware_revision": current.get("hardware_revision") or "",
            "confidence": current.get("confidence"),
            "first_seen": min(first_seen_values) if first_seen_values else None,
            "last_seen": current.get("last_seen"),
            "connection_count": len(ordered),
            "active_connection_count": 1 if status == "online" else 0,
            "current_connection": connections[0],
            "connections": connections,
        }

    async def _rows(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    d.*,
                    i.family,
                    i.model,
                    i.serial_number,
                    i.firmware,
                    i.hardware_revision,
                    i.confidence,
                    i.intelligence_status
                FROM devices d
                LEFT JOIN device_intelligence i ON i.device_id=d.id
                ORDER BY d.last_seen DESC
                """
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
