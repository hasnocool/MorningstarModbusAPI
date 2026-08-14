# src/morningstar_modbus/catalog/families/suresine_gen2.py
"""SureSine Gen2 register catalog."""

from morningstar_modbus.catalog.common import SURESINE_GEN2_LED_STATES
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/technical-doc-suresine-2-modbus-specification-en.pdf"
)

LOAD_STATE_BITS = (
    (0, "manual_power_on"), (1, "manual_power_off"), (2, "remote_switch_on"),
    (3, "remote_switch_off"), (4, "fault_power_off"), (5, "timed_auto_on"),
    (6, "timed_auto_off"), (7, "low_consumption_on"), (8, "low_consumption_off"),
    (9, "overload"), (10, "short_circuit"), (11, "hvd_fault"), (12, "lvd_fault"),
    (13, "high_temperature_fault"), (14, "comm_command_off"), (15, "comm_command_on"),
)
FAULTS = (
    (1, "ac_overcurrent"), (2, "ac_short"), (3, "hvd"), (4, "lvd"),
    (5, "heatsink_overtemp_disconnect"), (6, "inverter_fault"),
)
ALARMS = (
    (0, "heatsink_sensor_disconnected"), (1, "heatsink_sensor_short"),
    (2, "ambient_sensor_disconnected"),
)

SURESINE_GEN2 = DeviceProfileSpec(
    name="suresine_gen2",
    family="SureSine Gen2",
    aliases=("suresine gen2", "suresine 2", "suresine2", "suresine-2"),
    source_id="suresine-gen2-modbus",
    source_url=SOURCE,
    detection_priority=5,
    blocks=(RegisterBlock(0x0003, 0x0014), RegisterBlock(0x0051, 0x000F)),
    registers=(
        RegisterSpec("rated_power", 0x0003, decoder="ufactor:0.1", unit="W", category="metadata"),
        RegisterSpec("nominal_dc_voltage", 0x0004, decoder="ufactor:0.01", unit="V", category="metadata"),
        RegisterSpec("ac_output_rating", 0x0005, decoder="ufactor:0.1", unit="V", category="metadata"),
        RegisterSpec("ac_frequency_rating", 0x0006, unit="Hz", category="metadata"),
        RegisterSpec("remote_status", 0x0007, category="state"),
        RegisterSpec("battery_voltage", 0x0008, decoder="ufactor:0.01", unit="V"),
        RegisterSpec("battery_current", 0x0009, decoder="factor:0.01", unit="A"),
        RegisterSpec("ac_output_voltage", 0x000A, decoder="ufactor:0.1", unit="V"),
        RegisterSpec("ac_output_current", 0x000B, decoder="ufactor:0.01", unit="A"),
        RegisterSpec("heatsink_temp", 0x000C, decoder="s16", unit="C"),
        RegisterSpec("internal_temp", 0x000E, decoder="s16", unit="C"),
        RegisterSpec("dip_switch", 0x000F, category="configuration"),
        RegisterSpec("load_state", 0x0010, category="state", bits=LOAD_STATE_BITS),
        RegisterSpec("heatsink_temp_status", 0x0012, category="state"),
        RegisterSpec("ambient_temp_status", 0x0014, category="state"),
        RegisterSpec("faults", 0x0015, category="fault", bits=FAULTS),
        RegisterSpec("alarms", 0x0016, category="alarm", bits=ALARMS),
        RegisterSpec("total_energy", 0x0051, words=2, decoder="u32", unit="Wh"),
        RegisterSpec("run_state", 0x005C, category="state", enum=((0, "AC_OFF"), (1, "AC_ON"))),
        RegisterSpec("led_state", 0x005D, category="state", enum=SURESINE_GEN2_LED_STATES),
        RegisterSpec("instantaneous_power", 0x005E, decoder="ufactor:0.1", unit="W"),
        RegisterSpec("relay_state", 0x005F, category="state"),
    ),
    capabilities=("rtu", "eia485", "inverter", "modbus_tcp", "ethernet", "device_identification"),
    network=(
        ("default_modbus_id", "1"), ("baudrate", "9600"), ("stop_bits", "2"),
        ("tcp_models", "700W-2500W"), ("tcp_port", "502"), ("fallback_ip", "192.168.1.253"),
    ),
)
