# tests/test_catalog.py
import math
import struct

import pytest

from morningstar_modbus.catalog import catalog_detail, catalog_summary, detect_profile
from morningstar_modbus.catalog.registry import select_spec
from morningstar_modbus.catalog.scaling import float16
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
