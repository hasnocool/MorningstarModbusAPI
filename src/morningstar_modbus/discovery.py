# src/morningstar_modbus/discovery.py
"""Serial and bounded local TCP discovery with firmware-aware Morningstar intelligence."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections.abc import Iterable

from morningstar_modbus.config import AppConfig
from morningstar_modbus.intelligence import DeviceIntelligence, resolve_device_intelligence
from morningstar_modbus.models import DeviceIdentification, DiscoveredDevice, Endpoint
from morningstar_modbus.transport import AsyncModbusRtuClient, AsyncModbusTcpClient, ReadOnlyModbusClient

LOGGER = logging.getLogger(__name__)


async def _probe(
    client: ReadOnlyModbusClient,
    endpoint: Endpoint,
) -> tuple[DeviceIdentification, float, DeviceIntelligence] | None:
    started = time.perf_counter()
    try:
        try:
            identity = await client.read_device_identification()
        except Exception:
            await client.read_holding_registers(0, 1)
            identity = DeviceIdentification()
        intelligence = await resolve_device_intelligence(client, identity, endpoint=endpoint)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return identity, latency_ms, intelligence
    except (OSError, TimeoutError, ConnectionError):
        return None
    except Exception as exc:
        LOGGER.debug("probe failed: %s", exc)
        return None
    finally:
        await client.close()


async def discover_serial(config: AppConfig) -> list[DiscoveredDevice]:
    if not config.serial.enabled:
        return []
    from serial.tools import list_ports

    ports = await asyncio.to_thread(lambda: tuple(list_ports.comports()))
    allowlist = set(config.serial.ports)
    found: list[DiscoveredDevice] = []
    for port in ports:
        device = str(port.device)
        if allowlist and device not in allowlist:
            continue
        for unit_id in config.watch.unit_ids:
            endpoint = Endpoint(
                transport="serial",
                target=device,
                unit_id=unit_id,
                baudrate=config.serial.baudrate,
                stop_bits=config.serial.stop_bits,
                usb_serial=getattr(port, "serial_number", None),
                usb_vid=getattr(port, "vid", None),
                usb_pid=getattr(port, "pid", None),
            )
            result = await _probe(
                AsyncModbusRtuClient(
                    device,
                    baudrate=config.serial.baudrate,
                    stop_bits=config.serial.stop_bits,
                    unit_id=unit_id,
                    timeout=config.watch.request_timeout_seconds,
                ),
                endpoint,
            )
            if result is not None:
                identity, latency_ms, intelligence = result
                found.append(
                    DiscoveredDevice(
                        endpoint,
                        identity,
                        latency_ms,
                        intelligence.profile,
                        intelligence,
                    )
                )
    return found


def _tcp_hosts(config: AppConfig) -> Iterable[str]:
    yielded: set[str] = set()
    for host in config.tcp.hosts:
        if host not in yielded:
            yielded.add(host)
            yield host
    for subnet in config.tcp.subnets:
        network = ipaddress.ip_network(subnet, strict=False)
        for address in network.hosts():
            host = str(address)
            if host not in yielded:
                yielded.add(host)
                yield host


async def discover_tcp(config: AppConfig) -> list[DiscoveredDevice]:
    if not config.tcp.enabled:
        return []
    semaphore = asyncio.Semaphore(config.watch.max_tcp_concurrency)

    async def probe_host(host: str, unit_id: int) -> DiscoveredDevice | None:
        async with semaphore:
            endpoint = Endpoint("tcp", host, unit_id, port=config.tcp.port)
            result = await _probe(
                AsyncModbusTcpClient(
                    host,
                    port=config.tcp.port,
                    unit_id=unit_id,
                    timeout=config.watch.request_timeout_seconds,
                ),
                endpoint,
            )
            if result is None:
                return None
            identity, latency_ms, intelligence = result
            return DiscoveredDevice(
                endpoint,
                identity,
                latency_ms,
                intelligence.profile,
                intelligence,
            )

    tasks = [
        asyncio.create_task(probe_host(host, unit_id))
        for host in _tcp_hosts(config)
        for unit_id in config.watch.unit_ids
    ]
    if not tasks:
        return []
    results = await asyncio.gather(*tasks)
    return [result for result in results if result is not None]


async def discover(config: AppConfig) -> list[DiscoveredDevice]:
    serial_task = asyncio.create_task(discover_serial(config))
    tcp_task = asyncio.create_task(discover_tcp(config))
    serial_devices, tcp_devices = await asyncio.gather(serial_task, tcp_task)
    merged: dict[str, DiscoveredDevice] = {}
    for device in (*serial_devices, *tcp_devices):
        merged[device.endpoint.stable_key] = device
    return list(merged.values())
