from datetime import UTC, datetime, timedelta

import aiosqlite
import httpx
import pytest

import morningstar_modbus.watcher as watcher_module
from morningstar_modbus.api import create_app
from morningstar_modbus.config import AppConfig
from morningstar_modbus.controller_data import ControllerDataRepository
from morningstar_modbus.controller_scope import ControllerRegistry
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


def _device(endpoint: Endpoint, serial_number: str) -> DiscoveredDevice:
    return DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        1.0,
        "tristar_mppt",
        _intelligence(serial_number),
    )


async def _insert_legacy_device(
    path: str,
    *,
    device_id: str,
    target: str,
    serial_number: str,
    last_seen: str,
) -> None:
    first_seen = (datetime.fromisoformat(last_seen) - timedelta(hours=1)).isoformat()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT INTO devices (
                id, stable_key, transport, target, port, unit_id, usb_serial, usb_vid, usb_pid,
                vendor_name, product_code, revision, profile, status, first_seen, last_seen, last_error
            ) VALUES (?, ?, 'serial', ?, NULL, 1, NULL, 1027, 24577,
                      'Morningstar Corp.', 'TS-MPPT-60', '29', 'tristar_mppt',
                      'offline', ?, ?, NULL)
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


async def _insert_sample(
    path: str,
    *,
    device_id: str,
    observed_at: str,
    value: float,
) -> None:
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            """
            INSERT INTO poll_samples(device_id, observed_at, latency_ms, profile)
            VALUES (?, ?, 10.0, 'tristar_mppt')
            """,
            (device_id, observed_at),
        )
        sample_id = int(cursor.lastrowid or 0)
        await db.execute(
            """
            INSERT INTO register_values(
                sample_id, register_name, address, function, raw_json,
                numeric_value, text_value, unit
            ) VALUES (?, 'battery_voltage', 24, 'holding', '[0]', ?, NULL, 'V')
            """,
            (sample_id, value),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_controller_uid_survives_identity_promotion_and_old_alias_resolves(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    registry = ControllerRegistry(path)
    endpoint = Endpoint(
        "serial",
        "/dev/ttyUSB0",
        1,
        baudrate=9600,
        stop_bits=2,
        usb_serial="ADAPTER-1",
    )

    fallback_uid, fallback_device_id = await registry.register_observation(_device(endpoint, ""))
    identified_uid, identified_device_id = await registry.register_observation(
        _device(endpoint, "TS123456")
    )

    assert identified_uid == fallback_uid
    assert identified_device_id == fallback_device_id
    assert identified_uid.startswith("ctrl_")

    old_scope = await registry.resolve("usb:adapter-1:unit:1")
    new_scope = await registry.resolve("morningstar:tristar_mppt:ts123456")
    assert old_scope is not None
    assert new_scope is not None
    assert old_scope.controller_uid == identified_uid
    assert new_scope.controller_uid == identified_uid
    assert new_scope.controller_id == "morningstar:tristar_mppt:ts123456"

    controller = await registry.get_controller(identified_uid)
    assert controller is not None
    assert controller["controller_uid"] == identified_uid
    assert controller["controller_id"] == "morningstar:tristar_mppt:ts123456"


@pytest.mark.asyncio
async def test_controller_scope_unifies_legacy_sample_and_register_history(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    now = datetime.now(UTC)
    first_id = "serial:/dev/ttyUSB0:unit:1"
    second_id = "serial:/dev/ttyUSB1:unit:1"
    await _insert_legacy_device(
        path,
        device_id=first_id,
        target="/dev/ttyUSB0",
        serial_number="TS123456",
        last_seen=(now - timedelta(hours=2)).isoformat(),
    )
    await _insert_legacy_device(
        path,
        device_id=second_id,
        target="/dev/ttyUSB1",
        serial_number="TS123456",
        last_seen=(now - timedelta(hours=1)).isoformat(),
    )
    await _insert_sample(
        path,
        device_id=first_id,
        observed_at="2026-08-14T10:00:00+00:00",
        value=12.4,
    )
    await _insert_sample(
        path,
        device_id=second_id,
        observed_at="2026-08-14T11:00:00+00:00",
        value=13.6,
    )

    data = ControllerDataRepository(path)
    await data.initialize()
    controllers = await data.list_controllers()
    assert len(controllers) == 1
    uid = str(controllers[0]["controller_uid"])

    samples = await data.samples(uid, order="asc")
    assert [row["source_device_id"] for row in samples] == [first_id, second_id]

    history = await data.register_history(uid, "battery_voltage", order="asc")
    assert [row["value"] for row in history] == [12.4, 13.6]
    assert [row["source_device_id"] for row in history] == [first_id, second_id]

    scope, stats = await data.register_stats(
        uid,
        ("battery_voltage",),
        start=None,
        end=None,
    )
    assert set(scope.history_device_ids) == {first_id, second_id}
    assert stats[0]["count"] == 2
    assert stats[0]["min"] == 12.4
    assert stats[0]["max"] == 13.6

    summary = await data.history_summary(uid, start=None, end=None)
    assert summary["sample_count"] == 2
    assert summary["register_observation_count"] == 2


@pytest.mark.asyncio
async def test_controller_api_exposes_uid_and_source_device_provenance(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    store = TelemetryStore(path)
    await store.initialize()
    now = datetime.now(UTC)
    first_id = "serial:/dev/ttyUSB0:unit:1"
    second_id = "serial:/dev/ttyUSB1:unit:1"
    for index, device_id in enumerate((first_id, second_id)):
        await _insert_legacy_device(
            path,
            device_id=device_id,
            target=f"/dev/ttyUSB{index}",
            serial_number="TS123456",
            last_seen=(now - timedelta(minutes=2 - index)).isoformat(),
        )
    await _insert_sample(
        path,
        device_id=first_id,
        observed_at="2026-08-14T10:00:00+00:00",
        value=12.4,
    )
    await _insert_sample(
        path,
        device_id=second_id,
        observed_at="2026-08-14T11:00:00+00:00",
        value=13.6,
    )

    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        controllers = (await client.get("/v1/controllers")).json()
        uid = controllers[0]["controller_uid"]
        assert uid.startswith("ctrl_")
        assert set(controllers[0]["history_device_ids"]) == {first_id, second_id}

        response = await client.get(f"/v1/controllers/{uid}/samples", params={"order": "asc"})
        assert response.status_code == 200
        rows = response.json()
        assert [row["source_device_id"] for row in rows] == [first_id, second_id]

        response = await client.get(
            f"/v1/controllers/{uid}/registers/history",
            params=[("name", "battery_voltage"), ("order", "asc")],
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["controller_uid"] == uid
        points = payload["series"][0]["points"]
        assert [point["source_device_id"] for point in points] == [first_id, second_id]

        response = await client.get(f"/v1/controllers/{uid}/history/export", params={"format": "csv"})
        assert response.status_code == 200
        assert "source_device_id" in response.text.splitlines()[0]
        assert first_id in response.text
        assert second_id in response.text

        response = await client.get("/v1/controllers/ctrl_missing/samples")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_watcher_keeps_same_uid_when_identity_strengthens(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "telemetry.db")
    store = TelemetryStore(path)
    await store.initialize()
    watcher = Watcher(AppConfig(), store)
    endpoint = Endpoint(
        "serial",
        "/dev/ttyUSB0",
        1,
        baudrate=9600,
        stop_bits=2,
        usb_serial="ADAPTER-1",
    )
    current = [_device(endpoint, "")]

    async def fake_discover(_config: AppConfig) -> list[DiscoveredDevice]:
        return list(current)

    monkeypatch.setattr(watcher_module, "discover", fake_discover)
    await watcher._refresh_devices()
    key = endpoint.stable_key
    uid_before = watcher._controller_ids[key]
    lifecycle_before = watcher._lifecycles[key]

    current[:] = [_device(endpoint, "TS123456")]
    await watcher._refresh_devices()

    assert watcher._controller_ids[key] == uid_before
    assert watcher._lifecycles[key] is lifecycle_before
    controller = await watcher.controller_inventory.get_controller(uid_before)
    assert controller is not None
    assert controller["controller_id"] == "morningstar:tristar_mppt:ts123456"
