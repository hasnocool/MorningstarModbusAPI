# tests/test_storage.py
import pytest

from morningstar_modbus.domain.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    PollResult,
    RegisterValue,
)
from morningstar_modbus.persistence.store import TelemetryStore


@pytest.mark.asyncio
async def test_store_round_trip(tmp_path) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.db"))
    await store.initialize()
    endpoint = Endpoint("tcp", "127.0.0.1", 1, port=502)
    identity = DeviceIdentification("Morningstar", "TriStar MPPT", "1.0")
    device = DiscoveredDevice(endpoint, identity, 1.2, "tristar_mppt")
    device_id = await store.upsert_device(device)
    await store.save_poll(
        device_id,
        PollResult(
            endpoint,
            identity,
            "tristar_mppt",
            1.5,
            (
                RegisterValue(
                    "battery_voltage",
                    0x18,
                    "holding",
                    (123,),
                    12.3,
                    "V",
                ),
            ),
        ),
    )
    latest = await store.latest(device_id)
    assert latest is not None
    assert latest["values"][0]["register_name"] == "battery_voltage"
    assert latest["values"][0]["value"] == 12.3
