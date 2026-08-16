"""Source-backed GenStar MPPT system/battery/load and ReadyShunt counters.

Morningstar's GenStar V03 map extends the previously cataloged charge counters
with system battery/load counters, controller-local battery/load counters, and
an optional aggregated-shunt counter block.  Keep the base family readable and
layer the additional immutable declarations here so registry consumers see one
enhanced profile without duplicating the rest of the GenStar map.
"""

from __future__ import annotations

from dataclasses import replace

from morningstar_modbus.catalog.families.genstar_mppt import GENSTAR_MPPT as BASE_GENSTAR_MPPT
from morningstar_modbus.catalog.types import RegisterBlock, RegisterSpec

_BLOCK_REPLACEMENTS = {
    0x02D0: RegisterBlock(0x02D0, 0x0018),
    0x02E8: RegisterBlock(0x02E8, 0x0018),
}

_SYSTEM_METERING_REGISTERS = (
    RegisterSpec(
        "system_battery_ah_daily",
        0x02DC,
        words=2,
        decoder="f32",
        unit="Ah",
        description="System battery net amp-hours accumulated today.",
    ),
    RegisterSpec(
        "system_battery_ah_resettable",
        0x02DE,
        words=2,
        decoder="s32_factor:0.1",
        unit="Ah",
        description="System resettable signed battery net amp-hour counter.",
    ),
    RegisterSpec(
        "system_battery_ah_total",
        0x02E0,
        words=2,
        decoder="s32_factor:0.1",
        unit="Ah",
        description="System lifetime signed battery net amp-hour counter.",
    ),
    RegisterSpec(
        "system_load_ah_daily",
        0x02E2,
        words=2,
        decoder="f32",
        unit="Ah",
        description="System load amp-hours accumulated today.",
    ),
    RegisterSpec(
        "system_load_ah_resettable",
        0x02E4,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="System resettable load amp-hour counter.",
    ),
    RegisterSpec(
        "system_load_ah_total",
        0x02E6,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="System lifetime load amp-hour counter.",
    ),
    RegisterSpec(
        "internal_battery_ah_daily",
        0x02F4,
        words=2,
        decoder="f32",
        unit="Ah",
        description="Controller-local signed battery net amp-hours accumulated today.",
    ),
    RegisterSpec(
        "internal_battery_ah_resettable",
        0x02F6,
        words=2,
        decoder="s32_factor:0.1",
        unit="Ah",
        description="Controller-local resettable signed battery net amp-hour counter.",
    ),
    RegisterSpec(
        "internal_battery_ah_total",
        0x02F8,
        words=2,
        decoder="s32_factor:0.1",
        unit="Ah",
        description="Controller-local lifetime signed battery net amp-hour counter.",
    ),
    RegisterSpec(
        "internal_load_ah_daily",
        0x02FA,
        words=2,
        decoder="f32",
        unit="Ah",
        description="Controller-local load amp-hours accumulated today.",
    ),
    RegisterSpec(
        "internal_load_ah_resettable",
        0x02FC,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="Controller-local resettable load amp-hour counter.",
    ),
    RegisterSpec(
        "internal_load_ah_total",
        0x02FE,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="Controller-local lifetime load amp-hour counter.",
    ),
    RegisterSpec(
        "aggregated_shunt_charge_ah_daily",
        0x227C,
        words=2,
        decoder="f32",
        unit="Ah",
        description="Aggregated external-source shunt charge amp-hours for today.",
    ),
    RegisterSpec(
        "aggregated_shunt_charge_ah_resettable",
        0x227E,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="Aggregated external-source shunt resettable charge amp-hours.",
    ),
    RegisterSpec(
        "aggregated_shunt_charge_ah_total",
        0x2280,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="Aggregated external-source shunt lifetime charge amp-hours.",
    ),
    RegisterSpec(
        "aggregated_shunt_charge_kwh_daily",
        0x2282,
        words=2,
        decoder="f32",
        unit="kWh",
        description="Aggregated external-source shunt charge energy for today.",
    ),
    RegisterSpec(
        "aggregated_shunt_charge_kwh_resettable",
        0x2284,
        words=2,
        decoder="u32_factor:0.1",
        unit="kWh",
        description="Aggregated external-source shunt resettable charge energy.",
    ),
    RegisterSpec(
        "aggregated_shunt_charge_kwh_total",
        0x2286,
        words=2,
        decoder="u32_factor:0.1",
        unit="kWh",
        description="Aggregated external-source shunt lifetime charge energy.",
    ),
    RegisterSpec(
        "aggregated_shunt_battery_ah_daily",
        0x2288,
        words=2,
        decoder="f32",
        unit="Ah",
        description="Aggregated shunt battery net amp-hours for today.",
    ),
    RegisterSpec(
        "aggregated_shunt_battery_ah_resettable",
        0x228A,
        words=2,
        decoder="s32_factor:0.1",
        unit="Ah",
        description="Aggregated shunt resettable signed battery net amp-hours.",
    ),
    RegisterSpec(
        "aggregated_shunt_battery_ah_total",
        0x228C,
        words=2,
        decoder="s32_factor:0.1",
        unit="Ah",
        description="Aggregated shunt lifetime signed battery net amp-hours.",
    ),
    RegisterSpec(
        "aggregated_shunt_load_ah_daily",
        0x228E,
        words=2,
        decoder="f32",
        unit="Ah",
        description="Aggregated shunt load amp-hours for today.",
    ),
    RegisterSpec(
        "aggregated_shunt_load_ah_resettable",
        0x2290,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="Aggregated shunt resettable load amp-hours.",
    ),
    RegisterSpec(
        "aggregated_shunt_load_ah_total",
        0x2292,
        words=2,
        decoder="u32_factor:0.1",
        unit="Ah",
        description="Aggregated shunt lifetime load amp-hours.",
    ),
)


def _enhanced_blocks() -> tuple[RegisterBlock, ...]:
    blocks = tuple(
        _BLOCK_REPLACEMENTS.get(block.address, block)
        for block in BASE_GENSTAR_MPPT.blocks
    )
    if not any(block.address == 0x227C for block in blocks):
        blocks += (
            RegisterBlock(
                0x227C,
                0x0018,
                optional=True,
            ),
        )
    return blocks


GENSTAR_MPPT = replace(
    BASE_GENSTAR_MPPT,
    blocks=_enhanced_blocks(),
    registers=BASE_GENSTAR_MPPT.registers + _SYSTEM_METERING_REGISTERS,
    capabilities=BASE_GENSTAR_MPPT.capabilities
    + (
        "system_battery_counters",
        "system_load_counters",
        "aggregated_shunt_counters",
    ),
)
