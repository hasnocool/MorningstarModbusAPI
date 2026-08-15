"""TriStar MPPT 150V register catalog."""

from morningstar_modbus.catalog.common import (
    TRISTAR_MPPT_ALARMS,
    TRISTAR_MPPT_CHARGE_STATES,
    TRISTAR_MPPT_FAULTS,
)
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-tristar-mppt-modbus-specification-en.pdf"
)

TRISTAR_MPPT = DeviceProfileSpec(
    name="tristar_mppt",
    family="TriStar MPPT 150V",
    aliases=("tristar mppt", "ts-mppt-45", "ts-mppt-60", "tsmppt"),
    source_id="tristar-mppt-modbus-v11",
    source_url=SOURCE,
    detection_priority=20,
    blocks=(
        RegisterBlock(0x0000, 0x0050),
        RegisterBlock(0xE0C0, 0x000E, category="metadata", optional=True, cache=True),
    ),
    registers=(
        RegisterSpec("voltage_scale_hi", 0x0000, category="metadata"),
        RegisterSpec("voltage_scale_lo", 0x0001, category="metadata"),
        RegisterSpec("current_scale_hi", 0x0002, category="metadata"),
        RegisterSpec("current_scale_lo", 0x0003, category="metadata"),
        RegisterSpec("firmware_version", 0x0004, decoder="bcd", category="metadata"),
        RegisterSpec("battery_voltage", 0x0018, decoder="tristar_voltage", unit="V"),
        RegisterSpec("battery_terminal_voltage", 0x0019, decoder="tristar_voltage", unit="V"),
        RegisterSpec("battery_sense_voltage", 0x001A, decoder="tristar_voltage", unit="V"),
        RegisterSpec("array_voltage", 0x001B, decoder="tristar_voltage", unit="V"),
        RegisterSpec("battery_charge_current", 0x001C, decoder="tristar_current", unit="A"),
        RegisterSpec("array_current", 0x001D, decoder="tristar_current", unit="A"),
        RegisterSpec("heatsink_temp", 0x0023, decoder="s16", unit="C"),
        RegisterSpec("rts_temp", 0x0024, decoder="s16", unit="C"),
        RegisterSpec("battery_temp", 0x0025, decoder="s16", unit="C"),
        RegisterSpec("faults", 0x002C, category="fault", bits=TRISTAR_MPPT_FAULTS),
        RegisterSpec("alarms", 0x002E, words=2, decoder="u32", category="alarm", bits=TRISTAR_MPPT_ALARMS),
        RegisterSpec("charge_state", 0x0032, category="state", enum=TRISTAR_MPPT_CHARGE_STATES),
        RegisterSpec("target_voltage", 0x0033, decoder="tristar_voltage", unit="V"),
        RegisterSpec("output_power", 0x003A, decoder="tristar_power", unit="W"),
        RegisterSpec("input_power", 0x003B, decoder="tristar_power", unit="W"),
        RegisterSpec("daily_charge_wh", 0x0044, unit="Wh"),
        RegisterSpec("serial_number", 0xE0C0, words=4, decoder="ascii_lo_hi", category="metadata"),
        RegisterSpec("model_flag", 0xE0CC, category="metadata", enum=((0, "TS-MPPT-45"), (1, "TS-MPPT-60"))),
        RegisterSpec("hardware_version", 0xE0CD, category="metadata"),
    ),
    capabilities=("rtu", "rs232", "eia485", "modbus_tcp", "ethernet", "device_identification"),
    network=(
        ("tcp_port", "502"),
        ("default_modbus_id", "1"),
        ("dhcp", "enabled"),
        ("fallback_ip", "192.168.1.253"),
        ("netbios", "tsmppt<serial>"),
    ),
)
