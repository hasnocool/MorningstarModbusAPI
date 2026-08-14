# src/morningstar_modbus/catalog/families/relay_driver.py
"""Relay Driver RD-1 catalog boundary.

The official MODBUS document is indexed, but this profile intentionally retains
raw words until the exact register table is parsed into named definitions.
"""

from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock

SOURCE = (
    "https://www.morningstarcorp.com/wp-content/uploads/"
    "technical-doc-relay-driver-modbus-specification-en.pdf"
)

RELAY_DRIVER = DeviceProfileSpec(
    name="relay_driver",
    family="Relay Driver RD-1",
    aliases=("relay driver", "relaydriver", "rd-1"),
    source_id="relay-driver-modbus",
    source_url=SOURCE,
    detection_priority=90,
    blocks=(RegisterBlock(0x0000, 0x0020, optional=True),),
    registers=(),
    capabilities=("rtu", "rs232", "relay_outputs", "analog_inputs"),
    network=(("default_modbus_id", "1"),),
    coverage="source-indexed",
    notes=(
        "Dedicated family selection is implemented. Raw registers are preserved, but named RD-1 "
        "register decoding remains intentionally incomplete until the official table is parsed."
    ),
)
