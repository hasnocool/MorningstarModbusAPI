# tests/test_catalog.py
import math
import struct

import pytest

from morningstar_modbus.catalog import catalog_detail, catalog_summary, detect_profile
from morningstar_modbus.catalog.families.tristar_mppt import TRISTAR_MPPT
from morningstar_modbus.catalog.profile import CatalogProfile
from morningstar_modbus.catalog.registry import PROFILES, select_spec
from morningstar_modbus.catalog.scaling import float16
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec
from morningstar_modbus.models import DeviceIdentification


def test_family_selection_prefers_specific_products() -> None:
    assert select_spec("Morningstar Corp.", "TS-MPPT-60-600V-48").name == "tristar_mppt_600v"
    assert select_spec("Morningstar Corp.", "TriStar MPPT").name == "tristar_mppt"
    assert select_spec("Morningstar Corp.", "PS-MPPT-40").name == "prostar_mppt"
    assert select_spec("Morningstar Corp.", "SureSine300").name == "suresine_classic"
    assert select_spec("Morningstar Corp.", "GS-MPPT-100M-200V").name == "genstar_mppt"
    assert select_spec("Morningstar Corp.", "ReadyEdge RE-1").name == "readyedge"


def test_catalog_exposes_structured_family_metadata() -> None:
    names = {item["name"] for item in catalog_summary()}
    assert {
        "tristar_mppt",
        "tristar_mppt_600v",
        "tristar_pwm",
        "prostar_mppt",
        "prostar_pwm",
        "sunsaver_mppt",
        "sunsaver_duo",
        "suresine_classic",
        "suresine_gen2",
        "relay_driver",
        "genstar_mppt",
        "readyedge",
    } <= names
    detail = catalog_detail("tristar_mppt")
    assert detail is not None
    register_names = {item["name"] for item in detail["registers"]}
    assert {"serial_number", "faults", "alarms", "charge_state"} <= register_names


def test_every_named_register_is_covered_by_a_read_block() -> None:
    for spec in PROFILES:
        names = [register.name for register in spec.registers]
        assert len(names) == len(set(names)), f"duplicate register name in {spec.name}"
        for register in spec.registers:
            register_end = register.address + register.words
            assert any(
                block.function == register.function
                and block.address <= register.address
                and register_end <= block.address + block.count
                for block in spec.blocks
            ), f"{spec.name}.{register.name} is outside its declared read blocks"


def test_tristar_v11_runtime_map_names_every_documented_readonly_register() -> None:
    covered_addresses = {
        address
        for register in TRISTAR_MPPT.registers
        if register.address < 0x0050
        for address in range(register.address, register.address + register.words)
    }
    documented_runtime_addresses = (
        set(range(0x0018, 0x002D))
        | set(range(0x002E, 0x003F))
        | set(range(0x0040, 0x004A))
        | set(range(0x004B, 0x0050))
    )

    assert documented_runtime_addresses <= covered_addresses
    assert 0x002D not in covered_addresses
    assert 0x003F not in covered_addresses
    assert 0x004A not in covered_addresses
    assert all(register.description.strip() for register in TRISTAR_MPPT.registers)


def test_float16_decoder_matches_ieee_binary16() -> None:
    raw = struct.unpack(">H", struct.pack(">e", 12.5))[0]
    assert math.isclose(float16(raw), 12.5)


class SureSineGen2FingerprintClient:
    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        if (address, count) == (0x0003, 4):
            return [10000, 1200, 1200, 60]
        raise TimeoutError

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        raise TimeoutError

    async def read_device_identification(self) -> DeviceIdentification:
        return DeviceIdentification()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_read_only_fingerprint_can_identify_suresine_gen2() -> None:
    profile = await detect_profile(SureSineGen2FingerprintClient(), DeviceIdentification())
    assert profile.name == "suresine_gen2"


class NonMorningstarFingerprintClient(SureSineGen2FingerprintClient):
    def __init__(self) -> None:
        self.read_count = 0

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        self.read_count += 1
        return await super().read_holding_registers(address, count)


@pytest.mark.asyncio
async def test_explicit_non_morningstar_vendor_is_never_fingerprinted() -> None:
    client = NonMorningstarFingerprintClient()
    identity = DeviceIdentification(vendor_name="Example Controls", product_code="EC-100")
    profile = await detect_profile(client, identity)
    assert profile.name == "generic"
    assert client.read_count == 0


class RetryMetadataClient:
    def __init__(self) -> None:
        self.metadata_reads = 0

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        if (address, count) == (0x0010, 1):
            self.metadata_reads += 1
            if self.metadata_reads == 1:
                raise TimeoutError
            return [42]
        if (address, count) == (0x0020, 1):
            return [7]
        raise AssertionError((address, count))

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        raise AssertionError((address, count))

    async def read_device_identification(self) -> DeviceIdentification:
        return DeviceIdentification()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_optional_cached_metadata_retries_after_transient_failure() -> None:
    spec = DeviceProfileSpec(
        name="metadata-retry-test",
        family="test",
        aliases=(),
        source_id="test",
        source_url="https://example.invalid/test",
        blocks=(
            RegisterBlock(0x0010, 1, category="metadata", optional=True, cache=True),
            RegisterBlock(0x0020, 1),
        ),
        registers=(
            RegisterSpec("metadata_value", 0x0010, category="metadata"),
            RegisterSpec("telemetry_value", 0x0020),
        ),
    )
    client = RetryMetadataClient()
    profile = CatalogProfile(spec)

    first = {value.name: value.value for value in await profile.poll(client)}
    second = {value.name: value.value for value in await profile.poll(client)}

    assert "metadata_value" not in first
    assert second["metadata_value"] == 42
    assert second["telemetry_value"] == 7
    assert client.metadata_reads == 2
