# tests/test_protocol.py
from morningstar_modbus.protocol import append_crc, crc16, parse_device_identification, valid_crc


def test_crc_round_trip() -> None:
    payload = bytes.fromhex("010300000001")
    frame = append_crc(payload)
    assert valid_crc(frame)
    assert crc16(payload) == int.from_bytes(frame[-2:], "little")


def test_device_identification() -> None:
    pdu = bytes((0x2B, 0x0E, 0x01, 0x01, 0x00, 0x00, 0x03))
    for object_id, text in ((0, "Morningstar"), (1, "TriStar MPPT"), (2, "v1")):
        encoded = text.encode()
        pdu += bytes((object_id, len(encoded))) + encoded
    identity = parse_device_identification(pdu)
    assert identity.vendor_name == "Morningstar"
    assert identity.product_code == "TriStar MPPT"
    assert identity.major_minor_revision == "v1"
