# src/morningstar_modbus/cli.py
"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from dataclasses import asdict

import uvicorn

from morningstar_modbus.api import create_app
from morningstar_modbus.config import AppConfig, load_config
from morningstar_modbus.discovery import discover
from morningstar_modbus.storage import TelemetryStore
from morningstar_modbus.transport import AsyncModbusRtuClient, AsyncModbusTcpClient
from morningstar_modbus.watcher import Watcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="morningstar-modbus")
    parser.add_argument("--config", help="TOML configuration file")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover", help="Probe configured serial ports and TCP hosts/subnets")

    read = sub.add_parser("read", help="Perform one raw read without writing to the database")
    read.add_argument("--transport", choices=("serial", "tcp"), required=True)
    read.add_argument("--target", required=True, help="Serial device path or TCP host")
    read.add_argument("--unit-id", type=int, default=1)
    read.add_argument("--address", type=lambda value: int(value, 0), required=True)
    read.add_argument("--count", type=int, default=1)
    read.add_argument("--function", choices=("holding", "input"), default="holding")
    read.add_argument("--tcp-port", type=int, default=502)
    read.add_argument("--baudrate", type=int, default=9600)
    read.add_argument("--stop-bits", type=int, choices=(1, 2), default=2)

    sub.add_parser("watch", help="Continuously discover, poll, and persist devices")
    sub.add_parser("serve", help="Serve the database over HTTP without polling")
    sub.add_parser("run", help="Run watcher and HTTP API in the same process")
    return parser


async def _discover(config: AppConfig) -> int:
    devices = await discover(config)
    payload = [
        {
            "endpoint": asdict(device.endpoint),
            "identity": device.identification.to_dict(),
            "profile": device.profile,
            "latency_ms": device.latency_ms,
        }
        for device in devices
    ]
    print(json.dumps(payload, indent=2))
    return 0


async def _read(config: AppConfig, args: argparse.Namespace) -> int:
    timeout = config.watch.request_timeout_seconds
    if args.transport == "tcp":
        client = AsyncModbusTcpClient(
            args.target,
            port=args.tcp_port,
            unit_id=args.unit_id,
            timeout=timeout,
        )
    else:
        client = AsyncModbusRtuClient(
            args.target,
            baudrate=args.baudrate,
            stop_bits=args.stop_bits,
            unit_id=args.unit_id,
            timeout=timeout,
        )
    try:
        values = (
            await client.read_input_registers(args.address, args.count)
            if args.function == "input"
            else await client.read_holding_registers(args.address, args.count)
        )
        print(
            json.dumps(
                {
                    "address": args.address,
                    "count": args.count,
                    "function": args.function,
                    "values": values,
                },
                indent=2,
            )
        )
        return 0
    finally:
        await client.close()


async def _watch(config: AppConfig) -> int:
    store = TelemetryStore(config.database.path)
    await store.initialize()
    watcher = Watcher(config, store)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(watcher.stop()))
        except NotImplementedError:
            pass
    await watcher.run()
    return 0


async def _serve(config: AppConfig) -> int:
    store = TelemetryStore(config.database.path)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store),
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )
    await server.serve()
    return 0


async def _run(config: AppConfig) -> int:
    store = TelemetryStore(config.database.path)
    await store.initialize()
    watcher = Watcher(config, store)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store),
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )
    watcher_task = asyncio.create_task(watcher.run(), name="morningstar-watcher")
    server_task = asyncio.create_task(server.serve(), name="morningstar-api")
    done, pending = await asyncio.wait(
        {watcher_task, server_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    await watcher.stop()
    server.should_exit = True
    for task in pending:
        try:
            await task
        except asyncio.CancelledError:
            pass
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc
    return 0


async def async_main(args: argparse.Namespace, config: AppConfig) -> int:
    if args.command == "discover":
        return await _discover(config)
    if args.command == "read":
        return await _read(config, args)
    if args.command == "watch":
        return await _watch(config)
    if args.command == "serve":
        return await _serve(config)
    return await _run(config)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_config(args.config)
    raise SystemExit(asyncio.run(async_main(args, config)))


if __name__ == "__main__":
    main()
