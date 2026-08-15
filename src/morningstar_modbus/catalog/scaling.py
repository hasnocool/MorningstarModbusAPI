# src/morningstar_modbus/catalog/scaling.py
"""Shared Morningstar register decoding and scaling helpers."""

from __future__ import annotations

import struct
from collections.abc import Mapping


def signed_16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def fixed_point_scale(high_word: int, low_word: int) -> float:
    return float(high_word & 0xFFFF) + float(low_word & 0xFFFF) / 65536.0


def float16(value: int) -> float:
    """Decode the IEEE-754 binary16 format used by newer Morningstar products."""

    return float(struct.unpack(">e", struct.pack(">H", value & 0xFFFF))[0])


def bcd_integer(value: int) -> int:
    """Decode a packed-BCD register into an integer, ignoring leading zeroes."""

    digits: list[str] = []
    for shift in (12, 8, 4, 0):
        nibble = (value >> shift) & 0xF
        if nibble > 9:
            return value
        digits.append(str(nibble))
    return int("".join(digits))


def ascii_low_high(words: tuple[int, ...]) -> str:
    payload = bytearray()
    for word in words:
        payload.append(word & 0xFF)
        payload.append((word >> 8) & 0xFF)
    return payload.rstrip(b"\x00\xff ").decode("ascii", errors="replace").strip()


def ascii_high_low(words: tuple[int, ...]) -> str:
    payload = bytearray()
    for word in words:
        payload.append((word >> 8) & 0xFF)
        payload.append(word & 0xFF)
    return payload.rstrip(b"\x00\xff ").decode("ascii", errors="replace").strip()


def little_word_integer(words: tuple[int, ...]) -> int:
    value = 0
    for index, word in enumerate(words):
        value |= (word & 0xFFFF) << (16 * index)
    return value


def _context_word(context: Mapping[int, int], address: int, default: int = 0) -> int:
    return int(context.get(address, default))


def decode_value(decoder: str, words: tuple[int, ...], context: Mapping[int, int]) -> float | int | str:
    """Decode one catalog field using a compact declarative decoder name."""

    if not words:
        raise ValueError("cannot decode an empty register field")

    raw = words[0]
    if decoder == "raw":
        return raw
    if decoder == "s16":
        return signed_16(raw)
    if decoder == "f16":
        return float16(raw)
    if decoder == "bcd":
        return bcd_integer(raw)
    if decoder == "u32":
        if len(words) != 2:
            raise ValueError("u32 decoder requires two words")
        return ((words[0] & 0xFFFF) << 16) | (words[1] & 0xFFFF)
    if decoder.startswith("u32_factor:"):
        if len(words) != 2:
            raise ValueError("u32_factor decoder requires two words")
        combined = ((words[0] & 0xFFFF) << 16) | (words[1] & 0xFFFF)
        return combined * float(decoder.split(":", 1)[1])
    if decoder == "ascii_lo_hi":
        return ascii_low_high(words)
    if decoder == "ascii_hi_lo":
        return ascii_high_low(words)
    if decoder == "bitfield_words":
        return little_word_integer(words)
    if decoder == "f16_percent":
        return float16(raw) * 100.0
    if decoder.startswith("factor:"):
        return signed_16(raw) * float(decoder.split(":", 1)[1])
    if decoder.startswith("ufactor:"):
        return (raw & 0xFFFF) * float(decoder.split(":", 1)[1])
    if decoder.startswith("divide:"):
        return signed_16(raw) / float(decoder.split(":", 1)[1])
    if decoder.startswith("udivide:"):
        return (raw & 0xFFFF) / float(decoder.split(":", 1)[1])
    if decoder.startswith("percent:"):
        denominator = float(decoder.split(":", 1)[1])
        return (raw & 0xFFFF) * 100.0 / denominator
    if decoder == "tristar_voltage":
        scale = fixed_point_scale(_context_word(context, 0x0000), _context_word(context, 0x0001))
        return signed_16(raw) * scale / 32768.0
    if decoder == "tristar_current":
        scale = fixed_point_scale(_context_word(context, 0x0002), _context_word(context, 0x0003))
        return signed_16(raw) * scale / 32768.0
    if decoder == "tristar_power":
        voltage = fixed_point_scale(_context_word(context, 0x0000), _context_word(context, 0x0001))
        current = fixed_point_scale(_context_word(context, 0x0002), _context_word(context, 0x0003))
        return (raw & 0xFFFF) * voltage * current / 131072.0
    if decoder.startswith("ts600_"):
        firmware = bcd_integer(_context_word(context, 0x0004))
        if firmware >= 19:
            return float16(raw)
        kind = decoder.removeprefix("ts600_")
        if kind == "voltage":
            scale = fixed_point_scale(_context_word(context, 0x0000), _context_word(context, 0x0001))
            return signed_16(raw) * scale / 32768.0
        if kind == "current":
            scale = fixed_point_scale(_context_word(context, 0x0002), _context_word(context, 0x0003))
            return signed_16(raw) * scale / 32768.0
        return raw
    if decoder == "suresine_classic_current":
        output_voltage = _context_word(context, 0x000D)
        full_scale = 6.4 if output_voltage >= 180 else 17.0
        return signed_16(raw) * full_scale / 32768.0
    raise ValueError(f"unknown register decoder: {decoder}")
