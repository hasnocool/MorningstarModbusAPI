"""Continuous discovery and firmware-aware catalog polling runtime."""

from __future__ import annotations

import asyncio
import logging
import time

from morningstar_modbus.catalog import CatalogProfile, get_profile
from morningstar_modbus.config import AppConfig
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
        self._devices: dict[str, DiscoveredDevice] = {}
        self._device_ids: dict[str, str] = {}
        self._clients: dict[str, ReadOnlyModbusClient] = {}
        self._profiles: dict[str, CatalogProfile] = {}
        self._intelligence: dict[str, DeviceIntelligence] = {}
        self._lifecycles: dict[str, DeviceLifecycle] = {}
        self._traffic: dict[str, PollTrafficTracker] = {}
        self._present_keys: set[str] = set()
        self._stopping = asyncio.Event()

    async def stop(self) -> None:
        self._stopping.set()
        clients = tuple(self._clients.values())
        self._clients.clear()
        self._profiles.clear()
        self._intelligence.clear()
        self._traffic.clear()
        if clients:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)

    async def run(self) -> None:
        await self.performance_store.initialize()
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
                self._traffic.pop(key, None)
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

    async def _poll_one(self, key: str, device: DiscoveredDevice) -> None:
        device_id = self._device_ids.get(key)
        if device_id is None:
            return
        lifecycle = self._lifecycles.setdefault(key, DeviceLifecycle())
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
            performance = tracker.finish(
                configured_interval_seconds=self.config.watch.poll_interval_seconds,
                poll_latency_ms=latency_ms,
                success=True,
            )
            await self.performance_store.save(device_id, performance, sample_id=sample_id, mode="watch")
            if intelligence is not None:
                intelligence = refresh_intelligence(
                    intelligence,
                    values,
                    endpoint=device.endpoint,
                )
                self._intelligence[key] = intelligence
                await self.store.save_device_intelligence(device_id, intelligence)
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
