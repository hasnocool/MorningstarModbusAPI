from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.domain.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    PollResult,
    RegisterValue,
)
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.persistence.store import TelemetryStore
from morningstar_modbus.systems.components import (
    SystemComponentService,
    decode_readyedge_bus_and_address,
)
from morningstar_modbus.systems.data import SystemDataRepository


def _device(
    *,
    unit_id: int,
    profile: str,
    family: str,
    model: str,
    serial_number: str,
) -> DiscoveredDevice:
    endpoint = Endpoint("tcp", "192.0.2.20", unit_id, port=502)
    intelligence = DeviceIntelligence(
        profile=profile,
        family=family,
        model=model,
        serial_number=serial_number,
        firmware="1",
        confidence=1.0,
        status="verified",
    )
    return DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", model, "1"),
        1.0,
        profile,
        intelligence,
    )


def _readyedge() -> DiscoveredDevice:
    return _device(
        unit_id=1,
        profile="readyedge",
        family="ReadyEdge RE-1",
        model="RE-1",
        serial_number="RE-A",
    )


def _tristar() -> DiscoveredDevice:
    return _device(
        unit_id=200,
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        serial_number="TS-A",
    )


def _readyedge_poll(device: DiscoveredDevice) -> PollResult:
    values = (
        RegisterValue("serial_number", 0x0001, "holding", (0, 0, 0, 0), "RE-A"),
        RegisterValue("battery_soc", 0x0083, "holding", (0,), 82.0, "%"),
        RegisterValue(
            "connected_product_0_type",
            0x1F53,
            "holding",
            (0x0104,),
            "TriStar-MPPT",
        ),
        RegisterValue(
            "connected_product_0_serial",
            0x1F54,
            "holding",
            (0, 0, 0, 0),
            "TS-A",
        ),
        RegisterValue(
            "connected_product_0_bus_and_address",
            0x1F58,
            "holding",
            ((4 << 8) | 200,),
            (4 << 8) | 200,
        ),
    )
    return PollResult(device.endpoint, device.identification, device.profile, 5.0, values)


def _tristar_poll(device: DiscoveredDevice) -> PollResult:
    values = (
        RegisterValue("serial_number", 0xE0C0, "holding", (0, 0, 0, 0), "TS-A"),
        RegisterValue("battery_voltage", 0x0018, "holding", (0,), 14.2, "V"),
        RegisterValue("battery_charge_current", 0x001C, "holding", (0,), 20.0, "A"),
        RegisterValue("output_power", 0x003A, "holding", (0,), 280.0, "W"),
        RegisterValue("input_power_reported", 0x003B, "holding", (0,), 650.0, "W"),
        RegisterValue("input_power", 0x003B, "holding", (0,), 300.0, "W"),
        RegisterValue("daily_charge_ah", 0x0043, "holding", (0,), 70.0, "Ah"),
        RegisterValue("daily_charge_wh", 0x0044, "holding", (0,), 1000.0, "Wh"),
        RegisterValue("charge_state", 0x0032, "holding", (0,), "Absorption"),
        RegisterValue("faults", 0x002C, "holding", (0,), 0),
        RegisterValue("alarms", 0x002E, "holding", (0, 0), 0),
    )
    return PollResult(device.endpoint, device.identification, device.profile, 5.0, values)


async def _seed_component_system(tmp_path: Path) -> tuple[TelemetryStore, str, str]:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    registry = ControllerRegistry(store.path)

    readyedge = _readyedge()
    tristar = _tristar()
    readyedge_uid, readyedge_device_id = await registry.register_observation(readyedge)
    tristar_uid, tristar_device_id = await registry.register_observation(tristar)
    await store.save_poll(readyedge_device_id, _readyedge_poll(readyedge))
    await store.save_poll(tristar_device_id, _tristar_poll(tristar))
    return store, readyedge_uid, tristar_uid


def test_readyedge_bus_and_modbus_address_decoder() -> None:
    decoded = decode_readyedge_bus_and_address((4 << 8) | 200)
    assert decoded == {
        "raw": 1224,
        "bus_code": 4,
        "bus": "eia485",
        "modbus_id": 200,
    }


@pytest.mark.asyncio
async def test_component_graph_reconciles_readyedge_product_to_existing_controller(
    tmp_path: Path,
) -> None:
    store, readyedge_uid, tristar_uid = await _seed_component_system(tmp_path)
    data = SystemDataRepository(store.path)
    graph = await SystemComponentService(data).graph("sys_default")

    component_uids = {str(item["component_uid"]) for item in graph["components"]}
    assert readyedge_uid in component_uids
    assert tristar_uid in component_uids
    assert len(graph["components"]) == 4

    relationships = [
        item
        for item in graph["relationships"]
        if item["source"] == "readyedge_connected_product"
    ]
    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship["from"] == readyedge_uid
    assert relationship["to"] == tristar_uid
    assert relationship["type"] == "monitors"
    assert relationship["confidence"] == "verified"
    assert relationship["bus"]["bus"] == "eia485"
    assert relationship["bus"]["modbus_id"] == 200
    assert relationship["serial_number"] == "TS-A"


@pytest.mark.asyncio
async def test_power_flow_and_energy_ledger_are_explicit_about_unknown_flows(
    tmp_path: Path,
) -> None:
    store, _readyedge_uid, _tristar_uid = await _seed_component_system(tmp_path)
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = (await client.get("/v1/systems/sys_default/component-graph")).json()
        assert graph["summary"]["readyedge_connected_products"] == 1

        power = (await client.get("/v1/systems/sys_default/power-flow")).json()
        assert power["sources"]["solar_input_power_w"]["value"] == pytest.approx(300.0)
        assert power["battery"]["charge_power_w"]["value"] == pytest.approx(280.0)
        assert power["balance"]["controller_power_residual_w"]["value"] == pytest.approx(20.0)
        assert power["balance"]["controller_conversion_efficiency_percent"]["value"] == pytest.approx(
            280.0 / 300.0 * 100.0
        )
        assert power["battery"]["net_current_a"]["status"] == "unknown"
        assert power["loads"]["dc_power_w"]["status"] == "unknown"

        ledger = (await client.get("/v1/systems/sys_default/energy-ledger")).json()
        assert ledger["flows"]["battery_charge_wh"]["value"] == pytest.approx(1000.0)
        assert ledger["flows"]["battery_charge_wh"]["status"] == "observed"
        assert ledger["flows"]["load_consumption_wh"]["status"] == "unknown"

        topology = (await client.get("/v1/systems/sys_default/topology")).json()
        assert topology["component_graph"]["summary"]["readyedge_connected_products"] == 1
