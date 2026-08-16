# MorningstarModbusAPI

MorningstarModbusAPI is a read-only Morningstar Modbus telemetry service for USB / RS-232 / RS-485 (RTU) and Modbus TCP/IP devices.

It discovers Morningstar hardware, identifies it conservatively, reads and decodes telemetry, persists raw and interpreted observations in SQLite, reconciles changing endpoints into stable physical-controller identities, and exposes controller-first, system/site, and legacy device-scoped HTTP APIs.

The project does **not** expose Modbus write operations. Vendor specifications may document writable registers and coils, but the runtime remains a read-only boundary.

> **Release status:** the latest published release is **v0.6.0**. It adds controller history coverage and gap reconciliation, controller-vs-local energy accounting, system component graph/power-flow/energy-ledger improvements, and authoritative GenStar system metering/energy-balance support on top of the v0.5 system/site architecture.

## Current capabilities

- Automatic PySerial USB/serial enumeration.
- Modbus RTU over USB serial adapters, RS-232, and RS-485 adapters.
- Modbus TCP over explicit hosts or explicitly configured bounded local CIDRs.
- Standard Modbus Read Device Identification (`0x2B / 0x0E`) when supported.
- Conservative read-only family fingerprints for older devices.
- Source-backed Morningstar device/register catalog with scaling, enums, alarms, faults, firmware gates, metadata, and reserved ranges.
- Device intelligence combining identity, metadata, firmware compatibility, capability negotiation, confidence scoring, and plausibility validation.
- Persistent physical-controller inventory and immutable `controller_uid` identities that survive DHCP, USB path, and transport changes.
- Controller-scoped history that unifies historical `device_id` segments while preserving `source_device_id` provenance.
- Lifecycle/reconnect handling with stale-client cleanup, bounded exponential backoff, reconnect detection, and one selected polling connection per physical controller.
- Numeric or automatically selected polling intervals with separate persistence cadence.
- SQLite/WAL telemetry history using non-blocking `aiosqlite` access.
- Multi-register history, aggregation, statistics, summaries, and streaming CSV/JSONL export.
- Polling-performance instrumentation and safe staged benchmarking.
- Controller-retained daily-history backfill after startup/reconnect where a verified provider is available.
- **v0.6 history analytics:** day-level live-vs-retained coverage, recovered/partial/missing gap classification, controller-reported vs locally integrated daily energy, discrepancy metrics, and quality/provenance metadata.
- Normalized multi-controller system/site aggregation with explicit quality.
- System component graph, topology, power-flow, and energy-ledger views.
- Authoritative GenStar system metering/energy-balance support where source-backed registers are available.
- Unified events and SSE telemetry/event streaming.
- Optional inbound SNMP trap event ingestion.
- Exact read-only capture/replay and hardware verification tooling.
- Automated official-source catalog-maintenance tooling.
- FastAPI JSON endpoints and OpenAPI/Swagger documentation.

## Identity model

| Identifier | Meaning | Intended use |
| --- | --- | --- |
| `controller_uid` | Immutable ID for one physical controller | **Persist this in new applications** |
| `controller_id` | Strongest current evidence-derived identity alias | Diagnostics and compatibility; may be promoted |
| `device_id` | Raw telemetry-owning storage row / historical endpoint identity | Storage-level provenance and legacy routes |
| `system_uid` | Persistent application grouping above one or more controllers | System/site API |

For new integrations, start with `GET /v1/controllers` and persist `controller_uid`. Controller-scoped queries automatically span historical member device rows.

See [`docs/controller-scoped-data.md`](docs/controller-scoped-data.md), [`docs/api.md`](docs/api.md), and [`docs/system-api.md`](docs/system-api.md).

## History recovery and reconciliation

Supported controllers may retain daily history even when the API host was offline. MorningstarModbusAPI stores that evidence separately from normal high-frequency polling and never expands it into synthetic samples.

After retained-history synchronization, the v0.6 analytics layer can answer:

- which days contain persisted live samples;
- which missing days are recovered by a complete controller daily record;
- which gaps are partial or still missing;
- what energy the controller reported for a day;
- what energy can be independently integrated from persisted `output_power` observations;
- how far those two measurements differ;
- how much local integration time was skipped because sample gaps exceeded the configured threshold.

Key routes:

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
GET /v1/controllers/{controller_uid}/history/coverage
GET /v1/controllers/{controller_uid}/history/gaps
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

See [`docs/controller-history-backfill.md`](docs/controller-history-backfill.md) and [`docs/history-reconciliation-and-energy.md`](docs/history-reconciliation-and-energy.md).

## Controller-first API

Important routes include:

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/controllers` | Physical-controller inventory |
| `GET /v1/controllers/{controller_uid}` | Controller detail |
| `GET /v1/controllers/{controller_uid}/latest` | Latest telemetry |
| `GET /v1/controllers/{controller_uid}/samples` | Unified sample timeline |
| `GET /v1/controllers/{controller_uid}/registers/{name}/history` | Single-register history |
| `GET /v1/controllers/{controller_uid}/registers/history` | Multi-register raw/bucketed history |
| `GET /v1/controllers/{controller_uid}/registers/stats` | Register statistics |
| `GET /v1/controllers/{controller_uid}/history/summary` | Raw history/sample/error summary |
| `GET /v1/controllers/{controller_uid}/history/controller-daily` | Controller-retained daily evidence |
| `GET /v1/controllers/{controller_uid}/history/controller-daily/summary` | Retained-history summary |
| `GET /v1/controllers/{controller_uid}/history/coverage` | Day-level live/retained evidence coverage |
| `GET /v1/controllers/{controller_uid}/history/gaps` | Recovered/partial/missing gap intervals |
| `GET /v1/controllers/{controller_uid}/energy/daily` | Daily controller/local energy comparison |
| `GET /v1/controllers/{controller_uid}/energy/summary` | Range energy comparison summary |
| `GET /v1/controllers/{controller_uid}/history/export` | Streaming CSV/JSONL export |
| `GET /v1/controllers/{controller_uid}/polling/performance` | Polling-performance summary |
| `GET /v1/controllers/{controller_uid}/polling/history` | Polling-performance history |

Raw controller-scoped history preserves `source_device_id` so unified history does not erase storage provenance.

See [`docs/api.md`](docs/api.md) for complete route semantics and examples.

## System/site API

The system layer groups one or more immutable controller identities and publishes normalized, quality-aware site information. Depending on available evidence, it can expose:

- normalized metrics and historical aggregates;
- contributor and expected-contributor quality;
- component graph and typed relationships;
- inferred/verified topology;
- power flow;
- energy ledger/balance;
- unified events;
- SSE telemetry and event streams.

See [`docs/system-api.md`](docs/system-api.md) and [`docs/component-graph.md`](docs/component-graph.md).

## Register semantics

The catalog distinguishes:

1. **named semantic registers** — source-backed fields with decoder/unit/category metadata;
2. **documented reserved ranges** — readable words Morningstar intentionally leaves unnamed;
3. **unknown/unmapped addresses** — raw observations outside known named/reserved declarations.

Consumers should not invent semantic names for manufacturer-reserved words. See [`docs/device-catalog.md`](docs/device-catalog.md) and [`docs/device-intelligence.md`](docs/device-intelligence.md).

## Installation

Python 3.12+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp config.example.toml config.toml
```

For development:

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

## CLI

Discover configured devices:

```bash
morningstar-modbus --config config.toml discover
```

Run continuously:

```bash
morningstar-modbus --config config.toml watch
morningstar-modbus --config config.toml serve
morningstar-modbus --config config.toml run
```

Benchmark a real controller before selecting an aggressive fixed interval:

```bash
morningstar-modbus --config config.toml benchmark-polling \
  --device /dev/ttyUSB0 \
  --transport serial \
  --samples 12
```

Capture and verify read-only hardware sessions:

```bash
morningstar-modbus capture --device /dev/ttyUSB0 --transport serial --output captures/ts-mppt-60
morningstar-modbus verify --device /dev/ttyUSB0 --transport serial
morningstar-modbus replay tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29
```

See [`docs/polling-performance.md`](docs/polling-performance.md) and [`docs/hardware-verification.md`](docs/hardware-verification.md).

## Polling versus persistence

Live polling and persisted history are intentionally separate cadences. `database.telemetry_write_interval_seconds` cannot be configured below one second per physical controller, while the watcher may poll faster. Intermediate reads still affect lifecycle/intelligence and automatic interval evaluation but do not necessarily become history rows.

A database persistence failure is treated as a storage problem rather than retroactively converting a successful Modbus transaction into a controller communication failure.

See [`docs/telemetry-history.md`](docs/telemetry-history.md).

## Read-only safety boundary

The project does not expose:

- write-register operations;
- coil writes;
- controller reset/equalize triggers;
- configuration mutation;
- arbitrary Modbus function-code passthrough.

Retained-history recovery and analytics are also read only: they inspect and reconcile evidence but do not modify controller configuration or fabricate observations.

## Documentation

Start with [`docs/README.md`](docs/README.md). Release notes are indexed at [`docs/releases/README.md`](docs/releases/README.md); the current release is [`v0.6.0`](docs/releases/v0.6.0.md).
