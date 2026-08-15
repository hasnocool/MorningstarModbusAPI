"""Persistent physical-controller identity and connection inventory."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from morningstar_modbus.models import DiscoveredDevice, Endpoint

ONLINE_GRACE_SECONDS = 120.0

_INVENTORY_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS controller_identities (
    controller_id TEXT PRIMARY KEY,
    canonical_device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    identity_source TEXT NOT NULL,
    identity_value TEXT NOT NULL,
    profile TEXT NOT NULL,
    family TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_controller_identities_canonical
    ON controller_identities(canonical_device_id);
CREATE TABLE IF NOT EXISTS controller_device_members (
    device_id TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    controller_id TEXT NOT NULL REFERENCES controller_identities(controller_id) ON DELETE CASCADE,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_controller_device_members_controller
    ON controller_device_members(controller_id, last_seen DESC);
CREATE TABLE IF NOT EXISTS controller_connections (
    controller_id TEXT NOT NULL REFERENCES controller_identities(controller_id) ON DELETE CASCADE,
    endpoint_key TEXT NOT NULL,
    transport TEXT NOT NULL,
    target TEXT NOT NULL,
    port INTEGER,
    unit_id INTEGER NOT NULL,
    usb_serial TEXT,
    usb_vid INTEGER,
    usb_pid INTEGER,
    active INTEGER NOT NULL DEFAULT 0,
    match_strategy TEXT NOT NULL DEFAULT 'legacy',
    match_confidence REAL NOT NULL DEFAULT 0.5,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_success TEXT,
    PRIMARY KEY(controller_id, endpoint_key)
);
CREATE INDEX IF NOT EXISTS idx_controller_connections_active
    ON controller_connections(controller_id, active, last_seen DESC);
CREATE TABLE IF NOT EXISTS controller_connection_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    controller_id TEXT NOT NULL REFERENCES controller_identities(controller_id) ON DELETE CASCADE,
    endpoint_key TEXT NOT NULL,
    transport TEXT NOT NULL,
    target TEXT NOT NULL,
    port INTEGER,
    unit_id INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    observations INTEGER NOT NULL DEFAULT 1,
    UNIQUE(controller_id, endpoint_key, transport, target, unit_id)
);
CREATE INDEX IF NOT EXISTS idx_controller_connection_locations_controller
    ON controller_connection_locations(controller_id, last_seen DESC);
CREATE TABLE IF NOT EXISTS controller_identity_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    controller_id TEXT NOT NULL REFERENCES controller_identities(controller_id) ON DELETE CASCADE,
    endpoint_key TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_value TEXT NOT NULL,
    confidence REAL NOT NULL,
    first_observed TEXT NOT NULL,
    last_observed TEXT NOT NULL,
    observations INTEGER NOT NULL DEFAULT 1,
    UNIQUE(controller_id, endpoint_key, evidence_type, evidence_value)
);
CREATE INDEX IF NOT EXISTS idx_controller_identity_evidence_controller
    ON controller_identity_evidence(controller_id, last_observed DESC);
"""


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


def _controller_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    serial = str(row.get("serial_number") or "").strip()
    profile = str(row.get("profile") or "").strip().lower()
    if serial:
        value = serial.lower()
        return f"morningstar:{profile}:{value}", "controller_serial", serial
    usb_serial = str(row.get("usb_serial") or "").strip()
    if usb_serial:
        unit_id = int(row.get("unit_id") or 0)
        value = f"{usb_serial.lower()}:unit:{unit_id}"
        return f"usb:{value}", "usb_serial", usb_serial
    stable_key = str(row["stable_key"])
    return f"endpoint:{stable_key}", "endpoint", stable_key


def _device_row(device: DiscoveredDevice) -> dict[str, Any]:
    endpoint = device.endpoint
    intelligence = device.intelligence
    return {
        "stable_key": endpoint.stable_key,
        "transport": endpoint.transport,
        "target": endpoint.target,
        "port": endpoint.port,
        "unit_id": endpoint.unit_id,
        "usb_serial": endpoint.usb_serial,
        "usb_vid": endpoint.usb_vid,
        "usb_pid": endpoint.usb_pid,
        "profile": device.profile,
        "family": intelligence.family if intelligence is not None else "",
        "model": intelligence.model if intelligence is not None else device.identification.product_code,
        "serial_number": intelligence.serial_number if intelligence is not None else "",
    }


def _conflict_device_id(device: DiscoveredDevice) -> str:
    intelligence = device.intelligence
    serial = intelligence.serial_number if intelligence is not None else ""
    material = f"{device.profile}\0{serial}\0{device.endpoint.stable_key}".encode()
    digest = hashlib.sha256(material).hexdigest()[:20]
    return f"device:{device.profile}:{digest}"


class ControllerInventoryRepository:
    """Persist physical-controller identity while retaining legacy endpoint IDs.

    Existing databases may contain several ``devices`` rows for one physical
    controller. Initialization groups those rows conservatively, keeps the
    most recently seen row as the canonical telemetry ID, and records the
    older IDs as history members. Future endpoint changes then reuse that
    canonical ID instead of creating another telemetry history.
    """

    def __init__(self, path: str, *, online_grace_seconds: float = ONLINE_GRACE_SECONDS) -> None:
        self.path = path
        self.online_grace_seconds = online_grace_seconds

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_INVENTORY_SCHEMA)
            count = await (await db.execute("SELECT COUNT(*) FROM controller_identities")).fetchone()
            if count is not None and int(count[0]) == 0:
                await self._bootstrap_legacy_rows(db)
            await db.commit()

    async def _bootstrap_legacy_rows(self, db: aiosqlite.Connection) -> None:
        db.row_factory = aiosqlite.Row
        rows = await self._rows_from_db(db)
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        identities: dict[str, tuple[str, str]] = {}
        for row in rows:
            controller_id, identity_source, identity_value = _controller_identity(row)
            groups[controller_id].append(row)
            identities[controller_id] = (identity_source, identity_value)

        now = datetime.now(UTC)
        for controller_id, group in groups.items():
            ordered = sorted(
                group,
                key=lambda row: (str(row.get("last_seen") or ""), str(row["id"])),
                reverse=True,
            )
            current = ordered[0]
            identity_source, identity_value = identities[controller_id]
            first_seen_values = [str(row.get("first_seen") or "") for row in ordered if row.get("first_seen")]
            first_seen = min(first_seen_values) if first_seen_values else str(current.get("last_seen") or "")
            await db.execute(
                """
                INSERT INTO controller_identities (
                    controller_id, canonical_device_id, identity_source, identity_value,
                    profile, family, model, serial_number, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(controller_id) DO UPDATE SET
                    identity_source=excluded.identity_source,
                    identity_value=excluded.identity_value,
                    profile=excluded.profile,
                    family=excluded.family,
                    model=excluded.model,
                    serial_number=excluded.serial_number,
                    first_seen=MIN(controller_identities.first_seen, excluded.first_seen),
                    last_seen=MAX(controller_identities.last_seen, excluded.last_seen)
                """,
                (
                    controller_id,
                    current["id"],
                    identity_source,
                    identity_value,
                    current.get("profile") or "",
                    current.get("family") or "",
                    current.get("model") or current.get("product_code") or "",
                    current.get("serial_number") or "",
                    first_seen,
                    current.get("last_seen") or first_seen,
                ),
            )
            for index, row in enumerate(ordered):
                await self._upsert_member(
                    db,
                    controller_id,
                    str(row["id"]),
                    str(row.get("first_seen") or first_seen),
                    str(row.get("last_seen") or first_seen),
                )
                raw_status = str(row.get("status") or "offline").lower()
                active = (
                    index == 0
                    and raw_status in {"online", "error"}
                    and _is_fresh(
                        row.get("last_seen"),
                        now=now,
                        grace_seconds=self.online_grace_seconds,
                    )
                )
                await self._upsert_connection_from_row(db, controller_id, row, active=active)

    async def register_observation(self, device: DiscoveredDevice) -> tuple[str, str]:
        """Return ``(controller_id, canonical_device_id)`` for one discovery observation."""
        await self.initialize()
        now = datetime.now(UTC).isoformat()
        row = _device_row(device)
        controller_id, identity_source, identity_value = _controller_identity(row)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            identity = await (
                await db.execute(
                    "SELECT * FROM controller_identities WHERE controller_id=?",
                    (controller_id,),
                )
            ).fetchone()
            endpoint_owner = await (
                await db.execute(
                    """
                    SELECT ci.*
                    FROM controller_connections cc
                    JOIN controller_identities ci ON ci.controller_id=cc.controller_id
                    WHERE cc.endpoint_key=?
                    ORDER BY cc.last_seen DESC
                    LIMIT 1
                    """,
                    (device.endpoint.stable_key,),
                )
            ).fetchone()
            serial = str(row.get("serial_number") or "").strip()

            if identity is not None:
                canonical_device_id = str(identity["canonical_device_id"])
                match_strategy = identity_source
                match_confidence = 1.0 if identity_source == "controller_serial" else 0.8
            elif endpoint_owner is not None:
                owner_serial = str(endpoint_owner["serial_number"] or "").strip()
                owner_controller_id = str(endpoint_owner["controller_id"])
                owner_device_id = str(endpoint_owner["canonical_device_id"])
                if serial and owner_serial and serial != owner_serial:
                    canonical_device_id = _conflict_device_id(device)
                    match_strategy = "controller_serial_conflict"
                    match_confidence = 0.95
                    await self._insert_new_identity(
                        db,
                        controller_id,
                        canonical_device_id,
                        identity_source,
                        identity_value,
                        device,
                        row,
                        now,
                    )
                elif serial and not owner_serial:
                    canonical_device_id = owner_device_id
                    await self._promote_identity(
                        db,
                        old_controller_id=owner_controller_id,
                        new_controller_id=controller_id,
                        canonical_device_id=canonical_device_id,
                        identity_source=identity_source,
                        identity_value=identity_value,
                        device=device,
                        row=row,
                        now=now,
                    )
                    match_strategy = "controller_serial_promotion"
                    match_confidence = 1.0
                else:
                    controller_id = owner_controller_id
                    canonical_device_id = owner_device_id
                    identity_source = str(endpoint_owner["identity_source"])
                    identity_value = str(endpoint_owner["identity_value"])
                    match_strategy = "known_endpoint_owner"
                    match_confidence = 0.95 if owner_serial else 0.65
            else:
                endpoint_row = await (
                    await db.execute(
                        "SELECT id FROM devices WHERE stable_key=?",
                        (device.endpoint.stable_key,),
                    )
                ).fetchone()
                canonical_device_id = (
                    str(endpoint_row["id"])
                    if endpoint_row is not None
                    else device.endpoint.stable_key
                )
                match_strategy = "new_controller"
                match_confidence = 0.4
                await self._insert_new_identity(
                    db,
                    controller_id,
                    canonical_device_id,
                    identity_source,
                    identity_value,
                    device,
                    row,
                    now,
                )

            await self._update_canonical_device(db, canonical_device_id, device, now)
            await self._upsert_member(db, controller_id, canonical_device_id, now, now)
            await self._upsert_connection(
                db,
                controller_id,
                device.endpoint,
                now,
                match_strategy=match_strategy,
                match_confidence=match_confidence,
            )
            await self._record_evidence(db, controller_id, device, now)
            await db.execute(
                """
                UPDATE controller_identities
                SET last_seen=?, profile=?, family=?, model=?,
                    serial_number=CASE WHEN ?!='' THEN ? ELSE serial_number END
                WHERE controller_id=?
                """,
                (
                    now,
                    device.profile,
                    row.get("family") or "",
                    row.get("model") or "",
                    serial,
                    serial,
                    controller_id,
                ),
            )
            await db.commit()
        return controller_id, canonical_device_id

    async def _insert_new_identity(
        self,
        db: aiosqlite.Connection,
        controller_id: str,
        canonical_device_id: str,
        identity_source: str,
        identity_value: str,
        device: DiscoveredDevice,
        row: dict[str, Any],
        now: str,
    ) -> None:
        await self._insert_canonical_device(db, canonical_device_id, device, now)
        await db.execute(
            """
            INSERT INTO controller_identities (
                controller_id, canonical_device_id, identity_source, identity_value,
                profile, family, model, serial_number, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                controller_id,
                canonical_device_id,
                identity_source,
                identity_value,
                device.profile,
                row.get("family") or "",
                row.get("model") or "",
                row.get("serial_number") or "",
                now,
                now,
            ),
        )

    async def _promote_identity(
        self,
        db: aiosqlite.Connection,
        *,
        old_controller_id: str,
        new_controller_id: str,
        canonical_device_id: str,
        identity_source: str,
        identity_value: str,
        device: DiscoveredDevice,
        row: dict[str, Any],
        now: str,
    ) -> None:
        old = await (
            await db.execute(
                "SELECT first_seen FROM controller_identities WHERE controller_id=?",
                (old_controller_id,),
            )
        ).fetchone()
        first_seen = str(old[0]) if old is not None else now
        await db.execute(
            """
            INSERT INTO controller_identities (
                controller_id, canonical_device_id, identity_source, identity_value,
                profile, family, model, serial_number, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_controller_id,
                canonical_device_id,
                identity_source,
                identity_value,
                device.profile,
                row.get("family") or "",
                row.get("model") or "",
                row.get("serial_number") or "",
                first_seen,
                now,
            ),
        )
        for table in (
            "controller_device_members",
            "controller_connections",
            "controller_connection_locations",
            "controller_identity_evidence",
        ):
            await db.execute(
                f"UPDATE {table} SET controller_id=? WHERE controller_id=?",
                (new_controller_id, old_controller_id),
            )
        await db.execute(
            "DELETE FROM controller_identities WHERE controller_id=?",
            (old_controller_id,),
        )

    async def reconcile_presence(self, observed: set[tuple[str, str]]) -> None:
        """Mark the selected/current connection from one complete discovery cycle."""
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE controller_connections SET active=0")
            for controller_id, endpoint_key in sorted(observed):
                await db.execute(
                    """
                    UPDATE controller_connections
                    SET active=1
                    WHERE controller_id=? AND endpoint_key=?
                    """,
                    (controller_id, endpoint_key),
                )
            await db.commit()

    async def record_success(self, controller_id: str, endpoint_key: str) -> None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE controller_connections
                SET active=1, last_seen=?, last_success=?
                WHERE controller_id=? AND endpoint_key=?
                """,
                (now, now, controller_id, endpoint_key),
            )
            await db.execute(
                "UPDATE controller_identities SET last_seen=? WHERE controller_id=?",
                (now, controller_id),
            )
            await db.commit()

    async def mark_all_offline(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE devices SET status='offline' WHERE status IN ('online', 'error')")
            await db.execute("UPDATE controller_connections SET active=0")
            await db.commit()

    async def mark_device_offline(self, device_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE devices SET status='offline' WHERE id=?", (device_id,))
            await db.commit()

    async def list_controllers(self) -> list[dict[str, object]]:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            identities = await (
                await db.execute(
                    """
                    SELECT ci.*, d.status, d.vendor_name, d.product_code, d.last_error,
                           d.last_seen AS device_last_seen, d.first_seen AS device_first_seen,
                           di.firmware, di.hardware_revision, di.confidence, di.intelligence_status
                    FROM controller_identities ci
                    JOIN devices d ON d.id=ci.canonical_device_id
                    LEFT JOIN device_intelligence di ON di.device_id=ci.canonical_device_id
                    ORDER BY ci.last_seen DESC
                    """
                )
            ).fetchall()
            return [await self._identity_payload(db, dict(row)) for row in identities]

    async def get_controller(self, controller_id: str) -> dict[str, object] | None:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    """
                    SELECT ci.*, d.status, d.vendor_name, d.product_code, d.last_error,
                           d.last_seen AS device_last_seen, d.first_seen AS device_first_seen,
                           di.firmware, di.hardware_revision, di.confidence, di.intelligence_status
                    FROM controller_identities ci
                    JOIN devices d ON d.id=ci.canonical_device_id
                    LEFT JOIN device_intelligence di ON di.device_id=ci.canonical_device_id
                    WHERE ci.controller_id=?
                    """,
                    (controller_id,),
                )
            ).fetchone()
            return await self._identity_payload(db, dict(row)) if row is not None else None

    async def _identity_payload(
        self,
        db: aiosqlite.Connection,
        identity: dict[str, Any],
    ) -> dict[str, object]:
        controller_id = str(identity["controller_id"])
        member_rows = await (
            await db.execute(
                """
                SELECT device_id, first_seen, last_seen
                FROM controller_device_members
                WHERE controller_id=?
                ORDER BY last_seen DESC, device_id
                """,
                (controller_id,),
            )
        ).fetchall()
        members = [str(row[0]) for row in member_rows]
        connection_rows = await (
            await db.execute(
                """
                SELECT endpoint_key, transport, target, port, unit_id,
                       first_seen, last_seen, observations
                FROM controller_connection_locations
                WHERE controller_id=?
                ORDER BY last_seen DESC, id DESC
                """,
                (controller_id,),
            )
        ).fetchall()
        active_rows = await (
            await db.execute(
                """
                SELECT endpoint_key, target
                FROM controller_connections
                WHERE controller_id=? AND active=1
                ORDER BY last_seen DESC
                """,
                (controller_id,),
            )
        ).fetchall()
        active_locations = {(str(row[0]), str(row[1])) for row in active_rows}

        connections: list[dict[str, object]] = []
        for row in connection_rows:
            endpoint_key = str(row[0])
            target = str(row[2])
            active = (endpoint_key, target) in active_locations
            connections.append(
                {
                    "device_id": identity["canonical_device_id"],
                    "stable_key": endpoint_key,
                    "transport": row[1],
                    "target": target,
                    "port": row[3],
                    "unit_id": row[4],
                    "status": "online" if active else "offline",
                    "role": "current" if active else "previous",
                    "first_seen": row[5],
                    "last_seen": row[6],
                    "observations": row[7],
                }
            )

        now = datetime.now(UTC)
        current_fresh = _is_fresh(
            identity.get("device_last_seen"),
            now=now,
            grace_seconds=self.online_grace_seconds,
        )
        raw_status = str(identity.get("status") or "offline").lower()
        status = raw_status if current_fresh and raw_status in {"online", "error"} else "offline"
        if not active_locations:
            status = "offline"
        for connection in connections:
            if connection["role"] == "current":
                connection["status"] = status

        first_seen_values = [str(row[1]) for row in member_rows if row[1]]
        return {
            "controller_id": controller_id,
            "identity_source": identity["identity_source"],
            "identity_value": identity["identity_value"],
            "canonical_device_id": identity["canonical_device_id"],
            "current_device_id": identity["canonical_device_id"],
            "history_device_ids": members,
            "status": status,
            "vendor_name": identity.get("vendor_name") or "Morningstar",
            "product_code": identity.get("product_code") or "",
            "profile": identity.get("profile") or "",
            "family": identity.get("family") or "",
            "model": identity.get("model") or identity.get("product_code") or "",
            "serial_number": identity.get("serial_number") or "",
            "firmware": identity.get("firmware") or "",
            "hardware_revision": identity.get("hardware_revision") or "",
            "confidence": identity.get("confidence"),
            "first_seen": min(first_seen_values) if first_seen_values else identity.get("first_seen"),
            "last_seen": identity.get("last_seen"),
            "connection_count": len(connections),
            "active_connection_count": len(active_locations),
            "current_connection": next(
                (item for item in connections if item["role"] == "current"),
                connections[0] if connections else None,
            ),
            "connections": connections,
        }

    @staticmethod
    async def _upsert_member(
        db: aiosqlite.Connection,
        controller_id: str,
        device_id: str,
        first_seen: str,
        last_seen: str,
    ) -> None:
        await db.execute(
            """
            INSERT INTO controller_device_members(device_id, controller_id, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                controller_id=excluded.controller_id,
                first_seen=MIN(controller_device_members.first_seen, excluded.first_seen),
                last_seen=MAX(controller_device_members.last_seen, excluded.last_seen)
            """,
            (device_id, controller_id, first_seen, last_seen),
        )

    @staticmethod
    async def _upsert_connection_from_row(
        db: aiosqlite.Connection,
        controller_id: str,
        row: dict[str, Any],
        *,
        active: bool,
    ) -> None:
        endpoint = Endpoint(
            transport="tcp" if row["transport"] == "tcp" else "serial",
            target=str(row["target"]),
            unit_id=int(row["unit_id"]),
            port=int(row["port"]) if row.get("port") is not None else None,
            usb_serial=str(row["usb_serial"]) if row.get("usb_serial") else None,
            usb_vid=int(row["usb_vid"]) if row.get("usb_vid") is not None else None,
            usb_pid=int(row["usb_pid"]) if row.get("usb_pid") is not None else None,
        )
        await ControllerInventoryRepository._upsert_connection(
            db,
            controller_id,
            endpoint,
            str(row.get("last_seen") or row.get("first_seen") or datetime.now(UTC).isoformat()),
            match_strategy="legacy",
            match_confidence=0.5,
            first_seen=str(row.get("first_seen") or row.get("last_seen") or datetime.now(UTC).isoformat()),
            active=active,
        )

    @staticmethod
    async def _upsert_connection(
        db: aiosqlite.Connection,
        controller_id: str,
        endpoint: Endpoint,
        now: str,
        *,
        match_strategy: str,
        match_confidence: float,
        first_seen: str | None = None,
        active: bool = True,
    ) -> None:
        await db.execute(
            """
            INSERT INTO controller_connections (
                controller_id, endpoint_key, transport, target, port, unit_id,
                usb_serial, usb_vid, usb_pid, active, match_strategy,
                match_confidence, first_seen, last_seen, last_success
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(controller_id, endpoint_key) DO UPDATE SET
                transport=excluded.transport,
                target=excluded.target,
                port=excluded.port,
                unit_id=excluded.unit_id,
                usb_serial=excluded.usb_serial,
                usb_vid=excluded.usb_vid,
                usb_pid=excluded.usb_pid,
                active=excluded.active,
                match_strategy=excluded.match_strategy,
                match_confidence=MAX(controller_connections.match_confidence, excluded.match_confidence),
                first_seen=MIN(controller_connections.first_seen, excluded.first_seen),
                last_seen=MAX(controller_connections.last_seen, excluded.last_seen)
            """,
            (
                controller_id,
                endpoint.stable_key,
                endpoint.transport,
                endpoint.target,
                endpoint.port,
                endpoint.unit_id,
                endpoint.usb_serial,
                endpoint.usb_vid,
                endpoint.usb_pid,
                int(active),
                match_strategy,
                match_confidence,
                first_seen or now,
                now,
            ),
        )
        await db.execute(
            """
            INSERT INTO controller_connection_locations (
                controller_id, endpoint_key, transport, target, port, unit_id,
                first_seen, last_seen, observations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(controller_id, endpoint_key, transport, target, unit_id) DO UPDATE SET
                port=excluded.port,
                first_seen=MIN(controller_connection_locations.first_seen, excluded.first_seen),
                last_seen=MAX(controller_connection_locations.last_seen, excluded.last_seen),
                observations=controller_connection_locations.observations + 1
            """,
            (
                controller_id,
                endpoint.stable_key,
                endpoint.transport,
                endpoint.target,
                endpoint.port,
                endpoint.unit_id,
                first_seen or now,
                now,
            ),
        )

    @staticmethod
    async def _insert_canonical_device(
        db: aiosqlite.Connection,
        device_id: str,
        device: DiscoveredDevice,
        now: str,
    ) -> None:
        endpoint = device.endpoint
        stable_key = endpoint.stable_key
        occupied = await (
            await db.execute("SELECT id FROM devices WHERE stable_key=?", (stable_key,))
        ).fetchone()
        if occupied is not None and str(occupied[0]) != device_id:
            stable_key = device_id
        await db.execute(
            """
            INSERT OR IGNORE INTO devices (
                id, stable_key, transport, target, port, unit_id, usb_serial, usb_vid, usb_pid,
                vendor_name, product_code, revision, profile, status, first_seen, last_seen, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'online', ?, ?, NULL)
            """,
            (
                device_id,
                stable_key,
                endpoint.transport,
                endpoint.target,
                endpoint.port,
                endpoint.unit_id,
                endpoint.usb_serial,
                endpoint.usb_vid,
                endpoint.usb_pid,
                device.identification.vendor_name,
                device.identification.product_code,
                device.identification.major_minor_revision,
                device.profile,
                now,
                now,
            ),
        )

    @staticmethod
    async def _update_canonical_device(
        db: aiosqlite.Connection,
        device_id: str,
        device: DiscoveredDevice,
        now: str,
    ) -> None:
        endpoint = device.endpoint
        await db.execute(
            """
            UPDATE devices
            SET transport=?, target=?, port=?, unit_id=?, usb_serial=?, usb_vid=?, usb_pid=?,
                vendor_name=?, product_code=?, revision=?, profile=?, status='online',
                last_seen=?, last_error=NULL
            WHERE id=?
            """,
            (
                endpoint.transport,
                endpoint.target,
                endpoint.port,
                endpoint.unit_id,
                endpoint.usb_serial,
                endpoint.usb_vid,
                endpoint.usb_pid,
                device.identification.vendor_name,
                device.identification.product_code,
                device.identification.major_minor_revision,
                device.profile,
                now,
                device_id,
            ),
        )

    @staticmethod
    async def _record_evidence(
        db: aiosqlite.Connection,
        controller_id: str,
        device: DiscoveredDevice,
        now: str,
    ) -> None:
        endpoint = device.endpoint
        evidence: list[tuple[str, str, float]] = [("endpoint", endpoint.stable_key, 0.50)]
        if endpoint.usb_serial:
            evidence.append(("usb_serial", endpoint.usb_serial, 0.80))
        if device.identification.product_code:
            evidence.append(("product_code", device.identification.product_code, 0.35))
        intelligence = device.intelligence
        if intelligence is not None:
            if intelligence.serial_number:
                evidence.append(("controller_serial", intelligence.serial_number, 1.0))
            if intelligence.model:
                evidence.append(("model", intelligence.model, 0.40))
        for evidence_type, value, confidence in evidence:
            await db.execute(
                """
                INSERT INTO controller_identity_evidence (
                    controller_id, endpoint_key, evidence_type, evidence_value,
                    confidence, first_observed, last_observed, observations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(controller_id, endpoint_key, evidence_type, evidence_value) DO UPDATE SET
                    confidence=MAX(controller_identity_evidence.confidence, excluded.confidence),
                    last_observed=excluded.last_observed,
                    observations=controller_identity_evidence.observations + 1
                """,
                (
                    controller_id,
                    endpoint.stable_key,
                    evidence_type,
                    value,
                    confidence,
                    now,
                    now,
                ),
            )

    async def _rows(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await self._rows_from_db(db)
        return rows

    @staticmethod
    async def _rows_from_db(db: aiosqlite.Connection) -> list[dict[str, Any]]:
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
