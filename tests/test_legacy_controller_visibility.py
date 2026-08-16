from datetime import UTC, datetime, timedelta

import aiosqlite
import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.domain.models import DeviceIdentification, DiscoveredDevice, Endpoint
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.persistence.store import TelemetryStore


async def _insert_old_endpoint_only_device(path: str) -> None:
    last_seen = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    first_seen = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT INTO devices (
                id, stable_key, transport, target, port, unit_id, usb_serial, usb_vid, usb_pid,
                vendor_name, product_code, revision, profile, status, first_seen, last_seen, last_error
            ) VALUES (
                'serial:/dev/ttyUSB1:unit:1', 'serial:/dev/ttyUSB1:unit:1', 'serial',
                '/dev/ttyUSB1', NULL, 1, NULL, 6790, 29987,
                'Morningstar Corp.', 'TS-MPPT-60', '29', 'tristar_mppt',
                'offline', ?, ?, NULL
            )
            """,
            (first_seen, last_seen),
        )
        await db.commit()


def _identified_controller() -> tuple[DiscoveredDevice, Endpoint]:
    endpoint = Endpoint(
        "serial",
        "/dev/ttyUSB0",
        1,
        baudrate=9600,
        stop_bits=2,
        usb_serial="CURRENT-ADAPTER",
    )
    intelligence = DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        serial_number="TS123456",
        firmware="29",
        confidence=1.0,
        status="verified",
    )
    device = DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        1.0,
        "tristar_mppt",
        intelligence,
    )
    return device, endpoint


@pytest.mark.asyncio
async def test_default_controller_inventory_hides_inactive_legacy_endpoint_placeholder(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    store = TelemetryStore(path)
    await store.initialize()
    await _insert_old_endpoint_only_device(path)

    registry = ControllerRegistry(path)
    await registry.initialize()

    # The raw inventory keeps the historical endpoint identity as provenance.
    raw_before = await registry.inventory.list_controllers()
    assert len(raw_before) == 1
    assert raw_before[0]["identity_source"] == "endpoint"
    assert raw_before[0]["status"] == "offline"

    device, endpoint = _identified_controller()
    controller_uid, _ = await registry.register_observation(device)
    await registry.reconcile_presence({(controller_uid, endpoint.stable_key)})

    # The application-facing inventory contains only the controller that the
    # modern identity system has actually rediscovered.
    controllers = await registry.list_controllers()
    assert len(controllers) == 1
    assert controllers[0]["controller_uid"] == controller_uid
    assert controllers[0]["serial_number"] == "TS123456"
    assert controllers[0]["status"] == "online"

    # Nothing was deleted: the low-level inventory still has the legacy row.
    raw_after = await registry.inventory.list_controllers()
    assert len(raw_after) == 2
    assert {str(row["identity_source"]) for row in raw_after} == {
        "controller_serial",
        "endpoint",
    }

    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/controllers")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["controller_uid"] == controller_uid
    assert payload[0]["serial_number"] == "TS123456"
    assert payload[0]["status"] == "online"


@pytest.mark.asyncio
async def test_modern_endpoint_only_controller_remains_visible_after_disconnect(tmp_path) -> None:
    path = str(tmp_path / "telemetry.db")
    await TelemetryStore(path).initialize()
    registry = ControllerRegistry(path)

    endpoint = Endpoint("serial", "/dev/ttyUSB0", 1, baudrate=9600, stop_bits=2)
    intelligence = DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        serial_number="",
        firmware="29",
        confidence=0.5,
        status="candidate",
    )
    device = DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        0.5,
        "tristar_mppt",
        intelligence,
    )

    controller_uid, _ = await registry.register_observation(device)
    await registry.reconcile_presence(set())

    controllers = await registry.list_controllers()
    assert len(controllers) == 1
    assert controllers[0]["controller_uid"] == controller_uid
    assert controllers[0]["identity_source"] == "endpoint"
    assert controllers[0]["status"] == "offline"
