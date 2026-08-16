# src/morningstar_modbus/snmp_traps.py
"""Optional non-blocking SNMP trap ingestion into the unified event timeline.

The listener intentionally treats datagrams as opaque evidence.  It does not
implement SNMP SET/GET operations and does not persist community strings or raw
packets.  Source IP, size, and a SHA-256 digest are enough to correlate a trap
with controller/network events while preserving the project's read-only scope.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

import aiosqlite

from morningstar_modbus.persistence.events import EventStore


@dataclass(slots=True)
class SnmpTrapSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 9162
    max_packet_bytes: int = 65_507


class _TrapProtocol(asyncio.DatagramProtocol):
    def __init__(self, listener: SnmpTrapListener) -> None:
        self.listener = listener

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not data or len(data) > self.listener.settings.max_packet_bytes:
            return
        task = asyncio.create_task(self.listener._record(data, addr), name="snmp-trap-record")
        self.listener._tasks.add(task)
        task.add_done_callback(self.listener._tasks.discard)

    def error_received(self, exc: Exception) -> None:
        self.listener.last_error = f"{type(exc).__name__}: {exc}"


class SnmpTrapListener:
    """Async UDP trap listener; disabled unless explicitly configured."""

    def __init__(self, database_path: str, settings: SnmpTrapSettings) -> None:
        self.path = database_path
        self.settings = settings
        self.events = EventStore(database_path)
        self._transport: asyncio.DatagramTransport | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.last_error = ""

    async def start(self) -> None:
        if not self.settings.enabled or self._transport is not None:
            return
        await self.events.initialize()
        loop = asyncio.get_running_loop()
        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _TrapProtocol(self),
            local_addr=(self.settings.host, self.settings.port),
        )
        self._transport = transport

    async def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        tasks = tuple(self._tasks)
        self._tasks.clear()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _controller_candidates(self, source_host: str) -> tuple[str, ...]:
        try:
            async with aiosqlite.connect(self.path) as db:
                rows = await (
                    await db.execute(
                        """
                        SELECT DISTINCT pc.controller_uid
                        FROM controller_connections cc
                        JOIN physical_controllers pc
                          ON pc.current_controller_id=cc.controller_id
                        WHERE cc.transport='tcp' AND cc.target=? AND cc.active=1
                        ORDER BY pc.controller_uid
                        """,
                        (source_host,),
                    )
                ).fetchall()
        except aiosqlite.OperationalError:
            return ()
        return tuple(str(row[0]) for row in rows)

    async def _record(self, data: bytes, addr: tuple[str, int]) -> None:
        source_host, source_port = addr
        candidates = await self._controller_candidates(source_host)
        controller_uid = candidates[0] if len(candidates) == 1 else None
        payload: dict[str, Any] = {
            "source_port": source_port,
            "packet_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "candidate_controller_uids": list(candidates),
            "decoded": False,
        }
        await self.events.record(
            "SNMP_TRAP",
            controller_uid=controller_uid,
            severity="info",
            source="snmp-udp",
            message="SNMP trap datagram received",
            payload=payload,
            source_host=source_host,
        )
