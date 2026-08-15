from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

import morningstar_modbus.watcher as watcher_module
from morningstar_modbus.config import AppConfig
from morningstar_modbus.controller_inventory import ControllerInventoryRepository
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.models import DeviceIdentification, DiscoveredDevice, Endpoint
from morningstar_modbus.storage import TelemetryStore
from morningstar_modbus.watcher import Watcher


def _intelligence(serial_number: str) -> DeviceIntelligence:
    return DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        serial_number=serial_number,
        firmware="29",
        confidence=1.0,
        status="verified",
    )


def _device(endpoint: Endpoint, serial_number: str = "TS123456") -> DiscoveredDevice:
    return DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        1.0,
        "tristar_mppt",
        _intelligence(serial_number),
    )


async def _insert_legacy_endpoint(
    path: str,
    *,
    device_id: str,
    target: str,
    last_seen: str,
    serial_number: str = "TS123456",
) -> None:
    first_seen = (datetime.fromisoformat(last_seen) - timedelta(hours=6)).isoformat()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT INTO devices (
                id, stable_key, transport, target, port, unit_id, usb_serial, usb_vid, usb_pid,
                vendor_name, product_code, revision, profile, status, first_seen, last_seen, last_error
            ) VALUES (?, ?, 'serial', ?, NULL, 1, NULL, 1027, 24577,
                      'Morningstar Corp.', 'TS-MPPT-60', '29', 'tristar_mppt',
                      'online', ?, ?, NULL)
            """,
            (device_id, device_id, target, first_seen, last_seen),
        )
        await db.execute(
            """
            INSERT INTO device_intelligence (
                device_id, profile, family, model, serial_number, firmware, hardware_revision,
                catalog_revision, confidence, intelligence_status, capabilities_json, network_json,
                evidence_json, warnings_json, metadata_json, updated_at
            ) VALUES (?, 'tristar_mppt', 'TriStar MPPT 150V', 'TS-MPPT-60', ?, '29', '2',
                      'v11', 1.0, 'verified', '[]', '{}', '[]', '[]', '{}', ?)
            """,
            (device_id, serial_number, last_seen),
        )
        await db.commit()


class _FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_migration_keeps_latest_legacy_id_as_canonical_and_members(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    now = datetime.now(UTC)
    ids = [
        "serial:/dev/ttyUSB0:unit:1",
        "serial:/dev/ttyUSB1:unit:1",
        "serial:/dev/ttyUSB2:unit:1",
    ]
    for index, device_id in enumerate(ids):
        await _insert_legacy_endpoint(
            path,
            device_id=device_id,
            target=f"/dev/ttyUSB{index}",
            last_seen=(now - timedelta(hours=2 - index)).isoformat(),
        )

    repository = ControllerInventoryRepository(path)
    controllers = await repository.list_controllers()

    assert len(controllers) == 1
    controller = controllers[0]
    assert controller["canonical_device_id"] == ids[-1]
    assert controller["current_device_id"] == ids[-1]
    assert set(controller["history_device_ids"]) == set(ids)
    assert controller["connection_count"] == 3


@pytest.mark.asyncio
async def test_future_endpoint_move_reuses_canonical_device_id(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    store = TelemetryStore(path)
    await store.initialize()
    now = datetime.now(UTC)
    old_id = "tcp:192.0.2.10:502:unit:1"
    await _insert_legacy_endpoint(
        path,
        device_id=old_id,
        target="192.0.2.10",
        last_seen=now.isoformat(),
    )
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE devices SET transport='tcp', port=502 WHERE id=?",
            (old_id,),
        )
        await db.commit()

    repository = ControllerInventoryRepository(path)
    await repository.initialize()
    moved = _device(Endpoint("tcp", "192.0.2.77", 1, port=502))
    controller_id, device_id = await repository.register_observation(moved)

    assert device_id == old_id
    controller = await repository.get_controller(controller_id)
    assert controller is not None
    assert controller["canonical_device_id"] == old_id
    assert set(controller["history_device_ids"]) == {old_id}
    assert {item["target"] for item in controller["connections"]} == {
        "192.0.2.10",
        "192.0.2.77",
    }
    stored = await store.get_device(old_id)
    assert stored is not None
    assert stored["target"] == "192.0.2.77"


@pytest.mark.asyncio
async def test_endpoint_reuse_by_different_controller_serial_does_not_merge(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    store = TelemetryStore(path)
    await store.initialize()
    repository = ControllerInventoryRepository(path)

    first = _device(Endpoint("tcp", "192.0.2.10", 1, port=502), "SERIAL-A")
    first_controller, first_device_id = await repository.register_observation(first)
    await store.save_device_intelligence(first_device_id, first.intelligence)  # type: ignore[arg-type]

    replacement = _device(Endpoint("tcp", "192.0.2.10", 1, port=502), "SERIAL-B")
    second_controller, second_device_id = await repository.register_observation(replacement)

    assert second_controller != first_controller
    assert second_device_id != first_device_id
    assert second_device_id.startswith("device:tristar_mppt:")


@pytest.mark.asyncio
async def test_usb_path_change_is_recorded_without_changing_canonical_id(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    repository = ControllerInventoryRepository(path)
    first = _device(
        Endpoint(
            "serial",
            "/dev/ttyUSB0",
            1,
            baudrate=9600,
            stop_bits=2,
            usb_serial="ADAPTER-1",
        )
    )
    moved = _device(
        Endpoint(
            "serial",
            "/dev/ttyUSB1",
            1,
            baudrate=9600,
            stop_bits=2,
            usb_serial="ADAPTER-1",
        )
    )

    controller_id, first_id = await repository.register_observation(first)
    moved_controller, moved_id = await repository.register_observation(moved)

    assert moved_controller == controller_id
    assert moved_id == first_id
    controller = await repository.get_controller(controller_id)
    assert controller is not None
    assert {item["target"] for item in controller["connections"]} == {
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
    }


@pytest.mark.asyncio
async def test_fallback_usb_identity_promotes_when_controller_serial_appears(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    repository = ControllerInventoryRepository(path)
    endpoint = Endpoint(
        "serial",
        "/dev/ttyUSB0",
        1,
        baudrate=9600,
        stop_bits=2,
        usb_serial="ADAPTER-1",
    )

    fallback_controller, fallback_device = await repository.register_observation(_device(endpoint, ""))
    controller_id, canonical_device = await repository.register_observation(_device(endpoint, "TS123456"))

    assert fallback_controller.startswith("usb:")
    assert controller_id == "morningstar:tristar_mppt:ts123456"
    assert canonical_device == fallback_device
    controllers = await repository.list_controllers()
    assert len(controllers) == 1
    assert controllers[0]["controller_id"] == controller_id
    assert controllers[0]["canonical_device_id"] == fallback_device


@pytest.mark.asyncio
async def test_temporary_serial_metadata_loss_reuses_known_controller_identity(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    repository = ControllerInventoryRepository(path)
    endpoint = Endpoint(
        "serial",
        "/dev/ttyUSB0",
        1,
        baudrate=9600,
        stop_bits=2,
        usb_serial="ADAPTER-1",
    )

    controller_id, canonical_device = await repository.register_observation(_device(endpoint, "TS123456"))
    observed_controller, observed_device = await repository.register_observation(_device(endpoint, ""))

    assert observed_controller == controller_id
    assert observed_device == canonical_device
    assert len(await repository.list_controllers()) == 1


@pytest.mark.asyncio
async def test_watcher_rebinds_lifecycle_and_closes_stale_client(tmp_path, monkeypatch) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.db"))
    await store.initialize()
    watcher = Watcher(AppConfig(), store)
    first = _device(Endpoint("tcp", "192.0.2.10", 1, port=502))
    moved = _device(Endpoint("tcp", "192.0.2.77", 1, port=502))
    current = [first]

    async def fake_discover(_config: AppConfig) -> list[DiscoveredDevice]:
        return list(current)

    monkeypatch.setattr(watcher_module, "discover", fake_discover)
    await watcher._refresh_devices()
    first_key = first.endpoint.stable_key
    device_id = watcher._device_ids[first_key]
    controller_id = watcher._controller_ids[first_key]
    client = _FakeClient()
    watcher._clients[first_key] = client  # type: ignore[assignment]

    current[:] = [moved]
    await watcher._refresh_devices()
    moved_key = moved.endpoint.stable_key

    assert client.closed
    assert first_key not in watcher._devices
    assert watcher._device_ids[moved_key] == device_id
    assert watcher._controller_ids[moved_key] == controller_id
    assert watcher._controller_keys[controller_id] == moved_key
    assert watcher._lifecycles[moved_key].endpoint_changes == 1


@pytest.mark.asyncio
async def test_watcher_deduplicates_simultaneous_serial_and_tcp_connections(tmp_path, monkeypatch) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.db"))
    await store.initialize()
    watcher = Watcher(AppConfig(), store)
    serial = _device(
        Endpoint(
            "serial",
            "/dev/ttyUSB0",
            1,
            baudrate=9600,
            stop_bits=2,
            usb_serial="ADAPTER-1",
        )
    )
    tcp = _device(Endpoint("tcp", "192.0.2.10", 1, port=502))

    async def fake_discover(_config: AppConfig) -> list[DiscoveredDevice]:
        return [serial, tcp]

    monkeypatch.setattr(watcher_module, "discover", fake_discover)
    await watcher._refresh_devices()

    assert len(watcher._present_controller_ids) == 1
    assert watcher._present_keys == {tcp.endpoint.stable_key}
    controller_id = next(iter(watcher._present_controller_ids))
    controller = await watcher.controller_inventory.get_controller(controller_id)
    assert controller is not None
    assert controller["active_connection_count"] == 1
    assert controller["current_connection"]["transport"] == "tcp"
    assert {item["transport"] for item in controller["connections"]} == {"serial", "tcp"}
