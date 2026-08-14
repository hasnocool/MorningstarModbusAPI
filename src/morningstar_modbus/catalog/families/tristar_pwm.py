# src/morningstar_modbus/catalog/families/tristar_pwm.py
"""TriStar PWM register catalog."""

from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-modbus-specification-en.pdf"
)

CONTROL_MODES = ((0, "CHARGE"), (1, "LOAD"), (2, "DIVERSION"), (3, "LIGHTING"))
CHARGE_STATES = (
    (0, "START"), (1, "NIGHT_CHECK"), (2, "DISCONNECT"), (3, "NIGHT"), (4, "FAULT"),
    (5, "BULK"), (6, "PWM"), (7, "FLOAT"), (8, "EQUALIZE"),
)
FAULTS = (
    (0, "external_short"), (1, "overcurrent"), (2, "fet_shorted"), (3, "software"),
    (4, "hvd"), (5, "controller_hot"), (6, "dip_changed"), (7, "settings_edit"),
    (8, "reset"), (9, "miswire"), (10, "rts_shorted"), (11, "rts_disconnected"),
)
ALARMS = (
    (0, "rts_open"), (1, "rts_short"), (2, "rts_disconnected"), (3, "heatsink_sensor_open"),
    (4, "heatsink_sensor_short"), (5, "controller_hot"), (6, "current_limit"),
    (7, "current_offset"), (8, "battery_sense"), (9, "battery_sense_disconnected"),
    (10, "uncalibrated"), (11, "rts_miswire"), (12, "hvd"), (13, "high_duty"),
    (14, "miswire"), (15, "fet_open"), (16, "p12"), (17, "load_disconnect"),
)

TRISTAR_PWM = DeviceProfileSpec(
    name="tristar_pwm",
    family="TriStar PWM",
    aliases=("tristar pwm", "tristar-45", "tristar-60", "ts-45", "ts-60", "tristar"),
    source_id="tristar-pwm-modbus-v07",
    source_url=SOURCE,
    detection_priority=30,
    blocks=(
        RegisterBlock(0x0008, 0x0016),
        RegisterBlock(0xF000, 0x000C, category="metadata", optional=True, cache=True),
    ),
    registers=(
        RegisterSpec("battery_voltage", 0x0008, decoder="factor:0.002950897216796875", unit="V"),
        RegisterSpec("battery_sense_voltage", 0x0009, decoder="factor:0.002950897216796875", unit="V"),
        RegisterSpec("array_or_load_voltage", 0x000A, decoder="factor:0.00424652099609375", unit="V"),
        RegisterSpec("charge_current", 0x000B, decoder="factor:0.002034515380859375", unit="A"),
        RegisterSpec("load_current", 0x000C, decoder="factor:0.0096649169921875", unit="A"),
        RegisterSpec("battery_voltage_slow", 0x000D, decoder="factor:0.002950897216796875", unit="V"),
        RegisterSpec("heatsink_temp", 0x000E, decoder="s16", unit="C"),
        RegisterSpec("battery_temp", 0x000F, decoder="s16", unit="C"),
        RegisterSpec("target_voltage", 0x0010, decoder="factor:0.002950897216796875", unit="V"),
        RegisterSpec("alarm_low", 0x0017, category="alarm", bits=ALARMS),
        RegisterSpec("faults", 0x0018, category="fault", bits=FAULTS),
        RegisterSpec("dip_switch", 0x0019, category="configuration"),
        RegisterSpec("control_mode", 0x001A, category="state", enum=CONTROL_MODES),
        RegisterSpec("control_state", 0x001B, category="state", enum=CHARGE_STATES),
        RegisterSpec("duty_cycle", 0x001C, decoder="percent:230", unit="%"),
        RegisterSpec("alarm_high", 0x001D, category="alarm"),
        RegisterSpec("serial_number", 0xF000, words=4, decoder="ascii_lo_hi", category="metadata"),
        RegisterSpec("hardware_version", 0xF00A, category="metadata"),
        RegisterSpec("model_flag", 0xF00B, category="metadata", enum=((0, "TS-45"), (1, "TS-60"))),
    ),
    capabilities=("rtu", "rs232", "eia485", "charge", "load", "diversion", "lighting"),
    network=(("baudrate", "9600"), ("default_modbus_id", "1"), ("stop_bits", "2")),
)
