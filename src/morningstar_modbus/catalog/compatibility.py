# src/morningstar_modbus/catalog/compatibility.py
"""Version comparison helpers shared by catalog runtime and device intelligence."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

_VERSION_RE = re.compile(r"\d+")


class FirmwareGated(Protocol):
    since_firmware: str | None
    until_firmware: str | None


def version_tuple(value: object) -> tuple[int, ...]:
    if value is None or isinstance(value, bool):
        return ()
    text = f"{value:g}" if isinstance(value, float) else str(value).strip()
    return tuple(int(part) for part in _VERSION_RE.findall(text))


def compare_versions(left: object, right: object) -> int:
    a = version_tuple(left)
    b = version_tuple(right)
    if not a or not b:
        raise ValueError("both firmware versions must contain numeric components")
    width = max(len(a), len(b))
    a += (0,) * (width - len(a))
    b += (0,) * (width - len(b))
    return (a > b) - (a < b)


def in_range(value: object, *, since: str | None = None, until: str | None = None) -> bool:
    if not version_tuple(value):
        return since is None and until is None
    if since is not None and compare_versions(value, since) < 0:
        return False
    if until is not None and compare_versions(value, until) > 0:
        return False
    return True


def effective_items[T: FirmwareGated](items: Iterable[T], firmware: object) -> list[T]:
    return [
        item
        for item in items
        if in_range(
            firmware,
            since=item.since_firmware,
            until=item.until_firmware,
        )
    ]
