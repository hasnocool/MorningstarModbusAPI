# src/morningstar_modbus/catalog/families/sunsaver_duo.py
"""SunSaver Duo register catalog."""

from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-sunsaver-duo-modbus-specification-en.pdf"
)

STATES = ((1, "NORMAL"), (3, "NIGHT"), (4, "FAULT"))
FAULTS = (
    (0, "reverse_polarity_solar"), (1, "reverse_polarity_battery_1"),
    (2, "reverse_polarity_battery_2"), (3, "local_temp_sensor_damaged"),
    (4, "rts_damaged_or_removed"), (5, "overcurrent"),
    (6, "high_temperature_disconnect"), (7, "hvd"),
)
FLAGS = (
    (0, "internal_0"), (1, "internal_1"), (2, "internal_2"), (3, "regulation"),
    (4, "valid_rts"), (5, "alternating"), (6, "on_off_regulation"), (7, "started"),
)

SUNSAVER_DUO = DeviceProfileSpec(
    name="sunsaver_duo",
    family="SunSaver Duo",
    aliases=("sunsaver duo", "ssd", "sunsaverduo"),
    source_id="sunsaver-duo-modbus-v04",
    source_url=SOURCE,
    detection_priority=70,
    blocks=(RegisterBlock(0x0000, 0x0010), RegisterBlock(0x0106, 0x0006)),
    registers=(
        RegisterSpec("battery_1_voltage", 0x0000, decoder="udivide:1800", unit="V"),
        RegisterSpec("battery_2_voltage", 0x0001, decoder="udivide:1800", unit="V"),
        RegisterSpec("array_voltage", 0x0002, decoder="udivide:1032", unit="V"),
        RegisterSpec("array_current_1", 0x0003, decoder="udivide:673", unit="A"),
        RegisterSpec("array_current_2", 0x0004, decoder="udivide:673", unit="A"),
        RegisterSpec("target_voltage_1", 0x0008, decoder="udivide:1800", unit="V"),
        RegisterSpec("target_voltage_2", 0x0009, decoder="udivide:1800", unit="V"),
        RegisterSpec("duty_cycle_1", 0x000A, decoder="percent:417", unit="%"),
        RegisterSpec("duty_cycle_2", 0x000B, decoder="percent:417", unit="%"),
        RegisterSpec("duty_cycle_1_control", 0x0106, decoder="percent:417", unit="%"),
        RegisterSpec("duty_cycle_2_control", 0x0107, decoder="percent:417", unit="%"),
        RegisterSpec("state", 0x0108, category="state", enum=STATES),
        RegisterSpec("faults", 0x0109, category="fault", bits=FAULTS),
        RegisterSpec("flags", 0x010A, category="state", bits=FLAGS),
        RegisterSpec("dip_switch", 0x010B, category="configuration"),
    ),
    capabilities=("rtu", "meterbus", "dual_battery", "charge", "device_identification"),
    network=(("baudrate", "9600"), ("default_modbus_id", "1"), ("stop_bits", "2")),
)
