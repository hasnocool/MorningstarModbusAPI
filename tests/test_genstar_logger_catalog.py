# tests/test_genstar_logger_catalog.py
from __future__ import annotations

import math
import struct

from morningstar_modbus.catalog import get_profile
from morningstar_modbus.catalog.scaling import decode_value, float32


def _genstar():
    return get_profile("genstar_mppt").spec


def test_float32_decoder_matches_ieee_single_precision() -> None:
    words = struct.unpack(">HH", struct.pack(">f", 123.5))
    assert math.isclose(float32(words), 123.5)


def test_signed_32_factor_decoder_preserves_negative_battery_counters() -> None:
    assert decode_value("s32_factor:0.1", (0xFFFF, 0xFF9C), {}) == -10.0
    assert decode_value("s32_factor:0.1", (0x0000, 0x0064), {}) == 10.0


def test_genstar_catalog_exposes_documented_daily_and_hourly_logger_fields() -> None:
    registers = {register.name: register for register in _genstar().registers}

    assert registers["battery_voltage_min_hourly"].address == 0x026A
    assert registers["battery_voltage_max_hourly"].address == 0x026B
    assert registers["battery_voltage_min_daily"].address == 0x026C
    assert registers["battery_voltage_max_daily"].address == 0x026D
    assert registers["array_voltage_max_daily"].address == 0x026E
    assert registers["output_power_max_daily"].address == 0x0271
    assert registers["absorption_seconds_daily"].decoder == "f32"
    assert registers["equalize_seconds_daily"].decoder == "f32"
    assert registers["float_seconds_daily"].decoder == "f32"


def test_genstar_catalog_exposes_local_and_system_charge_counters() -> None:
    registers = {register.name: register for register in _genstar().registers}

    assert registers["system_charge_kwh_daily"].address == 0x02D0
    assert registers["system_charge_ah_daily"].address == 0x02D6
    assert registers["internal_charge_kwh_daily"].address == 0x02E8
    assert registers["internal_charge_ah_daily"].address == 0x02EE
    assert registers["internal_charge_kwh_total"].decoder == "u32_factor:0.1"
    assert registers["internal_charge_ah_total"].decoder == "u32_factor:0.1"


def test_genstar_catalog_completes_system_and_internal_battery_load_counters() -> None:
    profile = _genstar()
    registers = {register.name: register for register in profile.registers}
    blocks = {block.address: block for block in profile.blocks}

    assert blocks[0x02D0].count == 0x0018
    assert blocks[0x02E8].count == 0x0018

    assert registers["system_battery_ah_daily"].address == 0x02DC
    assert registers["system_battery_ah_resettable"].decoder == "s32_factor:0.1"
    assert registers["system_battery_ah_total"].address == 0x02E0
    assert registers["system_load_ah_daily"].address == 0x02E2
    assert registers["system_load_ah_total"].address == 0x02E6

    assert registers["internal_battery_ah_daily"].address == 0x02F4
    assert registers["internal_battery_ah_resettable"].decoder == "s32_factor:0.1"
    assert registers["internal_battery_ah_total"].address == 0x02F8
    assert registers["internal_load_ah_daily"].address == 0x02FA
    assert registers["internal_load_ah_total"].address == 0x02FE


def test_genstar_catalog_exposes_aggregated_shunt_counters_as_optional_block() -> None:
    profile = _genstar()
    registers = {register.name: register for register in profile.registers}
    blocks = {block.address: block for block in profile.blocks}

    assert blocks[0x227C].count == 0x0018
    assert blocks[0x227C].optional is True
    assert registers["aggregated_shunt_charge_ah_daily"].address == 0x227C
    assert registers["aggregated_shunt_charge_kwh_daily"].address == 0x2282
    assert registers["aggregated_shunt_battery_ah_daily"].address == 0x2288
    assert registers["aggregated_shunt_battery_ah_total"].decoder == "s32_factor:0.1"
    assert registers["aggregated_shunt_load_ah_daily"].address == 0x228E
    assert registers["aggregated_shunt_load_ah_total"].address == 0x2292


def test_genstar_capabilities_distinguish_snmp_polling_from_traps() -> None:
    capabilities = set(_genstar().capabilities)

    assert "hourly_logger_summary" in capabilities
    assert "daily_logger_summary" in capabilities
    assert "event_logger" in capabilities
    assert "sd_logging" in capabilities
    assert "snmp_polling" in capabilities
    assert "system_battery_counters" in capabilities
    assert "system_load_counters" in capabilities
    assert "aggregated_shunt_counters" in capabilities
    assert "snmp_traps" not in capabilities
