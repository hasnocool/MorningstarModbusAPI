# src/morningstar_modbus/models.py
"""Shared immutable data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

TransportName = Literal["serial", "tcp"]
RegisterFunction = Literal["holding", "input"]


@dataclass(frozen=True, slots=True)
class DeviceIdentification:
    vendor_name: str = ""
    product_code: str = ""
    major_minor_revision: str = ""
    conformity_level: int = 0
    raw_objects: tuple[tuple[int, str], ...] = ()
    raw_pdu_hex: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Endpoint:
    transport: TransportName
    target: str
    unit_id: int
    port: int | None = None
    baudrate: int | None = None
    stop_bits: int | None = None
    usb_serial: str | None = None
    usb_vid: int | None = None
    usb_pid: int | None = None

    @property
    def locator(self) -> str:
        if self.transport == "tcp":
            return f"{self.target}:{self.port or 502}"
        return self.target

    @property
    def stable_key(self) -> str:
        if self.transport == "serial" and self.usb_serial:
            return f"serial:usb:{self.usb_serial}:unit:{self.unit_id}"
        if self.transport == "serial" and self.usb_vid is not None and self.usb_pid is not None:
            return f"serial:vidpid:{self.usb_vid:04x}:{self.usb_pid:04x}:{self.target}:unit:{self.unit_id}"
        return f"{self.transport}:{self.locator}:unit:{self.unit_id}"


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    endpoint: Endpoint
    identification: DeviceIdentification
    latency_ms: float
    profile: str


@dataclass(frozen=True, slots=True)
class RegisterValue:
    name: str
    address: int
    function: RegisterFunction
    raw: tuple[int, ...]
    value: float | int | str | None
    unit: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PollResult:
    endpoint: Endpoint
    identification: DeviceIdentification
    profile: str
    latency_ms: float
    values: tuple[RegisterValue, ...]
