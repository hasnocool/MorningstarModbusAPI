"""Continuous discovery and firmware-aware catalog polling runtime."""

from __future__ import annotations

import asyncio
import logging
import time

from morningstar_modbus.catalog import CatalogProfile, get_profile
from morningstar_modbus.config import AppConfig
from morningstar_modbus.controller_history import ControllerHistoryBackfiller
from morningstar_modbus.controller_inventory import ControllerInventoryRepository
from morningstar_modbus.discovery import discover
from morningstar_modbus.intelligence import DeviceIntelligence, refresh_intelligence
from morningstar_modbus.lifecycle import DeviceLifecycle
from morningstar_modbus.models import DiscoveredDevice, PollResult
from morningstar_modbus.polling import PollTrafficTracker
from morningstar_modbus.polling_storage import PollingPerformanceStore
from morningstar_modbus.storage import TelemetryStore
from morningstar_modbus.transport import AsyncModbusRtuClient, AsyncModbusTcpClient, ReadOnlyModbusClient

LOGGER = logging.getLogger(__name__)


class Watcher:
    def __init__(self, config: AppConfig, store: TelemetryStore) -> None:
        self.config = config
        self.store = store
        self.performance_store = PollingPerformanceStore(store.path)
        self.controller_inventory = ControllerInventoryRepository(store.path)
        self._devices: dict[str, DiscoveredDevice] = {}
        self._device_ids: dict[str, str] = {}
        self._controller_ids: dict[str, str] = {}
        self._controller_keys: dict[str, str] = {}
        self._canonical_device_ids: dict[str, str] = {}
        self._clients: dict[str, ReadOnlyModbusClient] = {}
        self._profiles: dict[str, CatalogProfile] = {}
        self._intelligence: dict[str, DeviceIntelligence] = {}
        self._lifecycles: dict[str, DeviceLifecycle] = {}
        self._traffic: dict[str, PollTrafficTracker] = {}
        self._present_keys: set[str] = set()
        self._present_controller_ids: set[str] = set()
        self._history_backfiller = ControllerHistoryBackfiller(store.path, config.backfill)
        self._history_tasks: dict[str, asyncio.Task[None]] = {}
        self._history_attempted_controllers: set[str] = set()
        self._stopping = asyncio.Event()

    async def stop(self) -> None:
        self._stopping.set()
        for device_id in tuple(set(self._canonical_device_ids.values())):
            try:
                await self.controller_inventory.mark_device_offline(device_id)
            except Exception:
                LOGGER.exception("failed to persist offline state device=%s", device_id)
        history_tasks = tuple(self._history_tasks.values())
        self._history_tasks.clear()
        for task in history_tasks:
            task.cancel()
        clients = tuple(self._clients.values())
        self._clients.clear()
        self._profiles.clear()
        self._intelligence.clear()
        self._traffic.clear()
        if history_tasks:
            await asyncio.gather(*history_tasks, return_exceptions=True)
        if clients:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)

    async def run(self) -> None:
        await self._history_backfiller.initialize()
        await self.performance_store.initialize()
        await self.controller_inventory.initialize()
        # Stored rows describe previous daemon sessions until discovery proves
        # a controller/connection is present again. This prevents stale online state.
        await self.controller_inventory.mark_all_offline()
        next_discovery = 0.0
        try:
            while not self._stopping.is_set():
                now = time.monotonic()
                if now >= next_discovery:
                    await self._refresh_devices()
                    next_discovery = now + self.config.watch.discovery_interval_seconds
                cycle_started = time.monotonic()
                await self._poll_all()
                cycle_elapsed = time.monotonic() - cycle_started
                sleep_seconds = max(0.0, self.config.watch.poll_interval_seconds - cycle_elapsed)
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=sleep_seconds)
                except TimeoutError:
                    pass
        finally:
            await self.stop()

    async def _refresh_devices(self) -> None:
        found = await discover(self.config)
        resolved: list[tuple[str, str, str, DiscoveredDevice]] = []
        observed_connections: set[tuple[str, str]] = set()
        for device in found:
            key = device.endpoint.stable_key
            controller_id, device_id = await self.controller_inventory.register_observation(device)
            resolved.append((controller_id, device_id, key, device))
            observed_connections.add((controller_id, key))
        await self.controller_inventory.reconcile_presence(observed_connections)

        selected = self._select_controller_endpoints(resolved)
        found_controller_ids = set(selected)
        missing_controller_ids = self._present_controller_ids - found_controller_ids
        for controller_id in missing_controller_ids:
            key = self._controller_keys.get(controller_id)
            device_id = self._canonical_device_ids.get(controller_id)
            if key is not None:
                lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
                lifecycle.mark_missing()
                client = self._clients.pop(key, None)
                if client is not None:
                    await client.close()
                LOGGER.info(
                    "controller missing controller_id=%s device_id=%s lifecycle=%s",
                    controller_id,
                    device_id,
                    lifecycle.to_dict(),
                )
            if device_id is not None:
                try:
                    await self.controller_inventory.mark_device_offline(device_id)
                except Exception:
                    LOGGER.exception("failed to persist missing controller offline device=%s", device_id)

        for controller_id, (device_id, key, device) in selected.items():
            previous_key = self._controller_keys.get(controller_id)
            previous = self._devices.get(previous_key) if previous_key is not None else None
            if previous is None:
                previous = self._devices.get(key)
            endpoint_moved = (
                (previous_key is not None and previous_key != key)
                or (previous is not None and previous.endpoint != device.endpoint)
            )
            profile_changed = previous is not None and previous.profile != device.profile

            if previous_key is not None and previous_key != key:
                lifecycle = self._lifecycles.pop(previous_key, DeviceLifecycle())
                client = self._clients.pop(previous_key, None)
                if client is not None:
                    await client.close()
                self._profiles.pop(previous_key, None)
                self._intelligence.pop(previous_key, None)
                self._traffic.pop(previous_key, None)
                self._devices.pop(previous_key, None)
                self._device_ids.pop(previous_key, None)
                self._controller_ids.pop(previous_key, None)
            else:
                lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())

            if endpoint_moved and previous_key == key:
                client = self._clients.pop(key, None)
                if client is not None:
                    await client.close()
                self._traffic.pop(key, None)

            lifecycle.mark_discovered(endpoint_changed=endpoint_moved)
            self._lifecycles[key] = lifecycle
            if endpoint_moved:
                LOGGER.info(
                    "controller endpoint rebound controller_id=%s device_id=%s old=%s new=%s",
                    controller_id,
                    device_id,
                    previous.endpoint.locator if previous is not None else "unknown",
                    device.endpoint.locator,
                )
            if endpoint_moved or profile_changed:
                self._profiles.pop(key, None)
            if device.intelligence is not None:
                self._intelligence[key] = device.intelligence
                await self.store.save_device_intelligence(device_id, device.intelligence)
            self._devices[key] = device
            self._device_ids[key] = device_id
            self._controller_ids[key] = controller_id
            self._controller_keys[controller_id] = key
            self._canonical_device_ids[controller_id] = device_id

        self._present_controller_ids = found_controller_ids
        self._present_keys = {key for _device_id, key, _device in selected.values()}
        if found:
            LOGGER.info(
                "discovered %d Modbus endpoint(s) representing %d controller(s)",
                len(found),
                len(selected),
            )

    def _select_controller_endpoints(
        self,
        resolved: list[tuple[str, str, str, DiscoveredDevice]],
    ) -> dict[str, tuple[str, str, DiscoveredDevice]]:
        grouped: dict[str, list[tuple[str, str, DiscoveredDevice]]] = {}
        for controller_id, device_id, key, device in resolved:
            grouped.setdefault(controller_id, []).append((device_id, key, device))

        selected: dict[str, tuple[str, str, DiscoveredDevice]] = {}
        for controller_id, candidates in grouped.items():
            existing_key = self._controller_keys.get(controller_id)
            existing = next((item for item in candidates if item[1] == existing_key), None)
            if existing is not None:
                selected[controller_id] = existing
                continue
            selected[controller_id] = min(candidates, key=self._endpoint_preference)
        return selected

    @staticmethod
    def _endpoint_preference(item: tuple[str, str, DiscoveredDevice]) -> tuple[int, str]:
        _device_id, key, device = item
        endpoint = device.endpoint
        if endpoint.transport == "tcp":
            rank = 0
        elif endpoint.usb_serial:
            rank = 1
        else:
            rank = 2
        return rank, key

    async def _poll_all(self) -> None:
        if not self._present_keys:
            return
        async with asyncio.TaskGroup() as group:
            for key in tuple(self._present_keys):
                device = self._devices.get(key)
                lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
                if device is not None and lifecycle.can_poll():
                    group.create_task(self._poll_one(key, device))

    def _tracker(self, key: str, device: DiscoveredDevice) -> PollTrafficTracker:
        tracker = self._traffic.get(key)
        if tracker is None:
            endpoint = device.endpoint
            tracker = PollTrafficTracker(
                endpoint.transport,
                baudrate=(endpoint.baudrate or self.config.serial.baudrate)
                if endpoint.transport == "serial"
                else None,
                stop_bits=endpoint.stop_bits or self.config.serial.stop_bits,
            )
            self._traffic[key] = tracker
        return tracker

    def _create_client(self, key: str, device: DiscoveredDevice) -> ReadOnlyModbusClient:
        endpoint = device.endpoint
        observer = self._tracker(key, device).record
        if endpoint.transport == "tcp":
            return AsyncModbusTcpClient(
                endpoint.target,
                port=endpoint.port or 502,
                unit_id=endpoint.unit_id,
                timeout=self.config.watch.request_timeout_seconds,
                observer=observer,
            )
        return AsyncModbusRtuClient(
            endpoint.target,
            baudrate=endpoint.baudrate or self.config.serial.baudrate,
            stop_bits=endpoint.stop_bits or self.config.serial.stop_bits,
            unit_id=endpoint.unit_id,
            timeout=self.config.watch.request_timeout_seconds,
            observer=observer,
        )

    def _client(self, key: str, device: DiscoveredDevice) -> ReadOnlyModbusClient:
        client = self._clients.get(key)
        if client is None:
            client = self._create_client(key, device)
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
        controller_id: str,
        device_id: str,
        device: DiscoveredDevice,
        *,
        reconnected: bool,
    ) -> None:
        if not self._history_backfiller.supports(device):
            return
        initial_sync = controller_id not in self._history_attempted_controllers
        should_sync = (initial_sync and self.config.backfill.on_startup) or (
            reconnected and self.config.backfill.on_reconnect
        )
        if not should_sync:
            return
        existing = self._history_tasks.get(controller_id)
        if existing is not None and not existing.done():
            return
        self._history_attempted_controllers.add(controller_id)
        task = asyncio.create_task(
            self._backfill_history(controller_id, device_id, device),
            name=f"controller-history-{device_id}",
        )
        self._history_tasks[controller_id] = task

    async def _backfill_history(
        self,
        controller_id: str,
        device_id: str,
        device: DiscoveredDevice,
    ) -> None:
        try:
            result = await self._history_backfiller.sync(device_id, device)
            LOGGER.info(
                "controller history sync controller=%s device=%s status=%s records=%d oldest=%s newest=%s",
                controller_id,
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
                "controller history sync failed controller=%s device=%s endpoint=%s error=%s",
                controller_id,
                device_id,
                device.endpoint.locator,
                exc,
            )
        finally:
            current = self._history_tasks.get(controller_id)
            if current is asyncio.current_task():
                self._history_tasks.pop(controller_id, None)

    async def _poll_one(self, key: str, device: DiscoveredDevice) -> None:
        device_id = self._device_ids.get(key)
        controller_id = self._controller_ids.get(key)
        if device_id is None or controller_id is None:
            return
        lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
        reconnected = bool(lifecycle.offline_since or lifecycle.consecutive_failures)
        lifecycle.mark_connecting()
        tracker = self._tracker(key, device)
        tracker.begin()
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
            sample_id = await self.store.save_poll(
                device_id,
                PollResult(device.endpoint, device.identification, profile.name, latency_ms, values),
            )
            try:
                await self.controller_inventory.record_success(controller_id, device.endpoint.stable_key)
            except Exception:
                LOGGER.exception("failed to persist connection success controller=%s", controller_id)
            performance = tracker.finish(
                configured_interval_seconds=self.config.watch.poll_interval_seconds,
                poll_latency_ms=latency_ms,
                success=True,
            )
            try:
                await self.performance_store.save(
                    device_id,
                    performance,
                    sample_id=sample_id,
                    mode="watch",
                )
            except Exception:
                LOGGER.exception("failed to persist poll-performance telemetry device=%s", device_id)
            if intelligence is not None:
                intelligence = refresh_intelligence(
                    intelligence,
                    values,
                    endpoint=device.endpoint,
                )
                self._intelligence[key] = intelligence
                await self.store.save_device_intelligence(device_id, intelligence)
            self._schedule_history_backfill(
                controller_id,
                device_id,
                device,
                reconnected=reconnected,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            performance = tracker.finish(
                configured_interval_seconds=self.config.watch.poll_interval_seconds,
                poll_latency_ms=latency_ms,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            try:
                await self.performance_store.save(device_id, performance, mode="watch")
            except Exception:
                LOGGER.exception("failed to persist poll-performance telemetry device=%s", device_id)
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
