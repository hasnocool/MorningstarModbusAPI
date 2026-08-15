import pytest

from morningstar_modbus.config import AppConfig, DatabaseConfig, WatchConfig
from morningstar_modbus.models import DeviceIdentification, DiscoveredDevice, Endpoint, RegisterValue
from morningstar_modbus.polling import PollPersistenceLimiter, PollTrafficTracker
from morningstar_modbus.watcher import Watcher


class FakeStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self.polls: list[object] = []
        self.errors: list[str] = []

    async def save_poll(self, device_id: str, result: object) -> int:
        self.polls.append((device_id, result))
        return len(self.polls)

    async def save_device_intelligence(self, device_id: str, intelligence: object) -> None:
        return None

    async def save_error(self, device_id: str, error: str) -> None:
        self.errors.append(error)


class FakePerformanceStore:
    def __init__(self) -> None:
        self.rows: list[tuple[str, object, int | None, str]] = []

    async def save(
        self,
        device_id: str,
        performance: object,
        *,
        sample_id: int | None = None,
        mode: str = "watch",
    ) -> int:
        self.rows.append((device_id, performance, sample_id, mode))
        return len(self.rows)


class FakeInventory:
    def __init__(self) -> None:
        self.successes: list[tuple[str, str]] = []

    async def record_success(self, controller_id: str, stable_key: str) -> None:
        self.successes.append((controller_id, stable_key))


class FakeProfile:
    name = "fake"

    def __init__(self) -> None:
        self.poll_count = 0

    async def poll(self, client: object, *, firmware: str = "") -> tuple[RegisterValue, ...]:
        self.poll_count += 1
        return (RegisterValue("battery_voltage", 0, "holding", (1234,), 12.34, "V"),)


class FakeClient:
    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_subsecond_polling_persists_no_faster_than_once_per_second(tmp_path) -> None:
    config = AppConfig(
        database=DatabaseConfig(
            path=str(tmp_path / "telemetry.db"),
            telemetry_write_interval_seconds=1.0,
        ),
        watch=WatchConfig(poll_interval_seconds=0.2),
    )
    store = FakeStore(config.database.path)
    watcher = Watcher(config, store)  # type: ignore[arg-type]
    performance_store = FakePerformanceStore()
    inventory = FakeInventory()
    watcher.performance_store = performance_store  # type: ignore[assignment]
    watcher.controller_inventory = inventory  # type: ignore[assignment]

    clock = [0.0]
    watcher._persistence_limiter = PollPersistenceLimiter(1.0, clock=lambda: clock[0])

    endpoint = Endpoint("tcp", "127.0.0.1", 1, port=502)
    device = DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar", "Synthetic", "1.0"),
        1.0,
        "fake",
    )
    key = endpoint.stable_key
    profile = FakeProfile()
    watcher._device_ids[key] = "device-1"
    watcher._controller_ids[key] = "ctrl_test"
    watcher._profiles[key] = profile  # type: ignore[assignment]
    watcher._clients[key] = FakeClient()  # type: ignore[assignment]
    watcher._traffic[key] = PollTrafficTracker("tcp")

    # Backfill is unrelated to the persistence-cadence test.
    watcher._schedule_history_backfill = lambda *args, **kwargs: None  # type: ignore[method-assign]

    first = await watcher._poll_one(key, device, 0.2)
    clock[0] = 0.2
    second = await watcher._poll_one(key, device, 0.2)
    clock[0] = 1.0
    third = await watcher._poll_one(key, device, 0.2)

    assert first is not None and second is not None and third is not None
    assert profile.poll_count == 3
    assert len(store.polls) == 2
    assert len(performance_store.rows) == 2
    assert len(inventory.successes) == 2
    assert store.errors == []


@pytest.mark.asyncio
async def test_database_failure_does_not_turn_successful_modbus_poll_into_device_failure(tmp_path) -> None:
    class FailingStore(FakeStore):
        async def save_poll(self, device_id: str, result: object) -> int:
            raise RuntimeError("synthetic database failure")

    config = AppConfig(
        database=DatabaseConfig(path=str(tmp_path / "telemetry.db")),
        watch=WatchConfig(poll_interval_seconds=1.0),
    )
    store = FailingStore(config.database.path)
    watcher = Watcher(config, store)  # type: ignore[arg-type]
    watcher.performance_store = FakePerformanceStore()  # type: ignore[assignment]
    watcher.controller_inventory = FakeInventory()  # type: ignore[assignment]

    endpoint = Endpoint("tcp", "127.0.0.1", 1, port=502)
    device = DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar", "Synthetic", "1.0"),
        1.0,
        "fake",
    )
    key = endpoint.stable_key
    watcher._device_ids[key] = "device-1"
    watcher._controller_ids[key] = "ctrl_test"
    watcher._profiles[key] = FakeProfile()  # type: ignore[assignment]
    watcher._clients[key] = FakeClient()  # type: ignore[assignment]
    watcher._traffic[key] = PollTrafficTracker("tcp")
    watcher._schedule_history_backfill = lambda *args, **kwargs: None  # type: ignore[method-assign]

    performance = await watcher._poll_one(key, device, 1.0)

    assert performance is not None
    assert performance.success
    assert watcher._lifecycles[key].state == "online"
    assert watcher._lifecycles[key].consecutive_failures == 0
    assert key in watcher._clients
