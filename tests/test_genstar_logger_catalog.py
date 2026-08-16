# tests/test_genstar_logger_catalog.py
from __future__ import annotations

import math
import struct

from morningstar_modbus.catalog.families.genstar_mppt import GENSTAR_MPPT
from morningstar_modbus.catalog.scaling import float32


def test_float32_decoder_matches_ieee_single_precision() -> None:
    words = struct.unpack(">HH", struct.pack(">f", 123.5))
    assert math.isclose(float32(words), 123.5)


def test_genstar_catalog_exposes_documented_daily_and_hourly_logger_fields() -> None:
    registers = {register.name: register for register in GENSTAR_MPPT.registers}

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
    registers = {register.name: register for register in GENSTAR_MPPT.registers}

    assert registers["system_charge_kwh_daily"].address == 0x02D0
    assert registers["system_charge_ah_daily"].address == 0x02D6
    assert registers["internal_charge_kwh_daily"].address == 0x02E8
    assert registers["internal_charge_ah_daily"].address == 0x02EE
    assert registers["internal_charge_kwh_total"].decoder == "u32_factor:0.1"
    assert registers["internal_charge_ah_total"].decoder == "u32_factor:0.1"


def test_genstar_capabilities_distinguish_snmp_polling_from_traps() -> None:
    capabilities = set(GENSTAR_MPPT.capabilities)

    assert "hourly_logger_summary" in capabilities
    assert "daily_logger_summary" in capabilities
    assert "event_logger" in capabilities
    assert "sd_logging" in capabilities
    assert "snmp_polling" in capabilities
    assert "snmp_traps" not in capabilities
