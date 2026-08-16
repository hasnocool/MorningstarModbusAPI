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


def _genstar(*, unit_id: int, serial_number: str) -> DiscoveredDevice:
    endpoint = Endpoint("tcp", "192.0.2.30", unit_id, port=502)
    identification = DeviceIdentification("Morningstar Corp.", "GS-MPPT-60M-200V", "1")
    intelligence = DeviceIntelligence(
        profile="genstar_mppt",
        family="GenStar MPPT",
        model="GS-MPPT-60M-200V",
        serial_number=serial_number,
        firmware="3",
        confidence=1.0,
        status="verified",
    )
    return DiscoveredDevice(
        endpoint,
        identification,
        1.0,
        "genstar_mppt",
        intelligence,
    )


def _poll(
    device: DiscoveredDevice,
    *,
    battery_current: float = 8.0,
    system_charge_kwh: float = 2.4,
) -> PollResult:
    values = (
        RegisterValue("serial_number", 0x0001, "holding", (0, 0, 0, 0), device.intelligence.serial_number),
        RegisterValue("battery_sense_voltage", 0x0025, "holding", (0,), 13.2, "V"),
        RegisterValue("load_voltage", 0x0023, "holding", (0,), 13.2, "V"),
        RegisterValue("system_charge_current", 0x0063, "holding", (0,), 25.0, "A"),
        RegisterValue("system_battery_current", 0x0064, "holding", (0,), battery_current, "A"),
        RegisterValue("system_load_current", 0x0065, "holding", (0,), 17.0, "A"),
        RegisterValue("output_power", 0x00F0, "holding", (0,), 330.0, "W"),
        RegisterValue("battery_soc", 0x00E0, "holding", (0,), 80.0, "%"),
        RegisterValue("system_charge_kwh_daily", 0x02D0, "holding", (0, 0), system_charge_kwh, "kWh"),
        RegisterValue("system_charge_ah_daily", 0x02D6, "holding", (0, 0), 182.0, "Ah"),
        RegisterValue("system_battery_ah_daily", 0x02DC, "holding", (0, 0), 12.0, "Ah"),
        RegisterValue("system_load_ah_daily", 0x02E2, "holding", (0, 0), 170.0, "Ah"),
        RegisterValue("aggregated_shunt_charge_ah_daily", 0x227C, "holding", (0, 0), 45.0, "Ah"),
        RegisterValue("aggregated_shunt_charge_kwh_daily", 0x2282, "holding", (0, 0), 0.6, "kWh"),
        RegisterValue("aggregated_shunt_battery_ah_daily", 0x2288, "holding", (0, 0), 10.0, "Ah"),
        RegisterValue("aggregated_shunt_load_ah_daily", 0x228E, "holding", (0, 0), 35.0, "Ah"),
    )
    return PollResult(device.endpoint, device.identification, device.profile, 5.0, values)


async def _seed(tmp_path: Path, *polls: tuple[DiscoveredDevice, PollResult]) -> TelemetryStore:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    registry = ControllerRegistry(store.path)
    for device, poll in polls:
        _controller_uid, device_id = await registry.register_observation(device)
        await store.save_poll(device_id, poll)
    return store


@pytest.mark.asyncio
async def test_genstar_system_currents_complete_battery_and_load_power_flow(tmp_path: Path) -> None:
    device = _genstar(unit_id=1, serial_number="GS-A")
    store = await _seed(tmp_path, (device, _poll(device)))
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        power = (await client.get("/v1/systems/sys_default/power-flow")).json()

    assert power["battery"]["system_charge_current_a"]["value"] == pytest.approx(25.0)
    assert power["battery"]["net_current_a"]["value"] == pytest.approx(8.0)
    assert power["battery"]["net_current_a"]["resolution"] == "single_source"
    assert power["battery"]["net_power_w"]["value"] == pytest.approx(105.6)
    assert power["loads"]["dc_current_a"]["value"] == pytest.approx(17.0)
    assert power["loads"]["dc_power_w"]["value"] == pytest.approx(224.4)
    assert power["balance"]["system_charge_power_w"]["value"] == pytest.approx(330.0)
    assert power["balance"]["system_current_residual_a"]["value"] == pytest.approx(0.0)
    assert power["balance"]["whole_system_residual_w"]["value"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_energy_ledger_uses_system_and_shunt_counters_without_faking_ah_as_wh(
    tmp_path: Path,
) -> None:
    device = _genstar(unit_id=1, serial_number="GS-A")
    store = await _seed(tmp_path, (device, _poll(device)))
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ledger = (await client.get("/v1/systems/sys_default/energy-ledger")).json()

    assert ledger["flows"]["battery_charge_wh"]["value"] == pytest.approx(2400.0)
    assert ledger["flows"]["battery_charge_wh"]["source_metric"] == "system_charge_kwh_daily"
    assert ledger["flows"]["external_source_charge_wh"]["value"] == pytest.approx(600.0)
    assert ledger["flows"]["generator_generated_wh"]["status"] == "unknown"
    assert ledger["flows"]["battery_discharge_wh"]["status"] == "unknown"
    assert ledger["flows"]["load_consumption_wh"]["status"] == "unknown"
    assert ledger["counters"]["system_battery_ah_daily"]["value"] == pytest.approx(12.0)
    assert ledger["counters"]["system_load_ah_daily"]["value"] == pytest.approx(170.0)
    assert ledger["counters"]["shunt_battery_net_ah_daily"]["value"] == pytest.approx(10.0)
    assert ledger["counters"]["shunt_load_ah_daily"]["value"] == pytest.approx(35.0)


@pytest.mark.asyncio
async def test_conflicting_whole_system_current_reporters_remain_unknown(tmp_path: Path) -> None:
    first = _genstar(unit_id=1, serial_number="GS-A")
    second = _genstar(unit_id=2, serial_number="GS-B")
    store = await _seed(
        tmp_path,
        (first, _poll(first, battery_current=8.0)),
        (second, _poll(second, battery_current=-8.0)),
    )
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        power = (await client.get("/v1/systems/sys_default/power-flow")).json()

    assert power["battery"]["net_current_a"]["value"] is None
    assert power["battery"]["net_current_a"]["status"] == "unknown"
    assert power["battery"]["net_current_a"]["quality"] == "conflict"
    assert power["battery"]["net_power_w"]["status"] == "unknown"
