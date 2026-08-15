from pathlib import Path

import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.catalog import catalog_detail
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.lifecycle import DeviceLifecycle
from morningstar_modbus.models import DiscoveredDevice, Endpoint, PollResult
from morningstar_modbus.replay import ReplayMismatch, ReplayModbusClient
from morningstar_modbus.storage import TelemetryStore
from morningstar_modbus.verification import verify_device

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "morningstar"
    / "tristar_mppt"
    / "TS-MPPT-60"
    / "synthetic-fw-29"
)


@pytest.mark.asyncio
async def test_tristar_replay_runs_real_resolver_and_profile() -> None:
    client = ReplayModbusClient.from_bundle(FIXTURE)
    endpoint = Endpoint("tcp", "replay", 1, port=502)
    report, identification, values = await verify_device(client, endpoint)

    assert identification.vendor_name == "Morningstar Corporation"
    assert report.profile == "tristar_mppt"
    assert report.model == "TS-MPPT-60"
    assert report.firmware == "29"
    assert report.result == "verified"
    assert report.named_registers_decoded >= 20
    assert client.remaining == 0
    names = {value.name for value in values}
    assert {
        "battery_voltage",
        "array_voltage",
        "battery_charge_current",
        "array_current",
        "charge_state",
        "output_power",
        "input_power",
    } <= names


@pytest.mark.asyncio
async def test_replay_is_strict_about_request_order() -> None:
    client = ReplayModbusClient.from_bundle(FIXTURE)
    with pytest.raises(ReplayMismatch):
        await client.read_holding_registers(0, 1)


def test_catalog_exposes_verification_evidence() -> None:
    detail = catalog_detail("tristar_mppt")
    assert detail is not None
    verification = detail["verification"]
    assert verification["document"] == "verified"
    assert verification["software"] == "verified"
    assert verification["fixture"] == "synthetic"
    assert verification["hardware"] == "pending"


def test_device_lifecycle_backoff_and_recovery() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.mark_discovered()
    lifecycle.mark_failure(threshold=2, initial_backoff=1.0, max_backoff=8.0)
    assert lifecycle.state == "degraded"
    assert lifecycle.consecutive_failures == 1
    assert not lifecycle.can_poll(now=lifecycle.next_retry_monotonic - 0.1)

    lifecycle.mark_failure(threshold=2, initial_backoff=1.0, max_backoff=8.0)
    assert lifecycle.state == "offline"
    assert lifecycle.retry_in_seconds == 2.0
    lifecycle.mark_success()
    assert lifecycle.state == "online"
    assert lifecycle.consecutive_failures == 0
    assert lifecycle.reconnect_count == 1


@pytest.mark.asyncio
async def test_replay_values_flow_through_storage_and_api(tmp_path: Path) -> None:
    endpoint = Endpoint("tcp", "replay", 1, port=502)
    replay = ReplayModbusClient.from_bundle(FIXTURE)
    report, identification, values = await verify_device(replay, endpoint)

    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    intelligence = DeviceIntelligence(
        profile=report.profile,
        family=report.family,
        model=report.model,
        firmware=report.firmware,
        hardware_revision=report.hardware_revision,
        confidence=report.confidence,
        status=report.intelligence_status,
    )
    device = DiscoveredDevice(endpoint, identification, 1.0, report.profile, intelligence)
    device_id = await store.upsert_device(device)
    await store.save_poll(
        device_id,
        PollResult(endpoint, identification, report.profile, 1.0, values),
    )

    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        devices = await client.get("/v1/devices")
        latest = await client.get("/v1/devices/latest", params={"device_id": device_id})
        resolved = await client.get(
            "/v1/devices/intelligence",
            params={"device_id": device_id},
        )
        register_map = await client.get(
            "/v1/devices/register-map",
            params={"device_id": device_id},
        )
        validation = await client.get(
            "/v1/devices/profile/validation",
            params={"device_id": device_id},
        )
        history = await client.get(
            "/v1/devices/registers/battery_voltage/history",
            params={"device_id": device_id},
        )

    assert devices.status_code == 200
    assert latest.status_code == 200
    assert resolved.json()["model"] == "TS-MPPT-60"
    assert register_map.json()["profile"] == "tristar_mppt"
    assert validation.json()["status"] == report.intelligence_status
    assert history.json()
