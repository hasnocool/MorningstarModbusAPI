# src/morningstar_modbus/transport.py
"""Non-blocking Modbus TCP and thread-isolated Modbus RTU transports."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from morningstar_modbus.exceptions import ModbusDeviceError, ModbusProtocolError
from morningstar_modbus.models import DeviceIdentification
from morningstar_modbus.protocol import (
    READ_DEVICE_IDENTIFICATION,
    append_crc,
    parse_device_identification,
    parse_register_response,
    read_registers_pdu,
    valid_crc,
)

LOGGER = logging.getLogger(__name__)


class ReadOnlyModbusClient(Protocol):
    async def read_holding_registers(self, address: int, count: int) -> list[int]: ...
    async def read_input_registers(self, address: int, count: int) -> list[int]: ...
    async def read_device_identification(self) -> DeviceIdentification: ...
    async def close(self) -> None: ...


class AsyncModbusTcpClient:
    """Read-only Modbus TCP client using asyncio streams."""

    def __init__(self, host: str, *, port: int = 502, unit_id: int = 1, timeout: float = 1.5) -> None:
        if not 1 <= unit_id <= 247:
            raise ValueError("unit_id must be 1..247")
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._transaction_id = 0
        self._lock = asyncio.Lock()

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        pdu = await self._request(read_registers_pdu(0x03, address, count))
        return parse_register_response(pdu, function_code=0x03, count=count)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        pdu = await self._request(read_registers_pdu(0x04, address, count))
        return parse_register_response(pdu, function_code=0x04, count=count)

    async def read_device_identification(self) -> DeviceIdentification:
        return parse_device_identification(await self._request(READ_DEVICE_IDENTIFICATION))

    async def close(self) -> None:
        return None

    async def _request(self, pdu: bytes) -> bytes:
        async with self._lock:
            self._transaction_id = (self._transaction_id + 1) & 0xFFFF
            transaction_id = self._transaction_id
            request = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, self.unit_id) + pdu
            writer: asyncio.StreamWriter | None = None
            try:
                async with asyncio.timeout(self.timeout):
                    reader, writer = await asyncio.open_connection(self.host, self.port)
                    writer.write(request)
                    await writer.drain()
                    header = await reader.readexactly(7)
                    rx_id, protocol_id, length, unit_id = struct.unpack(">HHHB", header)
                    if rx_id != transaction_id or protocol_id != 0 or unit_id != self.unit_id:
                        raise ModbusProtocolError("invalid Modbus TCP response header")
                    if length < 2:
                        raise ModbusProtocolError("invalid Modbus TCP response length")
                    response_pdu = await reader.readexactly(length - 1)
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except (ConnectionError, OSError):
                        pass
            self._raise_if_exception(response_pdu)
            if response_pdu[0] != pdu[0]:
                raise ModbusProtocolError("Modbus function code mismatch")
            return response_pdu

    @staticmethod
    def _raise_if_exception(pdu: bytes) -> None:
        if not pdu:
            raise ModbusProtocolError("empty Modbus response")
        if pdu[0] & 0x80:
            if len(pdu) < 2:
                raise ModbusProtocolError("truncated Modbus exception response")
            raise ModbusDeviceError(pdu[0] & 0x7F, pdu[1])


class AsyncModbusRtuClient:
    """Read-only RTU client.

    PySerial is blocking. All open/read/write/close operations run in a dedicated
    single-worker executor, while asyncio.Lock guarantees request serialization.
    """

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        stop_bits: int = 2,
        unit_id: int = 1,
        timeout: float = 1.5,
    ) -> None:
        if not 1 <= unit_id <= 247:
            raise ValueError("unit_id must be 1..247")
        if stop_bits not in (1, 2):
            raise ValueError("stop_bits must be 1 or 2")
        self.port = port
        self.baudrate = baudrate
        self.stop_bits = stop_bits
        self.unit_id = unit_id
        self.timeout = timeout
        self._serial: Any | None = None
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morningstar-rtu")
        self._closed = False

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        pdu = await self._request(read_registers_pdu(0x03, address, count))
        return parse_register_response(pdu, function_code=0x03, count=count)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        pdu = await self._request(read_registers_pdu(0x04, address, count))
        return parse_register_response(pdu, function_code=0x04, count=count)

    async def read_device_identification(self) -> DeviceIdentification:
        return parse_device_identification(await self._request(READ_DEVICE_IDENTIFICATION))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._close_blocking)
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)

    async def _request(self, pdu: bytes) -> bytes:
        if self._closed:
            raise RuntimeError("RTU client is closed")
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._exchange_blocking, pdu)

    def _exchange_blocking(self, pdu: bytes) -> bytes:
        serial_port = self._ensure_open_blocking()
        frame = append_crc(bytes((self.unit_id,)) + pdu)
        try:
            serial_port.reset_input_buffer()
            serial_port.reset_output_buffer()
            serial_port.write(frame)
            serial_port.flush()
            time.sleep(0.02)
            deadline = time.monotonic() + self.timeout
            prefix = self._read_exact(serial_port, 2, deadline)
            unit_id, function_code = prefix
            if unit_id != self.unit_id:
                raise ModbusProtocolError(f"unexpected unit ID {unit_id}")
            if function_code & 0x80:
                tail = self._read_exact(serial_port, 3, deadline)
                response = prefix + tail
                if not valid_crc(response):
                    raise ModbusProtocolError("invalid RTU CRC")
                raise ModbusDeviceError(function_code & 0x7F, tail[0])
            if function_code in (0x03, 0x04):
                byte_count_raw = self._read_exact(serial_port, 1, deadline)
                byte_count = byte_count_raw[0]
                response = prefix + byte_count_raw + self._read_exact(serial_port, byte_count + 2, deadline)
            elif function_code == 0x2B:
                fixed = self._read_exact(serial_port, 6, deadline)
                if fixed[0] != 0x0E or fixed[1] != 0x01:
                    raise ModbusProtocolError("unexpected device-identification RTU header")
                objects = bytearray()
                for _ in range(fixed[5]):
                    header = self._read_exact(serial_port, 2, deadline)
                    objects.extend(header)
                    objects.extend(self._read_exact(serial_port, header[1], deadline))
                response = prefix + fixed + bytes(objects) + self._read_exact(serial_port, 2, deadline)
            else:
                raise ModbusProtocolError(f"unsupported RTU function 0x{function_code:02x}")
            if not valid_crc(response):
                raise ModbusProtocolError("invalid RTU CRC")
            response_pdu = response[1:-2]
            if response_pdu[0] != pdu[0]:
                raise ModbusProtocolError("Modbus function code mismatch")
            return response_pdu
        except (OSError, TimeoutError):
            self._close_blocking()
            raise

    def _ensure_open_blocking(self) -> Any:
        if self._serial is not None:
            return self._serial
        import serial

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO if self.stop_bits == 2 else serial.STOPBITS_ONE,
            timeout=min(self.timeout, 0.2),
            write_timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        return self._serial

    @staticmethod
    def _read_exact(serial_port: Any, size: int, deadline: float) -> bytes:
        payload = bytearray()
        while len(payload) < size:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out reading {size} RTU bytes")
            chunk = serial_port.read(size - len(payload))
            if chunk:
                payload.extend(chunk)
        return bytes(payload)

    def _close_blocking(self) -> None:
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except OSError:
                LOGGER.debug("serial close failed", exc_info=True)
