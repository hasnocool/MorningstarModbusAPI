"""Strict replay transport for recorded read-only Modbus captures."""

from __future__ import annotations

from pathlib import Path

from morningstar_modbus.capture import load_capture_transactions
from morningstar_modbus.models import DeviceIdentification
from morningstar_modbus.protocol import parse_device_identification, parse_register_response


class ReplayMismatch(RuntimeError):
    """Raised when runtime requests diverge from the recorded capture."""


class ReplayRecordedError(RuntimeError):
    """Raised when the capture contains a non-timeout recorded failure."""


class ReplayModbusClient:
    """ReadOnlyModbusClient implementation backed by an ordered transaction stream."""

    def __init__(self, transactions: tuple[dict[str, object], ...]) -> None:
        self._transactions = transactions
        self._index = 0
        self._closed = False

    @classmethod
    def from_bundle(cls, bundle: str | Path) -> ReplayModbusClient:
        return cls(load_capture_transactions(bundle))

    def _next(
        self,
        function_code: int,
        address: int | None,
        count: int | None,
    ) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("replay client is closed")
        if self._index >= len(self._transactions):
            raise ReplayMismatch("capture exhausted before runtime stopped requesting data")
        item = self._transactions[self._index]
        self._index += 1
        expected = (int(item["function_code"]), item.get("address"), item.get("count"))
        actual = (function_code, address, count)
        if expected != actual:
            raise ReplayMismatch(f"request mismatch expected={expected!r} actual={actual!r}")
        error_type = str(item.get("error_type") or "")
        error = str(item.get("error") or "recorded Modbus failure")
        if error_type:
            if error_type in {"TimeoutError", "CancelledError"}:
                raise TimeoutError(error)
            raise ReplayRecordedError(f"{error_type}: {error}")
        return item

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        item = self._next(0x03, address, count)
        pdu = bytes.fromhex(str(item["response_pdu_hex"]))
        return parse_register_response(pdu, function_code=0x03, count=count)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        item = self._next(0x04, address, count)
        pdu = bytes.fromhex(str(item["response_pdu_hex"]))
        return parse_register_response(pdu, function_code=0x04, count=count)

    async def read_device_identification(self) -> DeviceIdentification:
        item = self._next(0x2B, None, None)
        return parse_device_identification(bytes.fromhex(str(item["response_pdu_hex"])))

    async def close(self) -> None:
        self._closed = True

    @property
    def consumed(self) -> int:
        return self._index

    @property
    def remaining(self) -> int:
        return len(self._transactions) - self._index
