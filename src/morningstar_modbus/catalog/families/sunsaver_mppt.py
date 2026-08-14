# src/morningstar_modbus/catalog/families/sunsaver_mppt.py
"""SunSaver MPPT register catalog."""

from morningstar_modbus.catalog.common import (
    LOAD_FAULTS,
    LOAD_STATES,
    PWM_CHARGE_STATES,
    SUNSAVER_MPPT_ALARMS,
)
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-sunsaver-mppt-modbus-specification-en.pdf"
)

ARRAY_FAULTS = (
    (0, "overcurrent"), (1, "fet_shorted"), (2, "software"), (3, "battery_hvd"),
    (4, "array_hvd"), (5, "eeprom_edit"), (6, "rts_shorted"), (7, "rts_disconnected"),
    (8, "local_temp_sensor_failed"),
)

SUNSAVER_MPPT = DeviceProfileSpec(
    name="sunsaver_mppt",
    family="SunSaver MPPT",
    aliases=("sunsaver mppt", "ss-mppt", "ssmppt"),
    source_id="sunsaver-mppt-modbus-v11",
    source_url=SOURCE,
    detection_priority=60,
    blocks=(RegisterBlock(0x0008, 0x0033),),
    registers=(
        RegisterSpec("battery_voltage", 0x0008, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("array_voltage", 0x0009, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("load_voltage", 0x000A, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("charge_current", 0x000B, decoder="factor:0.0024169921875", unit="A"),
        RegisterSpec("load_current", 0x000C, decoder="factor:0.0024169921875", unit="A"),
        RegisterSpec("heatsink_temp", 0x000D, decoder="s16", unit="C"),
        RegisterSpec("battery_temp", 0x000E, decoder="s16", unit="C"),
        RegisterSpec("ambient_temp", 0x000F, decoder="s16", unit="C"),
        RegisterSpec("rts_temp", 0x0010, decoder="s16", unit="C"),
        RegisterSpec("charge_state", 0x0011, category="state", enum=PWM_CHARGE_STATES),
        RegisterSpec("array_faults", 0x0012, category="fault", bits=ARRAY_FAULTS),
        RegisterSpec("battery_voltage_slow", 0x0013, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("target_voltage", 0x0014, decoder="factor:0.002950897216796875", unit="V"),
        RegisterSpec("load_state", 0x001A, category="state", enum=LOAD_STATES),
        RegisterSpec("load_faults", 0x001B, category="fault", bits=LOAD_FAULTS),
        RegisterSpec("hourmeter", 0x0021, words=2, decoder="u32", unit="h"),
        RegisterSpec("alarms", 0x0023, words=2, decoder="u32", category="alarm", bits=SUNSAVER_MPPT_ALARMS),
        RegisterSpec("dip_switch", 0x0025, category="configuration"),
        RegisterSpec("led_state", 0x0026, category="state"),
        RegisterSpec("output_power", 0x0027, decoder="ufactor:0.01509857177734375", unit="W"),
        RegisterSpec("vmp", 0x0028, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("pmax", 0x0029, decoder="ufactor:0.01509857177734375", unit="W"),
        RegisterSpec("voc", 0x002A, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("lighting_should_be_on", 0x0038, category="state"),
        RegisterSpec("fixed_vmp", 0x0039, decoder="factor:0.0030517578125", unit="V"),
        RegisterSpec("fixed_vmp_percent", 0x003A, decoder="percent:255", unit="%"),
    ),
    capabilities=("rtu", "meterbus", "charge", "load", "lighting", "device_identification"),
    network=(("baudrate", "9600"), ("default_modbus_id", "1"), ("stop_bits", "2")),
)
