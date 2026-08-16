# src/morningstar_modbus/system_data.py
"""Persistent system/site read model over immutable physical-controller data."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from statistics import median

import aiosqlite

from morningstar_modbus.catalog import get_profile
from morningstar_modbus.history.controller_data import ControllerDataRepository
from morningstar_modbus.persistence.events import EventStore
from morningstar_modbus.systems.semantics import SYSTEM_METRICS, SystemMetricSpec, metric_spec

DEFAULT_SYSTEM_UID = "sys_default"
DEFAULT_SYSTEM_NAME = "default"

_SYSTEM_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS systems (
    system_uid TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    auto_discover INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS system_members (
    system_uid TEXT NOT NULL REFERENCES systems(system_uid) ON DELETE CASCADE,
    controller_uid TEXT NOT NULL REFERENCES physical_controllers(controller_uid) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    PRIMARY KEY(system_uid, controller_uid)
);
CREATE INDEX IF NOT EXISTS idx_system_members_controller
    ON system_members(controller_uid, system_uid);
"""

_RESOLUTION_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
}


class SystemNotFoundError(LookupError):
    """Raised when a system UID/name cannot be resolved."""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


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


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _state_clear(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) == 0.0
    normalized = str(value).strip().lower()
    return normalized in {"", "0", "0.0", "[]", "{}", "none", "clear", "normal", "ok"}


def _bucket_start(value: str, seconds: int) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return value
    epoch = int(parsed.timestamp())
    bucket = epoch - (epoch % seconds)
    return datetime.fromtimestamp(bucket, UTC).isoformat()


class SystemDataRepository:
    """Aggregate controller data into one persistent read-only site/system view."""

    def __init__(
        self,
        path: str,
        *,
        default_system_uid: str = DEFAULT_SYSTEM_UID,
        default_system_name: str = DEFAULT_SYSTEM_NAME,
    ) -> None:
        self.path = path
        self.default_system_uid = default_system_uid
        self.default_system_name = default_system_name
        self.controllers_data = ControllerDataRepository(path)
        self.events_store = EventStore(path)

    async def initialize(self) -> None:
        await self.controllers_data.initialize()
        await self.events_store.initialize()
        now = _utcnow()
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_SYSTEM_SCHEMA)
            await db.execute(
                """
                INSERT INTO systems(
                    system_uid, name, description, auto_discover, created_at, updated_at
                ) VALUES (
                    ?, ?, 'Automatically groups all discovered physical Morningstar controllers.',
                    1, ?, ?
                )
                ON CONFLICT(system_uid) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (self.default_system_uid, self.default_system_name, now, now),
            )
            await db.commit()
        await self.sync_memberships()

    async def sync_memberships(self) -> None:
        controllers = await self.controllers_data.list_controllers()
        if not controllers:
            return
        now = _utcnow()
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO system_members(system_uid, controller_uid, role, added_at)
                VALUES (?, ?, '', ?)
                ON CONFLICT(system_uid, controller_uid) DO NOTHING
                """,
                [
                    (self.default_system_uid, str(controller["controller_uid"]), now)
                    for controller in controllers
                ],
            )
            await db.commit()

    async def _resolve_uid(self, identifier: str) -> str:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            row = await (
                await db.execute(
                    "SELECT system_uid FROM systems WHERE system_uid=? OR name=? LIMIT 1",
                    (identifier, identifier),
                )
            ).fetchone()
        if row is None:
            raise SystemNotFoundError(identifier)
        return str(row[0])

    async def list_systems(self) -> list[dict[str, object]]:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    """
                    SELECT s.*, COUNT(sm.controller_uid) AS controller_count
                    FROM systems s
                    LEFT JOIN system_members sm ON sm.system_uid=s.system_uid
                    GROUP BY s.system_uid
                    ORDER BY s.name
                    """
                )
            ).fetchall()
        return [dict(row) for row in rows]

    async def system(self, identifier: str) -> dict[str, object]:
        system_uid = await self._resolve_uid(identifier)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    """
                    SELECT s.*, COUNT(sm.controller_uid) AS controller_count
                    FROM systems s
                    LEFT JOIN system_members sm ON sm.system_uid=s.system_uid
                    WHERE s.system_uid=?
                    GROUP BY s.system_uid
                    """,
                    (system_uid,),
                )
            ).fetchone()
        if row is None:
            raise SystemNotFoundError(identifier)
        return dict(row)

    async def controllers(self, identifier: str) -> list[dict[str, object]]:
        system_uid = await self._resolve_uid(identifier)
        all_controllers = await self.controllers_data.list_controllers()
        async with aiosqlite.connect(self.path) as db:
            rows = await (
                await db.execute(
                    "SELECT controller_uid, role, added_at FROM system_members WHERE system_uid=?",
                    (system_uid,),
                )
            ).fetchall()
        memberships = {
            str(uid): {"role": role, "added_at": added_at}
            for uid, role, added_at in rows
        }
        output: list[dict[str, object]] = []
        for controller in all_controllers:
            uid = str(controller["controller_uid"])
            membership = memberships.get(uid)
            if membership is None:
                continue
            item = dict(controller)
            item["system_role"] = membership["role"]
            item["system_added_at"] = membership["added_at"]
            output.append(item)
        return output

    @staticmethod
    def _eligible_controller_uids(
        controllers: list[dict[str, object]],
        spec: SystemMetricSpec,
    ) -> set[str]:
        eligible: set[str] = set()
        aliases = set(spec.registers)
        for controller in controllers:
            profile_name = str(controller.get("profile") or "")
            profile = get_profile(profile_name)
            if aliases.intersection(profile.spec.register_names):
                eligible.add(str(controller["controller_uid"]))
        return eligible

    @staticmethod
    def _select_value(
        sample: dict[str, object],
        spec: SystemMetricSpec,
    ) -> dict[str, object] | None:
        by_name = {
            str(value.get("register_name")): value
            for value in sample.get("values", [])
            if isinstance(value, dict)
        }
        for register_name in spec.registers:
            value = by_name.get(register_name)
            if value is None:
                continue
            decoded = value.get("value")
            if decoded is None:
                continue
            return {
                "register_name": register_name,
                "value": decoded,
                "unit": value.get("unit") or spec.unit,
            }
        return None

    @staticmethod
    def _aggregate_observations(
        spec: SystemMetricSpec,
        observations: list[dict[str, object]],
        expected_controller_uids: set[str],
    ) -> dict[str, object]:
        contributor_uids = {str(item["controller_uid"]) for item in observations}
        expected = len(expected_controller_uids)
        contributors = len(contributor_uids)
        if contributors == 0:
            quality = "empty"
        elif expected == 0 or contributors >= expected:
            quality = "complete"
        else:
            quality = "partial"

        value: object = None
        if spec.aggregation == "state_set":
            states: list[str] = []
            for item in observations:
                text = str(item["value"])
                if text not in states:
                    states.append(text)
            value = states
        else:
            numeric = [
                parsed
                for item in observations
                if (parsed := _numeric(item.get("value"))) is not None
            ]
            if numeric:
                if spec.aggregation == "sum":
                    value = sum(numeric)
                elif spec.aggregation == "median":
                    value = median(numeric)
                elif spec.aggregation == "max":
                    value = max(numeric)
                elif spec.aggregation == "min":
                    value = min(numeric)
                else:
                    latest = max(
                        observations,
                        key=lambda item: str(item.get("observed_at") or ""),
                    )
                    value = latest.get("value")

        ages = [
            max(0.0, (datetime.now(UTC) - parsed).total_seconds() * 1000.0)
            for item in observations
            if (parsed := _parse_time(item.get("observed_at"))) is not None
        ]
        return {
            "value": value,
            "unit": spec.unit,
            "aggregation": spec.aggregation,
            "quality": quality,
            "contributors": contributors,
            "expected_contributors": expected,
            "oldest_observation_age_ms": max(ages) if ages else None,
            "sources": observations,
        }

    async def latest(self, identifier: str) -> dict[str, object]:
        system = await self.system(identifier)
        controllers = await self.controllers(str(system["system_uid"]))
        samples = await asyncio.gather(
            *(
                self.controllers_data.latest(str(controller["controller_uid"]))
                for controller in controllers
            )
        )
        metrics: dict[str, object] = {}
        for spec in SYSTEM_METRICS:
            observations: list[dict[str, object]] = []
            for controller, sample in zip(controllers, samples, strict=True):
                if sample is None:
                    continue
                selected = self._select_value(sample, spec)
                if selected is None:
                    continue
                observations.append(
                    {
                        "controller_uid": controller["controller_uid"],
                        "observed_at": sample.get("observed_at"),
                        **selected,
                    }
                )
            metrics[spec.name] = self._aggregate_observations(
                spec,
                observations,
                self._eligible_controller_uids(controllers, spec),
            )
        timestamps = [
            str(sample.get("observed_at"))
            for sample in samples
            if sample is not None and sample.get("observed_at")
        ]
        return {
            "system_uid": system["system_uid"],
            "name": system["name"],
            "observed_at": max(timestamps) if timestamps else None,
            "controller_count": len(controllers),
            "metrics": metrics,
        }

    async def energy(self, identifier: str) -> dict[str, object]:
        latest = await self.latest(identifier)
        names = ("daily_charge_wh", "daily_charge_ah", "lifetime_charge_kwh")
        return {
            "system_uid": latest["system_uid"],
            "observed_at": latest["observed_at"],
            "metrics": {name: latest["metrics"][name] for name in names},
        }

    async def health(self, identifier: str) -> dict[str, object]:
        latest = await self.latest(identifier)
        controllers = await self.controllers(str(latest["system_uid"]))
        status_counts: dict[str, int] = defaultdict(int)
        for controller in controllers:
            status_counts[str(controller.get("status") or "unknown")] += 1
        faults = dict(latest["metrics"]["faults"])
        alarms = dict(latest["metrics"]["alarms"])
        active_faults = sum(
            1
            for source in faults.get("sources", [])
            if not _state_clear(source.get("value"))
        )
        active_alarms = sum(
            1
            for source in alarms.get("sources", [])
            if not _state_clear(source.get("value"))
        )
        offline = sum(
            count
            for state, count in status_counts.items()
            if state != "online"
        )
        if active_faults:
            overall = "critical"
        elif active_alarms or offline:
            overall = "warning"
        else:
            overall = "ok"
        return {
            "system_uid": latest["system_uid"],
            "status": overall,
            "controllers": dict(status_counts),
            "active_fault_controllers": active_faults,
            "active_alarm_controllers": active_alarms,
            "faults": faults,
            "alarms": alarms,
            "charge_state": latest["metrics"]["charge_state"],
        }

    async def _scope_map(
        self,
        identifier: str,
    ) -> tuple[str, dict[str, str], list[dict[str, object]]]:
        system_uid = await self._resolve_uid(identifier)
        controllers = await self.controllers(system_uid)
        mapping: dict[str, str] = {}
        for controller in controllers:
            uid = str(controller["controller_uid"])
            scope = await self.controllers_data.scope(uid)
            for device_id in scope.history_device_ids:
                mapping[device_id] = uid
        return system_uid, mapping, controllers

    async def history(
        self,
        identifier: str,
        metric_name: str,
        *,
        start: str | None,
        end: str | None,
        resolution: str,
        max_points: int = 20_000,
    ) -> dict[str, object]:
        spec = metric_spec(metric_name)
        if spec is None:
            raise ValueError(f"unknown system metric: {metric_name}")
        normalized_resolution = resolution.strip().lower()
        if (
            normalized_resolution != "raw"
            and normalized_resolution not in _RESOLUTION_SECONDS
        ):
            raise ValueError("resolution must be raw, 1m, 5m, 15m, 1h, or 1d")
        system_uid, device_to_controller, controllers = await self._scope_map(identifier)
        if not device_to_controller:
            return {
                "system_uid": system_uid,
                "metric": spec.to_dict(),
                "resolution": normalized_resolution,
                "points": [],
            }
        aliases = spec.registers
        device_ids = tuple(device_to_controller)
        device_placeholders = ",".join("?" for _ in device_ids)
        alias_placeholders = ",".join("?" for _ in aliases)
        clauses = [
            f"s.device_id IN ({device_placeholders})",
            f"v.register_name IN ({alias_placeholders})",
        ]
        params: list[object] = [*device_ids, *aliases]
        if start is not None:
            clauses.append("s.observed_at>=?")
            params.append(start)
        if end is not None:
            clauses.append("s.observed_at<?")
            params.append(end)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    f"""
                    SELECT s.device_id, s.observed_at, v.register_name,
                           v.numeric_value, v.text_value, v.unit
                    FROM register_values v
                    JOIN poll_samples s ON s.id=v.sample_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY s.observed_at ASC, s.id ASC
                    LIMIT ?
                    """,
                    (*params, max_points + 1),
                )
            ).fetchall()
        if len(rows) > max_points:
            raise ValueError(
                f"query exceeds {max_points} source observations; "
                "narrow the range or use a coarser window"
            )
        priority = {name: index for index, name in enumerate(aliases)}
        chosen: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            device_id = str(row["device_id"])
            controller_uid = device_to_controller.get(device_id)
            if controller_uid is None:
                continue
            if row["numeric_value"] is not None:
                value: object = row["numeric_value"]
            else:
                value = row["text_value"]
            item = {
                "controller_uid": controller_uid,
                "source_device_id": device_id,
                "observed_at": str(row["observed_at"]),
                "register_name": str(row["register_name"]),
                "value": value,
                "unit": row["unit"] or spec.unit,
            }
            key = (controller_uid, str(row["observed_at"]))
            previous = chosen.get(key)
            current_name = str(item["register_name"])
            if previous is None:
                chosen[key] = item
                continue
            previous_name = str(previous["register_name"])
            if priority[current_name] < priority[previous_name]:
                chosen[key] = item
        observations = sorted(
            chosen.values(),
            key=lambda item: str(item["observed_at"]),
        )
        if normalized_resolution == "raw":
            points: list[dict[str, object]] = observations
        else:
            seconds = _RESOLUTION_SECONDS[normalized_resolution]
            buckets: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
            for item in observations:
                bucket = _bucket_start(str(item["observed_at"]), seconds)
                buckets[bucket][str(item["controller_uid"])] = item
            expected = self._eligible_controller_uids(controllers, spec)
            points = []
            for bucket in sorted(buckets):
                sources = list(buckets[bucket].values())
                aggregate = self._aggregate_observations(spec, sources, expected)
                aggregate["bucket_start"] = bucket
                points.append(aggregate)
        return {
            "system_uid": system_uid,
            "metric": spec.to_dict(),
            "from": start,
            "to": end,
            "resolution": normalized_resolution,
            "points": points,
        }

    async def topology(self, identifier: str) -> dict[str, object]:
        system_uid = await self._resolve_uid(identifier)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    """
                    SELECT pc.controller_uid, ci.profile, ci.family, ci.model,
                           cc.endpoint_key, cc.transport, cc.target, cc.port, cc.unit_id,
                           cc.usb_serial, cc.active, cc.last_seen
                    FROM system_members sm
                    JOIN physical_controllers pc ON pc.controller_uid=sm.controller_uid
                    LEFT JOIN controller_identities ci
                      ON ci.controller_id=pc.current_controller_id
                    LEFT JOIN controller_connections cc
                      ON cc.controller_id=pc.current_controller_id
                    WHERE sm.system_uid=?
                    ORDER BY pc.controller_uid, cc.active DESC, cc.last_seen DESC
                    """,
                    (system_uid,),
                )
            ).fetchall()
        controller_nodes: dict[str, dict[str, object]] = {}
        endpoint_nodes: dict[str, dict[str, object]] = {}
        links: list[dict[str, object]] = []
        tcp_groups: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            uid = str(row["controller_uid"])
            controller_nodes.setdefault(
                uid,
                {
                    "id": uid,
                    "type": "controller",
                    "profile": row["profile"] or "",
                    "family": row["family"] or "",
                    "model": row["model"] or "",
                },
            )
            if row["endpoint_key"] is None:
                continue
            transport = str(row["transport"])
            target = str(row["target"])
            port = int(row["port"] or 0)
            if transport == "tcp":
                endpoint_id = f"{transport}:{target}:{port}"
            else:
                endpoint_id = f"{transport}:{target}"
            endpoint_nodes.setdefault(
                endpoint_id,
                {
                    "id": endpoint_id,
                    "type": "transport_endpoint",
                    "transport": transport,
                    "target": target,
                    "port": row["port"],
                },
            )
            link = {
                "from": uid,
                "to": endpoint_id,
                "type": "modbus_connection",
                "unit_id": int(row["unit_id"]),
                "active": bool(row["active"]),
                "last_seen": row["last_seen"],
            }
            links.append(link)
            if transport == "tcp" and row["active"]:
                tcp_groups[(target, port)].append(
                    {
                        "controller_uid": uid,
                        "unit_id": int(row["unit_id"]),
                    }
                )
        bridge_candidates = [
            {
                "target": target,
                "port": port,
                "type": "modbus_tcp_multi_unit_endpoint",
                "confidence": "inferred",
                "controllers": members,
                "reason": (
                    "Multiple physical controller identities are reachable through one "
                    "TCP endpoint at different Modbus unit IDs. This is consistent with "
                    "Morningstar Ethernet-to-serial bridging but is not asserted as proof "
                    "of bridge topology."
                ),
            }
            for (target, port), members in tcp_groups.items()
            if len({item["controller_uid"] for item in members}) > 1
        ]
        return {
            "system_uid": system_uid,
            "nodes": [*controller_nodes.values(), *endpoint_nodes.values()],
            "links": links,
            "bridge_candidates": bridge_candidates,
        }

    async def events(
        self,
        identifier: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, object]]:
        system_uid, device_to_controller, _controllers = await self._scope_map(identifier)
        controller_uids = tuple(sorted(set(device_to_controller.values())))
        events = await self.events_store.recent(
            controller_uids,
            start=start,
            end=end,
            limit=limit,
            include_unassigned=system_uid == self.default_system_uid,
        )
        if not device_to_controller:
            return events[: max(1, min(limit, 5000))]

        device_ids = tuple(device_to_controller)
        placeholders = ",".join("?" for _ in device_ids)
        range_clauses: list[str] = []
        range_params: list[object] = []
        if start is not None:
            range_clauses.append("observed_at>=?")
            range_params.append(start)
        if end is not None:
            range_clauses.append("observed_at<?")
            range_params.append(end)
        error_where = f"device_id IN ({placeholders})"
        if range_clauses:
            error_where += " AND " + " AND ".join(range_clauses)

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            error_rows = await (
                await db.execute(
                    f"""
                    SELECT id, device_id, observed_at, error
                    FROM poll_errors
                    WHERE {error_where}
                    ORDER BY observed_at DESC
                    LIMIT ?
                    """,
                    (*device_ids, *range_params, limit),
                )
            ).fetchall()
            for row in error_rows:
                events.append(
                    {
                        "id": f"poll-error:{row['id']}",
                        "controller_uid": device_to_controller[str(row["device_id"])],
                        "observed_at": str(row["observed_at"]),
                        "event_type": "COMMUNICATION_ERROR",
                        "severity": "warning",
                        "source": "modbus-poll",
                        "message": str(row["error"]),
                        "payload": {"source_device_id": str(row["device_id"])},
                    }
                )
            try:
                sync_rows = await (
                    await db.execute(
                        f"""
                        SELECT id, device_id, attempted_at, source, status,
                               records_seen, records_written, oldest_day, newest_day, error
                        FROM controller_history_syncs
                        WHERE device_id IN ({placeholders})
                        ORDER BY attempted_at DESC
                        LIMIT ?
                        """,
                        (*device_ids, limit),
                    )
                ).fetchall()
            except aiosqlite.OperationalError:
                sync_rows = []
            for row in sync_rows:
                timestamp = str(row["attempted_at"])
                if start is not None and timestamp < start:
                    continue
                if end is not None and timestamp >= end:
                    continue
                ok = str(row["status"]) == "ok"
                events.append(
                    {
                        "id": f"history-sync:{row['id']}",
                        "controller_uid": device_to_controller[str(row["device_id"])],
                        "observed_at": timestamp,
                        "event_type": (
                            "HISTORY_BACKFILL_COMPLETED"
                            if ok
                            else "HISTORY_BACKFILL_FAILED"
                        ),
                        "severity": "info" if ok else "warning",
                        "source": str(row["source"]),
                        "message": str(row["error"] or ""),
                        "payload": {
                            "records_seen": int(row["records_seen"]),
                            "records_written": int(row["records_written"]),
                            "oldest_day": row["oldest_day"],
                            "newest_day": row["newest_day"],
                        },
                    }
                )
            transition_clauses = [
                f"s.device_id IN ({placeholders})",
                (
                    "v.register_name IN ('charge_state','charger_state','faults',"
                    "'fault_state','alarms','alarm_state')"
                ),
            ]
            transition_params: list[object] = list(device_ids)
            if start is not None:
                transition_clauses.append("s.observed_at>=?")
                transition_params.append(start)
            if end is not None:
                transition_clauses.append("s.observed_at<?")
                transition_params.append(end)
            transition_rows = await (
                await db.execute(
                    f"""
                    SELECT s.device_id, s.observed_at, s.id AS sample_id,
                           v.register_name, v.numeric_value, v.text_value
                    FROM register_values v
                    JOIN poll_samples s ON s.id=v.sample_id
                    WHERE {' AND '.join(transition_clauses)}
                    ORDER BY s.observed_at DESC, s.id DESC
                    LIMIT ?
                    """,
                    (*transition_params, max(limit * 10, 1000)),
                )
            ).fetchall()

        previous: dict[tuple[str, str], object] = {}
        for row in reversed(transition_rows):
            controller_uid = device_to_controller[str(row["device_id"])]
            register_name = str(row["register_name"])
            if row["numeric_value"] is not None:
                value: object = row["numeric_value"]
            else:
                value = row["text_value"]
            key = (controller_uid, register_name)
            old = previous.get(key)
            previous[key] = value
            if old is None or old == value:
                continue
            normalized_name = register_name.lower()
            event_type = "STATE_CHANGED"
            severity = "info"
            if "charge" in normalized_name:
                state = str(value).upper()
                if "FLOAT" in state:
                    event_type = "FLOAT_ENTERED"
                elif "ABSOR" in state:
                    event_type = "ABSORPTION_ENTERED"
                elif "EQUAL" in state:
                    event_type = "EQUALIZATION_ENTERED"
                else:
                    event_type = "CHARGE_STATE_CHANGED"
            elif "fault" in normalized_name:
                event_type = (
                    "FAULT_CLEARED" if _state_clear(value) else "FAULT_STARTED"
                )
                severity = "info" if _state_clear(value) else "critical"
            elif "alarm" in normalized_name:
                event_type = (
                    "ALARM_CLEARED" if _state_clear(value) else "ALARM_STARTED"
                )
                severity = "info" if _state_clear(value) else "warning"
            events.append(
                {
                    "id": f"transition:{controller_uid}:{row['sample_id']}:{register_name}",
                    "controller_uid": controller_uid,
                    "observed_at": str(row["observed_at"]),
                    "event_type": event_type,
                    "severity": severity,
                    "source": "live-modbus",
                    "message": "",
                    "payload": {
                        "register_name": register_name,
                        "previous": old,
                        "value": value,
                    },
                }
            )
        events.sort(
            key=lambda item: (
                str(item.get("observed_at") or ""),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        return events[: max(1, min(limit, 5000))]
