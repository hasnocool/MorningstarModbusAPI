# src/morningstar_modbus/catalog/families/prostar_pwm.py
"""ProStar PWM Gen3 register catalog."""

from morningstar_modbus.catalog.common import LOAD_FAULTS, LOAD_STATES, PROSTAR_ALARMS, PWM_CHARGE_STATES
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/technical-doc-prostar-modbus-specification-en.pdf"
)

ARRAY_FAULTS = (
    (0, "overcurrent_phase_1"), (1, "fet_shorted"), (2, "software"), (3, "battery_hvd"),
    (4, "array_hvd"), (5, "eeprom_edit"), (6, "rts_shorted"), (7, "rts_disconnected"),
    (8, "local_temp_sensor_failed"), (9, "battery_lvd"), (10, "dip_changed"),
    (11, "processor_supply_fault"),
)

PROSTAR_PWM = DeviceProfileSpec(
    name="prostar_pwm",
    family="ProStar PWM Gen3",
    aliases=("prostar pwm", "ps-pwm", "prostar gen3", "prostar"),
    source_id="prostar-pwm-modbus-v2",
    source_url=SOURCE,
    detection_priority=50,
    blocks=(RegisterBlock(0x0000, 0x004D),),
    registers=(
        RegisterSpec("firmware_version", 0x0000, category="metadata"),
        RegisterSpec("system_voltage_multiplier", 0x0001, category="metadata"),
        RegisterSpec("charge_current", 0x0010, decoder="f16", unit="A"),
        RegisterSpec("array_current", 0x0011, decoder="f16", unit="A"),
        RegisterSpec("battery_terminal_voltage", 0x0012, decoder="f16", unit="V"),
        RegisterSpec("array_voltage", 0x0013, decoder="f16", unit="V"),
        RegisterSpec("load_voltage", 0x0014, decoder="f16", unit="V"),
        RegisterSpec("battery_net_current", 0x0015, decoder="f16", unit="A"),
        RegisterSpec("load_current", 0x0016, decoder="f16", unit="A"),
        RegisterSpec("battery_sense_voltage", 0x0017, decoder="f16", unit="V"),
        RegisterSpec("heatsink_temp", 0x001A, decoder="f16", unit="C"),
        RegisterSpec("battery_temp", 0x001B, decoder="f16", unit="C"),
        RegisterSpec("ambient_temp", 0x001C, decoder="f16", unit="C"),
        RegisterSpec("rts_temp", 0x001D, decoder="f16", unit="C"),
        RegisterSpec("charge_state", 0x0021, category="state", enum=PWM_CHARGE_STATES),
        RegisterSpec("array_faults", 0x0022, category="fault", bits=ARRAY_FAULTS),
        RegisterSpec("load_state", 0x002E, category="state", enum=LOAD_STATES),
        RegisterSpec("load_faults", 0x002F, category="fault", bits=LOAD_FAULTS),
        RegisterSpec("hourmeter", 0x0036, words=2, decoder="u32", unit="h"),
        RegisterSpec("alarms", 0x0038, words=2, decoder="u32", category="alarm", bits=PROSTAR_ALARMS),
        RegisterSpec("dip_switch", 0x003A, category="configuration"),
        RegisterSpec("led_state", 0x003B, category="state"),
    ),
    capabilities=("rtu", "meterbus", "charge", "load", "lighting", "device_identification"),
    network=(("baudrate", "9600"), ("default_modbus_id", "1"), ("stop_bits", "2")),
)
