# src/morningstar_modbus/catalog/families/suresine_classic.py
"""SureSine Classic 300W register catalog."""

from morningstar_modbus.catalog.common import SURESINE_CLASSIC_LOAD_STATES
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/technical-doc-suresine-modbus-specification-en.pdf"
)

FAULTS = (
    (0, "reset"), (1, "overcurrent"), (3, "software"), (4, "hvd"),
    (5, "heatsink_overtemp"), (6, "dip_changed"), (7, "settings_edit"),
)
ALARMS = (
    (0, "heatsink_sensor_open"), (1, "heatsink_sensor_short"), (3, "heatsink_hot"),
)

SURESINE_CLASSIC = DeviceProfileSpec(
    name="suresine_classic",
    family="SureSine Classic 300W",
    aliases=("suresine300", "suresine 300", "suresine classic"),
    source_id="suresine-classic-modbus-v03",
    source_url=SOURCE,
    detection_priority=80,
    blocks=(
        RegisterBlock(0x0000, 0x0011),
        RegisterBlock(0xE002, 2, category="network", optional=True, cache=True),
        RegisterBlock(0xE044, 4, category="metadata", optional=True, cache=True),
    ),
    registers=(
        RegisterSpec("battery_voltage_raw", 0x0000, decoder="ufactor:0.0002581787109375", unit="V"),
        RegisterSpec("ac_output_current_raw", 0x0001, decoder="suresine_classic_current", unit="A"),
        RegisterSpec("battery_voltage", 0x0004, decoder="ufactor:0.0002581787109375", unit="V"),
        RegisterSpec("ac_output_current", 0x0005, decoder="suresine_classic_current", unit="A"),
        RegisterSpec("heatsink_temp", 0x0006, decoder="s16", unit="C"),
        RegisterSpec("faults", 0x0007, category="fault", bits=FAULTS),
        RegisterSpec("alarms", 0x0008, category="alarm", bits=ALARMS),
        RegisterSpec("dip_switch", 0x000A, category="configuration"),
        RegisterSpec("load_state", 0x000B, category="state", enum=SURESINE_CLASSIC_LOAD_STATES),
        RegisterSpec("modulation_index", 0x000C, decoder="percent:256", unit="%"),
        RegisterSpec("ac_output_voltage", 0x000D, unit="V"),
        RegisterSpec("ac_output_frequency", 0x000E, unit="Hz"),
        RegisterSpec("modbus_id", 0xE002, category="network"),
        RegisterSpec("meterbus_id", 0xE003, category="network"),
        RegisterSpec("serial_number", 0xE044, words=4, decoder="ascii_lo_hi", category="metadata"),
    ),
    capabilities=("rtu", "meterbus", "inverter", "device_identification"),
    network=(("baudrate", "9600"), ("default_modbus_id", "1"), ("stop_bits", "2")),
)
