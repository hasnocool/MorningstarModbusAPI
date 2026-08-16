"""Immutable physical-controller identity and scope resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite

from morningstar_modbus.controllers.inventory import ControllerInventoryRepository
from morningstar_modbus.domain.models import DiscoveredDevice

_SCOPE_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS physical_controllers (
    controller_uid TEXT PRIMARY KEY,
    canonical_device_id TEXT NOT NULL UNIQUE REFERENCES devices(id) ON DELETE CASCADE,
    current_controller_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_physical_controllers_current_identity
    ON physical_controllers(current_controller_id);
CREATE TABLE IF NOT EXISTS controller_identity_aliases (
    controller_id TEXT PRIMARY KEY,
    controller_uid TEXT NOT NULL REFERENCES physical_controllers(controller_uid) ON DELETE CASCADE,
    identity_source TEXT NOT NULL,
    identity_value TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_controller_identity_aliases_uid
    ON controller_identity_aliases(controller_uid, active, last_seen DESC);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_uid() -> str:
    return f"ctrl_{uuid4().hex}"


@dataclass(frozen=True)
class ControllerScope:
    """Stable physical-controller identity plus all telemetry-owning device IDs."""

    controller_uid: str
    controller_id: str
    canonical_device_id: str
    history_device_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "controller_uid": self.controller_uid,
            "controller_id": self.controller_id,
            "canonical_device_id": self.canonical_device_id,
            "history_device_ids": list(self.history_device_ids),
        }


class ControllerScopeRepository:
    """Assign immutable controller UIDs to the evidence-derived identity layer.

    ``controller_id`` remains a compatibility alias and may change when stronger
    identity evidence appears. ``controller_uid`` is generated once, persisted,
    and reused across those promotions by matching the canonical telemetry ID.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_SCOPE_SCHEMA)
            await self._sync_current_identities(db)
            await db.commit()

    async def sync(self) -> None:
        await self.initialize()

    async def _sync_current_identities(self, db: aiosqlite.Connection) -> None:
        db.row_factory = aiosqlite.Row
        rows = await (
            await db.execute(
                """
                SELECT controller_id, canonical_device_id, identity_source, identity_value,
                       first_seen, last_seen
                FROM controller_identities
                ORDER BY last_seen, controller_id
                """
            )
        ).fetchall()
        for row in rows:
            controller_id = str(row["controller_id"])
            canonical_device_id = str(row["canonical_device_id"])
            alias = await (
                await db.execute(
                    "SELECT controller_uid FROM controller_identity_aliases WHERE controller_id=?",
                    (controller_id,),
                )
            ).fetchone()
            physical = await (
                await db.execute(
                    """
                    SELECT controller_uid, first_seen
                    FROM physical_controllers
                    WHERE canonical_device_id=?
                    """,
                    (canonical_device_id,),
                )
            ).fetchone()

            if alias is not None:
                controller_uid = str(alias["controller_uid"])
            elif physical is not None:
                controller_uid = str(physical["controller_uid"])
            else:
                controller_uid = _new_uid()

            first_seen = str(row["first_seen"] or _now())
            last_seen = str(row["last_seen"] or first_seen)
            await db.execute(
                """
                INSERT INTO physical_controllers(
                    controller_uid, canonical_device_id, current_controller_id, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(controller_uid) DO UPDATE SET
                    canonical_device_id=excluded.canonical_device_id,
                    current_controller_id=excluded.current_controller_id,
                    first_seen=MIN(physical_controllers.first_seen, excluded.first_seen),
                    last_seen=MAX(physical_controllers.last_seen, excluded.last_seen)
                """,
                (controller_uid, canonical_device_id, controller_id, first_seen, last_seen),
            )
            await db.execute(
                "UPDATE controller_identity_aliases SET active=0 WHERE controller_uid=?",
                (controller_uid,),
            )
            await db.execute(
                """
                INSERT INTO controller_identity_aliases(
                    controller_id, controller_uid, identity_source, identity_value,
                    first_seen, last_seen, active
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(controller_id) DO UPDATE SET
                    controller_uid=excluded.controller_uid,
                    identity_source=excluded.identity_source,
                    identity_value=excluded.identity_value,
                    first_seen=MIN(controller_identity_aliases.first_seen, excluded.first_seen),
                    last_seen=MAX(controller_identity_aliases.last_seen, excluded.last_seen),
                    active=1
                """,
                (
                    controller_id,
                    controller_uid,
                    str(row["identity_source"]),
                    str(row["identity_value"]),
                    first_seen,
                    last_seen,
                ),
            )

    async def resolve(self, identifier: str) -> ControllerScope | None:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            physical = await (
                await db.execute(
                    "SELECT * FROM physical_controllers WHERE controller_uid=?",
                    (identifier,),
                )
            ).fetchone()
            if physical is None:
                alias = await (
                    await db.execute(
                        """
                        SELECT pc.*
                        FROM controller_identity_aliases a
                        JOIN physical_controllers pc ON pc.controller_uid=a.controller_uid
                        WHERE a.controller_id=?
                        """,
                        (identifier,),
                    )
                ).fetchone()
                physical = alias
            if physical is None:
                return None

            controller_uid = str(physical["controller_uid"])
            current_controller_id = str(physical["current_controller_id"])
            members = await (
                await db.execute(
                    """
                    SELECT device_id
                    FROM controller_device_members
                    WHERE controller_id=?
                    ORDER BY last_seen, device_id
                    """,
                    (current_controller_id,),
                )
            ).fetchall()
            history_device_ids = tuple(str(row[0]) for row in members)
            canonical_device_id = str(physical["canonical_device_id"])
            if canonical_device_id not in history_device_ids:
                history_device_ids = (*history_device_ids, canonical_device_id)
            return ControllerScope(
                controller_uid=controller_uid,
                controller_id=current_controller_id,
                canonical_device_id=canonical_device_id,
                history_device_ids=tuple(dict.fromkeys(history_device_ids)),
            )

    async def list_scopes(self) -> list[ControllerScope]:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            rows = await (
                await db.execute(
                    "SELECT controller_uid FROM physical_controllers ORDER BY last_seen DESC"
                )
            ).fetchall()
        scopes: list[ControllerScope] = []
        for row in rows:
            scope = await self.resolve(str(row[0]))
            if scope is not None:
                scopes.append(scope)
        return scopes


class ControllerRegistry:
    """Facade joining mutable identity evidence to immutable controller UIDs."""

    def __init__(self, path: str, *, online_grace_seconds: float = 120.0) -> None:
        self.inventory = ControllerInventoryRepository(
            path,
            online_grace_seconds=online_grace_seconds,
        )
        self.scopes = ControllerScopeRepository(path)

    async def initialize(self) -> None:
        await self.inventory.initialize()
        await self.scopes.initialize()

    async def register_observation(self, device: DiscoveredDevice) -> tuple[str, str]:
        # Sync before registration so a fallback identity is retained as an alias
        # if this observation promotes it to a stronger controller serial identity.
        await self.initialize()
        controller_id, device_id = await self.inventory.register_observation(device)
        await self.scopes.sync()
        scope = await self.scopes.resolve(controller_id)
        if scope is None:
            raise RuntimeError(f"controller scope missing after registration: {controller_id}")
        return scope.controller_uid, device_id

    async def resolve(self, identifier: str) -> ControllerScope | None:
        return await self.scopes.resolve(identifier)

    async def list_controllers(self) -> list[dict[str, object]]:
        await self.initialize()
        records = await self.inventory.list_controllers()
        output: list[dict[str, object]] = []
        for record in records:
            controller_id = str(record["controller_id"])
            scope = await self.scopes.resolve(controller_id)
            if scope is None:
                continue
            item = dict(record)
            item.update(scope.to_dict())
            output.append(item)
        return output

    async def get_controller(self, identifier: str) -> dict[str, object] | None:
        scope = await self.scopes.resolve(identifier)
        if scope is None:
            return None
        record = await self.inventory.get_controller(scope.controller_id)
        if record is None:
            return None
        item = dict(record)
        item.update(scope.to_dict())
        return item

    async def reconcile_presence(self, observed: set[tuple[str, str]]) -> None:
        translated: set[tuple[str, str]] = set()
        for controller_uid, endpoint_key in observed:
            scope = await self.scopes.resolve(controller_uid)
            if scope is not None:
                translated.add((scope.controller_id, endpoint_key))
        await self.inventory.reconcile_presence(translated)

    async def record_success(self, controller_uid: str, endpoint_key: str) -> None:
        scope = await self.scopes.resolve(controller_uid)
        if scope is None:
            return
        await self.inventory.record_success(scope.controller_id, endpoint_key)
        await self.scopes.sync()

    async def mark_all_offline(self) -> None:
        await self.inventory.mark_all_offline()

    async def mark_device_offline(self, device_id: str) -> None:
        await self.inventory.mark_device_offline(device_id)
