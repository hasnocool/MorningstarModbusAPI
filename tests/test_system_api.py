# tests/test_system_api.py
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.config import AppConfig, HistoryBackfillConfig, load_config
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.domain.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    PollResult,
    RegisterValue,
)
from morningstar_modbus.history.retained.service import ControllerHistoryBackfiller
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.persistence.store import TelemetryStore
from morningstar_modbus.systems.data import SystemDataRepository


def _device(unit_id: int, serial_number: str) -> DiscoveredDevice:
    endpoint = Endpoint("tcp", "192.0.2.10", unit_id, port=502)
    intelligence = DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        serial_number=serial_number,
        firmware="29",
        confidence=1.0,
        status="verified",
    )
    return DiscoveredDevice(
        endpoint,
        DeviceIdentification("Morningstar Corp.", "TS-MPPT-60", "29"),
        1.0,
        "tristar_mppt",
        intelligence,
    )


def _poll(
    device: DiscoveredDevice,
    *,
    battery_voltage: float,
    charge_current: float,
    output_power: float,
    input_power: float,
    daily_wh: float,
    daily_ah: float,
    charge_state: str,
    faults: int = 0,
    alarms: int = 0,
) -> PollResult:
    values = (
        RegisterValue("battery_voltage", 0x0018, "holding", (0,), battery_voltage, "V"),
        RegisterValue(
            "battery_charge_current",
            0x001C,
            "holding",
            (0,),
            charge_current,
            "A",
        ),
        RegisterValue("charge_state", 0x0032, "holding", (0,), charge_state),
        RegisterValue("output_power", 0x003A, "holding", (0,), output_power, "W"),
        RegisterValue("input_power_reported", 0x003B, "holding", (0,), input_power, "W"),
        RegisterValue("daily_charge_ah", 0x0043, "holding", (0,), daily_ah, "Ah"),
        RegisterValue("daily_charge_wh", 0x0044, "holding", (0,), daily_wh, "Wh"),
        RegisterValue("faults", 0x002C, "holding", (faults,), faults),
        RegisterValue("alarms", 0x002E, "holding", (alarms, 0), alarms),
    )
    return PollResult(
        device.endpoint,
        device.identification,
        device.profile,
        5.0,
        values,
    )


async def _seed_two_controller_system(tmp_path: Path) -> tuple[TelemetryStore, tuple[str, str]]:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    registry = ControllerRegistry(store.path)

    first = _device(1, "TS-A")
    second = _device(2, "TS-B")
    first_uid, first_device_id = await registry.register_observation(first)
    second_uid, second_device_id = await registry.register_observation(second)

    await store.save_poll(
        first_device_id,
        _poll(
            first,
            battery_voltage=14.2,
            charge_current=20.0,
            output_power=280.0,
            input_power=300.0,
            daily_wh=1000.0,
            daily_ah=70.0,
            charge_state="Absorption",
        ),
    )
    await store.save_poll(
        second_device_id,
        _poll(
            second,
            battery_voltage=14.4,
            charge_current=30.0,
            output_power=420.0,
            input_power=450.0,
            daily_wh=1500.0,
            daily_ah=105.0,
            charge_state="Float",
        ),
    )
    return store, (first_uid, second_uid)


@pytest.mark.asyncio
async def test_system_api_aggregates_multi_controller_site_and_topology(tmp_path: Path) -> None:
    store, controller_uids = await _seed_two_controller_system(tmp_path)
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        systems_response = await client.get("/v1/systems")
        assert systems_response.status_code == 200
        systems = systems_response.json()
        assert len(systems) == 1
        assert systems[0]["system_uid"] == "sys_default"
        assert systems[0]["controller_count"] == 2

        latest_response = await client.get("/v1/systems/sys_default/latest")
        assert latest_response.status_code == 200
        metrics = latest_response.json()["metrics"]
        assert metrics["battery_charge_current_a"]["value"] == pytest.approx(50.0)
        assert metrics["battery_voltage_v"]["value"] == pytest.approx(14.3)
        assert metrics["charge_output_power_w"]["value"] == pytest.approx(700.0)
        assert metrics["solar_input_power_w"]["value"] == pytest.approx(750.0)
        assert metrics["battery_charge_current_a"]["quality"] == "complete"
        assert metrics["battery_charge_current_a"]["expected_contributors"] == 2

        energy = (await client.get("/v1/systems/sys_default/energy")).json()
        assert energy["metrics"]["daily_charge_wh"]["value"] == pytest.approx(2500.0)
        assert energy["metrics"]["daily_charge_ah"]["value"] == pytest.approx(175.0)

        health = (await client.get("/v1/systems/sys_default/health")).json()
        assert health["status"] == "ok"
        assert health["active_fault_controllers"] == 0
        assert health["active_alarm_controllers"] == 0

        topology = (await client.get("/v1/systems/sys_default/topology")).json()
        assert len(topology["bridge_candidates"]) == 1
        bridge = topology["bridge_candidates"][0]
        assert bridge["confidence"] == "inferred"
        assert {item["controller_uid"] for item in bridge["controllers"]} == set(controller_uids)
        assert {item["unit_id"] for item in bridge["controllers"]} == {1, 2}


@pytest.mark.asyncio
async def test_system_history_and_event_timeline_preserve_provenance(tmp_path: Path) -> None:
    store, controller_uids = await _seed_two_controller_system(tmp_path)
    registry = ControllerRegistry(store.path)
    first = _device(1, "TS-A")
    first_uid, first_device_id = await registry.register_observation(first)
    assert first_uid == controller_uids[0]

    await store.save_poll(
        first_device_id,
        _poll(
            first,
            battery_voltage=14.3,
            charge_current=25.0,
            output_power=350.0,
            input_power=375.0,
            daily_wh=1200.0,
            daily_ah=84.0,
            charge_state="Float",
        ),
    )
    await store.save_error(first_device_id, "TimeoutError: controller did not answer")

    data = SystemDataRepository(store.path)
    history = await data.history(
        "sys_default",
        "battery_charge_current_a",
        start=None,
        end=None,
        resolution="1m",
    )
    assert history["metric"]["aggregation"] == "sum"
    assert history["points"]
    assert all("sources" in point for point in history["points"])

    events = await data.events("sys_default", limit=100)
    event_types = {str(event["event_type"]) for event in events}
    assert "FLOAT_ENTERED" in event_types
    assert "COMMUNICATION_ERROR" in event_types
    assert all(event.get("controller_uid") in set(controller_uids) for event in events)


@pytest.mark.asyncio
async def test_retained_history_registry_keeps_legacy_repository_surface(tmp_path: Path) -> None:
    config = HistoryBackfillConfig()
    backfiller = ControllerHistoryBackfiller(str(tmp_path / "history.sqlite3"), config)
    assert backfiller.repository is not None
    assert backfiller.summary() == [{"name": "tristar-liveview-daily"}]


@pytest.mark.asyncio
async def test_system_marks_aggregate_partial_when_expected_controller_has_no_sample(
    tmp_path: Path,
) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    registry = ControllerRegistry(store.path)
    first = _device(1, "TS-A")
    second = _device(2, "TS-B")
    _first_uid, first_device_id = await registry.register_observation(first)
    await registry.register_observation(second)
    await store.save_poll(
        first_device_id,
        _poll(
            first,
            battery_voltage=14.2,
            charge_current=20.0,
            output_power=280.0,
            input_power=300.0,
            daily_wh=1000.0,
            daily_ah=70.0,
            charge_state="Absorption",
        ),
    )

    latest = await SystemDataRepository(store.path).latest("sys_default")
    metric = latest["metrics"]["battery_charge_current_a"]
    assert metric["value"] == pytest.approx(20.0)
    assert metric["quality"] == "partial"
    assert metric["contributors"] == 1
    assert metric["expected_contributors"] == 2


def test_system_and_snmp_configuration_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[system]
default_uid = "sys_camp"
default_name = "camp"

[snmp]
enabled = true
host = "127.0.0.1"
port = 9162
max_packet_bytes = 4096
""".strip(),
        encoding="utf-8",
    )
    config = load_config(str(config_path))
    assert isinstance(config, AppConfig)
    assert config.system.default_uid == "sys_camp"
    assert config.system.default_name == "camp"
    assert config.snmp.enabled is True
    assert config.snmp.port == 9162
    assert config.snmp.max_packet_bytes == 4096
