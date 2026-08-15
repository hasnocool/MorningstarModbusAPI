from datetime import UTC, datetime, timedelta

import aiosqlite
import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.controller_inventory import ControllerInventoryRepository
from morningstar_modbus.storage import TelemetryStore


async def _insert_endpoint(
    path: str,
    *,
    device_id: str,
    target: str,
    last_seen: str,
    serial_number: str = "TS123456",
    status: str = "online",
) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT INTO devices (
                id, stable_key, transport, target, port, unit_id, usb_serial, usb_vid, usb_pid,
                vendor_name, product_code, revision, profile, status, first_seen, last_seen, last_error
            ) VALUES (?, ?, 'serial', ?, NULL, 1, NULL, 1027, 24577,
                      'Morningstar Corp.', 'TS-MPPT-60', '29', 'tristar_mppt', ?, ?, ?, NULL)
            """,
            (
                device_id,
                device_id,
                target,
                status,
                (datetime.fromisoformat(last_seen) - timedelta(hours=6)).isoformat(),
                last_seen,
            ),
        )
        if serial_number:
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


@pytest.mark.asyncio
async def test_groups_reconnected_endpoints_by_controller_serial(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    store = TelemetryStore(path)
    await store.initialize()
    now = datetime.now(UTC)
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB0:unit:1",
        target="/dev/ttyUSB0",
        last_seen=(now - timedelta(hours=6)).isoformat(),
    )
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB1:unit:1",
        target="/dev/ttyUSB1",
        last_seen=(now - timedelta(hours=1)).isoformat(),
    )
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB2:unit:1",
        target="/dev/ttyUSB2",
        last_seen=(now - timedelta(seconds=10)).isoformat(),
    )

    controllers = await ControllerInventoryRepository(path).list_controllers()

    assert len(controllers) == 1
    controller = controllers[0]
    assert controller["serial_number"] == "TS123456"
    assert controller["status"] == "online"
    assert controller["current_device_id"] == "serial:/dev/ttyUSB2:unit:1"
    assert controller["connection_count"] == 3
    assert controller["active_connection_count"] == 1
    assert [item["role"] for item in controller["connections"]] == [
        "current",
        "previous",
        "previous",
    ]
    assert [item["status"] for item in controller["connections"]] == [
        "online",
        "offline",
        "offline",
    ]

    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/controllers")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["connection_count"] == 3


@pytest.mark.asyncio
async def test_old_online_record_is_reported_offline_when_stale(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB0:unit:1",
        target="/dev/ttyUSB0",
        last_seen=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    )

    controllers = await ControllerInventoryRepository(path, online_grace_seconds=120).list_controllers()

    assert controllers[0]["status"] == "offline"
    assert controllers[0]["active_connection_count"] == 0


@pytest.mark.asyncio
async def test_ambiguous_identical_controllers_without_serial_are_not_merged(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    now = datetime.now(UTC).isoformat()
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB0:unit:1",
        target="/dev/ttyUSB0",
        last_seen=now,
        serial_number="",
    )
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB1:unit:1",
        target="/dev/ttyUSB1",
        last_seen=now,
        serial_number="",
    )

    controllers = await ControllerInventoryRepository(path).list_controllers()

    assert len(controllers) == 2
    assert all(controller["identity_source"] == "endpoint" for controller in controllers)


@pytest.mark.asyncio
async def test_serialless_endpoint_is_not_guessed_into_identified_controller(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    now = datetime.now(UTC)
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB0:unit:1",
        target="/dev/ttyUSB0",
        last_seen=(now - timedelta(minutes=1)).isoformat(),
        serial_number="TS123456",
    )
    await _insert_endpoint(
        path,
        device_id="serial:/dev/ttyUSB1:unit:1",
        target="/dev/ttyUSB1",
        last_seen=now.isoformat(),
        serial_number="",
    )

    controllers = await ControllerInventoryRepository(path).list_controllers()

    assert len(controllers) == 2
    assert {controller["identity_source"] for controller in controllers} == {
        "controller_serial",
        "endpoint",
    }


@pytest.mark.asyncio
async def test_offline_lifecycle_updates_persisted_endpoint_status(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    device_id = "serial:/dev/ttyUSB0:unit:1"
    await _insert_endpoint(
        path,
        device_id=device_id,
        target="/dev/ttyUSB0",
        last_seen=datetime.now(UTC).isoformat(),
        status="error",
    )
    repository = ControllerInventoryRepository(path)

    await repository.mark_device_offline(device_id)
    controller = (await repository.list_controllers())[0]
    assert controller["status"] == "offline"
    assert controller["current_connection"]["status"] == "offline"

    async with aiosqlite.connect(path) as db:
        row = await (await db.execute("SELECT status FROM devices WHERE id=?", (device_id,))).fetchone()
    assert row == ("offline",)
