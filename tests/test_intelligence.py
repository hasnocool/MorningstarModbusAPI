# tests/test_intelligence.py
from pathlib import Path

import pytest

from morningstar_modbus.catalog.compatibility import compare_versions, in_range
from morningstar_modbus.catalog.types import (
    DeviceProfileSpec,
    RegisterBlock,
    RegisterSpec,
    ReservedRegisterRange,
)
from morningstar_modbus.intelligence import (
    DeviceIntelligence,
    effective_register_map,
    refresh_intelligence,
    resolve_device_intelligence,
)
from morningstar_modbus.intelligence.models import IntelligenceEvidence
from morningstar_modbus.models import DeviceIdentification, Endpoint, RegisterValue
from morningstar_modbus.storage import TelemetryStore


class TriStarMetadataClient:
    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        if (address, count) == (0xE0C0, 0x000E):
            words = [0] * 14
            words[0:4] = [0x4241, 0x3143, 0x3332, 0x0034]
            words[12] = 1
            words[13] = 0x0102
            return words
        if count == 1 and address in {0x0000, 0x0001, 0x0002, 0x0003}:
            return [0]
        if (address, count) == (0x0004, 1):
            return [0x0029]
        raise TimeoutError((address, count))

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        raise TimeoutError((address, count))

    async def read_device_identification(self) -> DeviceIdentification:
        return DeviceIdentification()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_resolver_combines_identity_metadata_and_catalog() -> None:
    identity = DeviceIdentification(
        vendor_name="Morningstar Corporation",
        product_code="TS-MPPT-60",
    )
    endpoint = Endpoint("tcp", "192.0.2.10", 1, port=502)
    intelligence = await resolve_device_intelligence(
        TriStarMetadataClient(),
        identity,
        endpoint=endpoint,
    )

    assert intelligence.profile == "tristar_mppt"
    assert intelligence.model == "TS-MPPT-60"
    assert intelligence.serial_number == "ABC1234"
    assert intelligence.firmware == "29"
    assert intelligence.hardware_revision == "1.2"
    assert intelligence.status == "verified"
    assert intelligence.confidence >= 0.85
    assert "modbus_tcp" in intelligence.capabilities


def test_firmware_comparison_and_ranges_are_numeric() -> None:
    assert compare_versions("v1.10", "1.9") > 0
    assert compare_versions("29", "v29.0") == 0
    assert in_range("2.5", since="2.0", until="2.9")
    assert not in_range("3.0", until="2.9")


def test_effective_map_applies_firmware_gates() -> None:
    from morningstar_modbus.catalog.registry import PROFILE_BY_NAME

    spec = DeviceProfileSpec(
        name="firmware-gate-test",
        family="test",
        aliases=(),
        source_id="test",
        source_url="https://example.invalid",
        blocks=(
            RegisterBlock(0, 1),
            RegisterBlock(10, 1, since_firmware="2.0"),
        ),
        registers=(
            RegisterSpec("always", 0),
            RegisterSpec("new", 10, since_firmware="2.0"),
        ),
        reserved_ranges=(
            ReservedRegisterRange(5),
            ReservedRegisterRange(15, since_firmware="2.0"),
        ),
    )
    PROFILE_BY_NAME[spec.name] = spec
    try:
        old = effective_register_map(spec.name, "1.9")
        new = effective_register_map(spec.name, "2.0")
    finally:
        PROFILE_BY_NAME.pop(spec.name, None)

    assert old is not None and new is not None
    assert {item["name"] for item in old["registers"]} == {"always"}
    assert {item["name"] for item in new["registers"]} == {"always", "new"}
    assert {item["address"] for item in old["reserved_ranges"]} == {5}
    assert {item["address"] for item in new["reserved_ranges"]} == {5, 15}


def test_tristar_effective_map_marks_documented_reserved_words() -> None:
    register_map = effective_register_map("tristar_mppt", "32")
    assert register_map is not None

    reserved_addresses = {
        address
        for item in register_map["reserved_ranges"]
        for address in range(int(item["address"]), int(item["address"]) + int(item["count"]))
    }

    assert set(range(0x0005, 0x0018)).issubset(reserved_addresses)
    assert {0x002D, 0x003F, 0x004A}.issubset(reserved_addresses)
    assert set(range(0xE0C4, 0xE0CC)).issubset(reserved_addresses)


def test_implausible_telemetry_invalidates_profile() -> None:
    base = DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        confidence=0.9,
        status="verified",
        evidence=(
            IntelligenceEvidence("vendor", "vendor matched", 0.28),
            IntelligenceEvidence("product-code", "product matched", 0.32),
            IntelligenceEvidence("metadata", "metadata matched", 0.18),
            IntelligenceEvidence("firmware", "firmware resolved", 0.08),
        ),
    )
    values = (
        RegisterValue("battery_voltage", 0x0018, "holding", (1,), 5000.0, "V"),
    )
    updated = refresh_intelligence(base, values)
    assert updated.status == "invalid"
    assert any(issue.code == "implausible-value" for issue in updated.warnings)


@pytest.mark.asyncio
async def test_intelligence_persistence_is_separate_from_telemetry(tmp_path: Path) -> None:
    store = TelemetryStore(str(tmp_path / "telemetry.sqlite3"))
    await store.initialize()
    device_id = "tcp:192.0.2.10:502:unit:1"
    intelligence = DeviceIntelligence(
        profile="tristar_mppt",
        family="TriStar MPPT 150V",
        model="TS-MPPT-60",
        firmware="29",
        confidence=0.92,
        status="verified",
        capabilities=("modbus_tcp",),
    )
    from morningstar_modbus.models import DiscoveredDevice

    device = DiscoveredDevice(
        Endpoint("tcp", "192.0.2.10", 1, port=502),
        DeviceIdentification("Morningstar", "TS-MPPT-60"),
        1.0,
        "tristar_mppt",
        intelligence,
    )
    assert await store.upsert_device(device) == device_id
    record = await store.get_device_intelligence(device_id)
    assert record is not None
    assert record["model"] == "TS-MPPT-60"
    assert record["intelligence_status"] == "verified"
    assert record["capabilities"] == ["modbus_tcp"]
