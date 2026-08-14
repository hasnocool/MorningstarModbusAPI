# src/morningstar_modbus/protocol.py
"""Small read-only Modbus protocol codec shared by RTU and TCP transports."""

from __future__ import annotations

import struct
from collections.abc import Mapping

from morningstar_modbus.exceptions import ModbusProtocolError
from morningstar_modbus.models import DeviceIdentification

READ_DEVICE_IDENTIFICATION = bytes((0x2B, 0x0E, 0x01, 0x00))


def crc16(payload: bytes) -> int:
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(payload: bytes) -> bytes:
    return payload + struct.pack("<H", crc16(payload))


def valid_crc(frame: bytes) -> bool:
    return len(frame) >= 3 and crc16(frame[:-2]) == struct.unpack("<H", frame[-2:])[0]


def read_registers_pdu(function_code: int, address: int, count: int) -> bytes:
    if function_code not in (0x03, 0x04):
        raise ValueError("only holding (0x03) and input (0x04) reads are supported")
    if not 0 <= address <= 0xFFFF:
        raise ValueError("address must fit uint16")
    if not 1 <= count <= 125:
        raise ValueError("count must be between 1 and 125")
    return struct.pack(">BHH", function_code, address, count)


def parse_register_response(pdu: bytes, *, function_code: int, count: int) -> list[int]:
    if len(pdu) < 2 or pdu[0] != function_code:
        raise ModbusProtocolError("unexpected register response function")
    expected_bytes = count * 2
    if pdu[1] != expected_bytes or len(pdu[2:]) != expected_bytes:
        raise ModbusProtocolError("register response byte count mismatch")
    return list(struct.unpack(f">{count}H", pdu[2:]))


def parse_device_identification(pdu: bytes) -> DeviceIdentification:
    if len(pdu) < 7:
        raise ModbusProtocolError("truncated Read Device Identification response")
    if pdu[:3] != bytes((0x2B, 0x0E, 0x01)):
        raise ModbusProtocolError("unexpected Read Device Identification header")

    conformity = pdu[3]
    object_count = pdu[6]
    cursor = 7
    objects: list[tuple[int, str]] = []
    for _ in range(object_count):
        if cursor + 2 > len(pdu):
            raise ModbusProtocolError("truncated device-identification object header")
        object_id = pdu[cursor]
        length = pdu[cursor + 1]
        cursor += 2
        if cursor + length > len(pdu):
            raise ModbusProtocolError("truncated device-identification object value")
        value = pdu[cursor : cursor + length].decode("ascii", errors="replace").strip()
        cursor += length
        objects.append((object_id, value))
    if cursor != len(pdu):
        raise ModbusProtocolError("unexpected trailing bytes in device-identification response")

    values: Mapping[int, str] = dict(objects)
    return DeviceIdentification(
        vendor_name=values.get(0x00, ""),
        product_code=values.get(0x01, ""),
        major_minor_revision=values.get(0x02, ""),
        conformity_level=conformity,
        raw_objects=tuple(objects),
        raw_pdu_hex=pdu.hex(),
    )
