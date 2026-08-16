# src/morningstar_modbus/catalog/families/readyedge.py
"""ReadyEdge RE-1 register catalog."""

from morningstar_modbus.catalog.types import (
    DeviceProfileSpec,
    RegisterBlock,
    RegisterSpec,
    ReservedRegisterRange,
)

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-readyedge-modbus-specification-en.pdf"
)

SYSTEM_FAULTS = (
    (0, "system_eeprom"),
    (2, "software"),
    (6, "system_setting_edit"),
    (19, "minboot"),
    (29, "system_setting_bad"),
    (30, "hardware"),
)
ALARMS = (
    (0, "rts1_open"),
    (1, "rts1_short"),
    (2, "rts1_disconnected"),
    (9, "connected_product_missing"),
    (14, "soc_invalid"),
    (15, "rts2_open"),
    (16, "rts2_short"),
    (17, "rts2_disconnected"),
    (20, "tank_sensor_open"),
    (21, "tank_sensor_short"),
    (22, "tank_sensor_low"),
    (23, "tank_sensor_bad_range"),
    (24, "eeprom"),
    (25, "ethernet"),
    (27, "software"),
    (29, "external_flash"),
    (33, "rtc_low_battery"),
    (35, "rtc_wrong"),
    (36, "rtc_hardware"),
    (41, "wireless_failure"),
    (42, "hardware"),
    (43, "unknown_block_type"),
    (44, "block1_hardware"),
    (45, "block2_hardware"),
    (46, "block3_hardware"),
    (47, "block4_hardware"),
    (48, "block5_hardware"),
    (49, "block6_hardware"),
    (50, "generator_start_failed"),
    (52, "schedule_publisher_failed"),
    (55, "connected_product_address_conflict"),
    (56, "incorrect_installer_password"),
)

CONNECTED_PRODUCT_TYPES = (
    (0xFFFF, "none"),
    (0x0000, "unknown"),
    (0x0100, "TriStar-PWM"),
    (0x0104, "TriStar-MPPT"),
    (0x0105, "SunSaver-MPPT"),
    (0x0106, "SureSine-300"),
    (0x0109, "TriStar-MPPT-600V"),
    (0x010A, "ProStar-MPPT"),
    (0x010D, "ProStar-PWM"),
)

_CONNECTED_PRODUCT_BASE = 0x1F53
_CONNECTED_PRODUCT_STRIDE = 0x10


def _connected_product_registers() -> tuple[RegisterSpec, ...]:
    registers: list[RegisterSpec] = []
    for slot in range(16):
        base = _CONNECTED_PRODUCT_BASE + slot * _CONNECTED_PRODUCT_STRIDE
        prefix = f"connected_product_{slot}_"
        registers.extend(
            (
                RegisterSpec(
                    prefix + "type",
                    base,
                    category="network",
                    enum=CONNECTED_PRODUCT_TYPES,
                    description=(
                        "Configured ReadyEdge Connected Product type for this slot."
                    ),
                ),
                RegisterSpec(
                    prefix + "serial",
                    base + 1,
                    words=4,
                    decoder="ascii_hi_lo",
                    category="network",
                    description="Configured Connected Product serial number.",
                ),
                RegisterSpec(
                    prefix + "bus_and_address",
                    base + 5,
                    category="network",
                    description=(
                        "Physical bus in the upper byte and Modbus device address "
                        "in the lower byte."
                    ),
                ),
            )
        )
    return tuple(registers)


def _connected_product_reserved_ranges() -> tuple[ReservedRegisterRange, ...]:
    return tuple(
        ReservedRegisterRange(
            address=_CONNECTED_PRODUCT_BASE + slot * _CONNECTED_PRODUCT_STRIDE + 6,
            count=10,
            description=(
                "ReadyEdge Connected Product slot reserved expansion words; "
                "manufacturer documentation says clients must not write them."
            ),
        )
        for slot in range(16)
    )


READYEDGE = DeviceProfileSpec(
    name="readyedge",
    family="ReadyEdge RE-1",
    aliases=("readyedge", "ready edge", "re-1"),
    source_id="readyedge-modbus-v01",
    source_url=SOURCE,
    detection_priority=2,
    blocks=(
        RegisterBlock(0x0000, 0x0006, category="metadata", cache=True),
        RegisterBlock(0x0016, 0x0005),
        RegisterBlock(0x0076, 0x0002),
        RegisterBlock(0x0082, 0x0004),
        RegisterBlock(0x01E2, 0x0004),
        RegisterBlock(0x01EA, 0x0004),
        RegisterBlock(0x0270, 0x0001),
        RegisterBlock(0x1F53, 0x0076, category="network", optional=True),
        RegisterBlock(0x1FD3, 0x0076, category="network", optional=True),
    ),
    registers=(
        RegisterSpec("firmware_version", 0x0000, category="metadata"),
        RegisterSpec(
            "serial_number",
            0x0001,
            words=4,
            decoder="ascii_hi_lo",
            category="metadata",
        ),
        RegisterSpec("software_patchlevel", 0x0005, category="metadata"),
        RegisterSpec("dc_input_1_voltage", 0x0016, decoder="f16", unit="V"),
        RegisterSpec("dc_input_2_voltage", 0x0017, decoder="f16", unit="V"),
        RegisterSpec("dc_input_3_voltage", 0x0018, decoder="f16", unit="V"),
        RegisterSpec("input_voltage", 0x0019, decoder="f16", unit="V"),
        RegisterSpec("output_12v_voltage", 0x001A, decoder="f16", unit="V"),
        RegisterSpec("rts_1_temp", 0x0076, decoder="f16", unit="C"),
        RegisterSpec("rts_2_temp", 0x0077, decoder="f16", unit="C"),
        RegisterSpec("ac_detected", 0x0082, category="state"),
        RegisterSpec("battery_soc", 0x0083, decoder="f16_percent", unit="%"),
        RegisterSpec("battery_soc_min_daily", 0x0084, decoder="f16_percent", unit="%"),
        RegisterSpec("battery_soc_max_daily", 0x0085, decoder="f16_percent", unit="%"),
        RegisterSpec(
            "system_faults",
            0x01E2,
            words=4,
            decoder="bitfield_words",
            category="fault",
            bits=SYSTEM_FAULTS,
        ),
        RegisterSpec(
            "alarms",
            0x01EA,
            words=4,
            decoder="bitfield_words",
            category="alarm",
            bits=ALARMS,
        ),
        RegisterSpec("led_state", 0x0270, category="state"),
        *_connected_product_registers(),
    ),
    reserved_ranges=_connected_product_reserved_ranges(),
    capabilities=(
        "rtu",
        "usb",
        "rs232",
        "eia485",
        "modbus_tcp",
        "ethernet",
        "meterbus",
        "ms_can",
        "readyrail",
        "connected_product_bridge",
        "connected_product_inventory",
        "device_identification",
    ),
    network=(
        ("baudrate", "9600"),
        ("stop_bits", "2"),
        ("tcp_port", "502"),
        ("default_modbus_id", "1"),
        ("dhcp", "enabled"),
        ("netbios", "RE<serial>"),
        ("connected_product_ids", "200-215"),
    ),
)
