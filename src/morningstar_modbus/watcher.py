"""Continuous discovery and firmware-aware catalog polling runtime."""

from __future__ import annotations

import asyncio
import logging
import time

from morningstar_modbus.catalog import CatalogProfile, get_profile
from morningstar_modbus.config import AppConfig
from morningstar_modbus.controller_history import ControllerHistoryBackfiller
from morningstar_modbus.discovery import discover
from morningstar_modbus.intelligence import DeviceIntelligence, refresh_intelligence
from morningstar_modbus.lifecycle import DeviceLifecycle
from morningstar_modbus.models import DiscoveredDevice, PollResult
from morningstar_modbus.storage import TelemetryStore
from morningstar_modbus.transport import AsyncModbusRtuClient, AsyncModbusTcpClient, ReadOnlyModbusClient

LOGGER = logging.getLogger(__name__)


class Watcher:
    def __init__(self, config: AppConfig, store: TelemetryStore) -> None:
        self.config = config
        self.store = store
        self._devices: dict[str, DiscoveredDevice] = {}
        self._device_ids: dict[str, str] = {}
        self._clients: dict[str, ReadOnlyModbusClient] = {}
        self._profiles: dict[str, CatalogProfile] = {}
        self._intelligence: dict[str, DeviceIntelligence] = {}
        self._lifecycles: dict[str, DeviceLifecycle] = {}
        self._present_keys: set[str] = set()
        self._history_backfiller = ControllerHistoryBackfiller(store.path, config.backfill)
        self._history_tasks: dict[str, asyncio.Task[None]] = {}
        self._history_attempted_keys: set[str] = set()
        self._stopping = asyncio.Event()

    async def stop(self) -> None:
        self._stopping.set()
        history_tasks = tuple(self._history_tasks.values())
        self._history_tasks.clear()
        for task in history_tasks:
            task.cancel()
        clients = tuple(self._clients.values())
        self._clients.clear()
        self._profiles.clear()
        self._intelligence.clear()
        if history_tasks:
            await asyncio.gather(*history_tasks, return_exceptions=True)
        if clients:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)

    async def run(self) -> None:
        await self._history_backfiller.initialize()
        next_discovery = 0.0
        try:
            while not self._stopping.is_set():
                now = time.monotonic()
                if now >= next_discovery:
                    await self._refresh_devices()
                    next_discovery = now + self.config.watch.discovery_interval_seconds
                await self._poll_all()
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self.config.watch.poll_interval_seconds
                    )
                except TimeoutError:
                    pass
        finally:
            await self.stop()

    async def _refresh_devices(self) -> None:
        found = await discover(self.config)
        found_keys = {device.endpoint.stable_key for device in found}
        missing = self._present_keys - found_keys
        for key in missing:
            lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
            lifecycle.mark_missing()
            client = self._clients.pop(key, None)
            if client is not None:
                await client.close()
            LOGGER.info("device missing key=%s lifecycle=%s", key, lifecycle.to_dict())

        for device in found:
            key = device.endpoint.stable_key
            previous = self._devices.get(key)
            endpoint_moved = previous is not None and previous.endpoint != device.endpoint
            profile_changed = previous is not None and previous.profile != device.profile
            lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
            lifecycle.mark_discovered(endpoint_changed=endpoint_moved)
            if endpoint_moved:
                client = self._clients.pop(key, None)
                if client is not None:
                    await client.close()
                LOGGER.info(
                    "endpoint moved key=%s old=%s new=%s",
                    key,
                    previous.endpoint.locator,
                    device.endpoint.locator,
                )
            if endpoint_moved or profile_changed:
                self._profiles.pop(key, None)
            if device.intelligence is not None:
                self._intelligence[key] = device.intelligence
            self._devices[key] = device
            self._device_ids[key] = await self.store.upsert_device(device)
        self._present_keys = found_keys
        if found:
            LOGGER.info("discovered %d Modbus endpoint(s)", len(found))

    async def _poll_all(self) -> None:
        if not self._present_keys:
            return
        async with asyncio.TaskGroup() as group:
            for key in tuple(self._present_keys):
                device = self._devices.get(key)
                lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
                if device is not None and lifecycle.can_poll():
                    group.create_task(self._poll_one(key, device))

    def _create_client(self, device: DiscoveredDevice) -> ReadOnlyModbusClient:
        endpoint = device.endpoint
        if endpoint.transport == "tcp":
            return AsyncModbusTcpClient(
                endpoint.target,
                port=endpoint.port or 502,
                unit_id=endpoint.unit_id,
                timeout=self.config.watch.request_timeout_seconds,
            )
        return AsyncModbusRtuClient(
            endpoint.target,
            baudrate=endpoint.baudrate or self.config.serial.baudrate,
            stop_bits=endpoint.stop_bits or self.config.serial.stop_bits,
            unit_id=endpoint.unit_id,
            timeout=self.config.watch.request_timeout_seconds,
        )

    def _client(self, key: str, device: DiscoveredDevice) -> ReadOnlyModbusClient:
        client = self._clients.get(key)
        if client is None:
            client = self._create_client(device)
            self._clients[key] = client
        return client

    def _profile(self, key: str, device: DiscoveredDevice) -> CatalogProfile:
        profile = self._profiles.get(key)
        if profile is None or profile.name != device.profile:
            profile = get_profile(device.profile)
            self._profiles[key] = profile
        return profile

    def _schedule_history_backfill(
        self,
        key: str,
        device_id: str,
        device: DiscoveredDevice,
        *,
        reconnected: bool,
    ) -> None:
        if not self._history_backfiller.supports(device):
            return
        initial_sync = key not in self._history_attempted_keys
        should_sync = (initial_sync and self.config.backfill.on_startup) or (
            reconnected and self.config.backfill.on_reconnect
        )
        if not should_sync:
            return
        existing = self._history_tasks.get(key)
        if existing is not None and not existing.done():
            return
        self._history_attempted_keys.add(key)
        task = asyncio.create_task(
            self._backfill_history(key, device_id, device),
            name=f"controller-history-{device_id}",
        )
        self._history_tasks[key] = task

    async def _backfill_history(
        self,
        key: str,
        device_id: str,
        device: DiscoveredDevice,
    ) -> None:
        try:
            result = await self._history_backfiller.sync(device_id, device)
            LOGGER.info(
                "controller history sync device=%s status=%s records=%d oldest=%s newest=%s",
                device_id,
                result.status,
                result.records_written,
                result.oldest_day,
                result.newest_day,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning(
                "controller history sync failed device=%s endpoint=%s error=%s",
                device_id,
                device.endpoint.locator,
                exc,
            )
        finally:
            current = self._history_tasks.get(key)
            if current is asyncio.current_task():
                self._history_tasks.pop(key, None)

    async def _poll_one(self, key: str, device: DiscoveredDevice) -> None:
        device_id = self._device_ids.get(key)
        if device_id is None:
            return
        lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
        reconnected = bool(lifecycle.offline_since or lifecycle.consecutive_failures)
        lifecycle.mark_connecting()
        client = self._client(key, device)
        profile = self._profile(key, device)
        intelligence = self._intelligence.get(key)
        started = time.perf_counter()
        try:
            values = await profile.poll(
                client,
                firmware=intelligence.firmware if intelligence is not None else "",
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            lifecycle.mark_success()
            await self.store.save_poll(
                device_id,
                PollResult(device.endpoint, device.identification, profile.name, latency_ms, values),
            )
            if intelligence is not None:
                intelligence = refresh_intelligence(
                    intelligence,
                    values,
                    endpoint=device.endpoint,
                )
                self._intelligence[key] = intelligence
                await self.store.save_device_intelligence(device_id, intelligence)
            self._schedule_history_backfill(
                key,
                device_id,
                device,
                reconnected=reconnected,
            )
        except Exception as exc:
            lifecycle.mark_failure(
                threshold=self.config.watch.failure_threshold,
                initial_backoff=self.config.watch.retry_backoff_initial_seconds,
                max_backoff=self.config.watch.retry_backoff_max_seconds,
            )
            client = self._clients.pop(key, None)
            if client is not None:
                await client.close()
            LOGGER.warning(
                "poll failed endpoint=%s error=%s lifecycle=%s",
                device.endpoint.locator,
                exc,
                lifecycle.to_dict(),
            )
            await self.store.save_error(device_id, f"{type(exc).__name__}: {exc}")
