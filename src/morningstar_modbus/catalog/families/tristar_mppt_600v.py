# src/morningstar_modbus/catalog/families/tristar_mppt_600v.py
"""TriStar MPPT 600V register catalog."""

from morningstar_modbus.catalog.common import TRISTAR_MPPT_CHARGE_STATES, TRISTAR_MPPT_FAULTS
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-tristar-mppt-600v-modbus-specification-en.pdf"
)

TRISTAR_MPPT_600V = DeviceProfileSpec(
    name="tristar_mppt_600v",
    family="TriStar MPPT 600V",
    aliases=("tristar mppt 600v", "ts-mppt-60-600v", "tsmppt600v"),
    source_id="tristar-mppt-600v-modbus",
    source_url=SOURCE,
    detection_priority=10,
    blocks=(RegisterBlock(0x0000, 0x0050),),
    registers=(
        RegisterSpec("voltage_scale_hi", 0x0000, category="metadata"),
        RegisterSpec("voltage_scale_lo", 0x0001, category="metadata"),
        RegisterSpec("current_scale_hi", 0x0002, category="metadata"),
        RegisterSpec("current_scale_lo", 0x0003, category="metadata"),
        RegisterSpec("firmware_version", 0x0004, decoder="bcd", category="metadata"),
        RegisterSpec("fpga_version", 0x0005, decoder="bcd", category="metadata"),
        RegisterSpec("system_voltage_multiplier", 0x0006, category="metadata"),
        RegisterSpec("battery_voltage", 0x0018, decoder="ts600_voltage", unit="V"),
        RegisterSpec("battery_terminal_voltage", 0x0019, decoder="ts600_voltage", unit="V"),
        RegisterSpec("battery_sense_voltage", 0x001A, decoder="ts600_voltage", unit="V"),
        RegisterSpec("array_voltage", 0x001B, decoder="ts600_voltage", unit="V"),
        RegisterSpec("battery_charge_current", 0x001C, decoder="ts600_current", unit="A"),
        RegisterSpec("array_current", 0x001D, decoder="ts600_current", unit="A"),
        RegisterSpec("faults", 0x002C, category="fault", bits=TRISTAR_MPPT_FAULTS),
        RegisterSpec("charge_state", 0x0032, category="state", enum=TRISTAR_MPPT_CHARGE_STATES),
    ),
    capabilities=("rtu", "rs232", "eia485", "modbus_tcp", "ethernet"),
    network=(
        ("tcp_port", "502"),
        ("default_modbus_id", "1"),
        ("dhcp", "enabled"),
        ("fallback_ip", "192.168.1.253"),
        ("netbios", "tsmppt600v<serial>"),
    ),
    notes="Firmware 19+ telemetry uses Float16; older firmware is decoded with legacy per-unit scaling.",
)
