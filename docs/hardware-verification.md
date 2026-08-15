# Hardware verification and Modbus capture/replay

MorningstarModbusAPI separates three evidence levels: vendor documentation, deterministic software/replay tests, and observations from known physical hardware. A profile must not be marked hardware-verified solely because a PDF or synthetic fixture exists.

## Capture a physical device

Capture performs read-only Device Identification, metadata resolution, and one profile poll while recording the exact Modbus transport exchanges.

```bash
morningstar-modbus capture --device /dev/ttyUSB0 --transport serial --output captures/ts-mppt-60
morningstar-modbus capture --device 192.168.1.50 --transport tcp --output captures/ts-mppt-60-tcp
```

A bundle contains `manifest.json`, `identification.json`, `transactions.jsonl`, `registers.json`, and `expected.json`. TCP captures preserve the MBAP header and PDU; successful RTU captures preserve complete request/response ADUs including CRC.

Structured endpoint and serial identifiers are redacted by default. Exact raw protocol frames are retained for faithful replay and **may themselves contain device identifiers**. Review a capture before publishing it.

## Verify attached hardware

```bash
morningstar-modbus verify --device /dev/ttyUSB0 --transport serial
morningstar-modbus verify --device 192.168.1.50 --transport tcp --json
```

`verify` runs the normal identity resolver and firmware-aware catalog profile, reports required/optional block availability and named register coverage, and fails verification when required blocks are unavailable or decoded telemetry invalidates the profile.

Use `--capture PATH` to retain the exact verification exchange stream.

## Replay in CI

```bash
morningstar-modbus replay tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29
```

`ReplayModbusClient` is strict: function code, address, count, and transaction order must match the capture. Response PDUs are fed through the production protocol parsers. This catches changes in identity, metadata, firmware gating, decoding, validation, persistence, and API behavior without requiring hardware in CI.

The checked-in TriStar fixture is deliberately marked `synthetic-spec-derived`. It establishes replay coverage but is not physical-device evidence. Once a reviewed capture from known hardware is committed, update the profile verification metadata with the observed model/firmware and fixture path.

## Device lifecycle

The watcher now tracks `discovered → connecting → online → degraded → offline → rediscovering` in memory. Failed polls use exponential backoff and force the next attempt to create a fresh client. Devices absent from the latest discovery pass are no longer polled through stale endpoints; rediscovery can restore them and increments reconnect/endpoint-change counters.
