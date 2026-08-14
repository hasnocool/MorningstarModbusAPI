# src/morningstar_modbus/catalog/families/prostar_mppt.py
"""ProStar MPPT register catalog."""

from morningstar_modbus.catalog.common import (
    LOAD_FAULTS,
    LOAD_STATES,
    PROSTAR_ALARMS,
    PROSTAR_MPPT_ARRAY_FAULTS,
    PROSTAR_MPPT_CHARGE_STATES,
)
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-prostar-mppt-modbus-specification-en-1.pdf"
)

PROSTAR_MPPT = DeviceProfileSpec(
    name="prostar_mppt",
    family="ProStar MPPT",
    aliases=("prostar mppt", "ps-mppt", "psmppt"),
    source_id="prostar-mppt-modbus-v05",
    source_url=SOURCE,
    detection_priority=40,
    blocks=(
        RegisterBlock(0x0000, 0x0052),
        RegisterBlock(0xE034, 2, category="network", optional=True, cache=True),
    ),
    registers=(
        RegisterSpec("firmware_version", 0x0000, category="metadata"),
        RegisterSpec("system_voltage_multiplier", 0x0001, category="metadata"),
        RegisterSpec("supply_3v3", 0x0004, decoder="f16", unit="V"),
        RegisterSpec("supply_12v", 0x0005, decoder="f16", unit="V"),
        RegisterSpec("supply_5v", 0x0006, decoder="f16", unit="V"),
        RegisterSpec("gate_drive_voltage", 0x0007, decoder="f16", unit="V"),
        RegisterSpec("meterbus_supply_voltage", 0x0008, decoder="f16", unit="V"),
        RegisterSpec("charge_current", 0x0010, decoder="f16", unit="A"),
        RegisterSpec("array_current", 0x0011, decoder="f16", unit="A"),
        RegisterSpec("battery_terminal_voltage", 0x0012, decoder="f16", unit="V"),
        RegisterSpec("array_voltage", 0x0013, decoder="f16", unit="V"),
        RegisterSpec("load_voltage", 0x0014, decoder="f16", unit="V"),
        RegisterSpec("battery_net_current", 0x0015, decoder="f16", unit="A"),
        RegisterSpec("load_current", 0x0016, decoder="f16", unit="A"),
        RegisterSpec("battery_sense_voltage", 0x0017, decoder="f16", unit="V"),
        RegisterSpec("battery_voltage_60s", 0x0018, decoder="f16", unit="V"),
        RegisterSpec("battery_current_60s", 0x0019, decoder="f16", unit="A"),
        RegisterSpec("heatsink_temp", 0x001A, decoder="f16", unit="C"),
        RegisterSpec("battery_temp", 0x001B, decoder="f16", unit="C"),
        RegisterSpec("ambient_temp", 0x001C, decoder="f16", unit="C"),
        RegisterSpec("rts_temp", 0x001D, decoder="f16", unit="C"),
        RegisterSpec("charge_state", 0x0021, category="state", enum=PROSTAR_MPPT_CHARGE_STATES),
        RegisterSpec("array_faults", 0x0022, category="fault", bits=PROSTAR_MPPT_ARRAY_FAULTS),
        RegisterSpec("target_voltage", 0x0024, decoder="f16", unit="V"),
        RegisterSpec("load_state", 0x002E, category="state", enum=LOAD_STATES),
        RegisterSpec("load_faults", 0x002F, category="fault", bits=LOAD_FAULTS),
        RegisterSpec("hourmeter", 0x0036, words=2, decoder="u32", unit="h"),
        RegisterSpec("alarms", 0x0038, words=2, decoder="u32", category="alarm", bits=PROSTAR_ALARMS),
        RegisterSpec("dip_switch", 0x003A, category="configuration"),
        RegisterSpec("led_state", 0x003B, category="state"),
        RegisterSpec("output_power", 0x003C, decoder="f16", unit="W"),
        RegisterSpec("vmp", 0x003D, decoder="f16", unit="V"),
        RegisterSpec("pmax", 0x003E, decoder="f16", unit="W"),
        RegisterSpec("voc", 0x003F, decoder="f16", unit="V"),
        RegisterSpec("modbus_id", 0xE034, category="network"),
        RegisterSpec("meterbus_id", 0xE035, category="network"),
    ),
    capabilities=("rtu", "meterbus", "charge", "load", "lighting", "device_identification"),
    network=(("baudrate", "9600"), ("default_modbus_id", "1"), ("stop_bits", "2")),
)
