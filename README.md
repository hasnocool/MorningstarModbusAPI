# MorningstarModbusAPI

MorningstarModbusAPI is a read-only Morningstar Modbus data service for USB / RS-232 / RS-485 (RTU) and Modbus TCP/IP devices.

It discovers Morningstar hardware, resolves product and physical-controller identity conservatively, reads and decodes telemetry, persists raw evidence and derived metadata in SQLite, and exposes both controller-first and backward-compatible device-scoped HTTP APIs. The project also includes capture/replay verification, retained controller-history backfill, polling-performance instrumentation, and official-source catalog maintenance.

The runtime does **not** expose Modbus write operations. Vendor specifications may document write-capable registers and coils, but this project deliberately implements only read paths.

## Current capabilities

### Transport, discovery, and safety

- Automatic PySerial USB/serial enumeration.
- Modbus RTU over USB serial adapters, RS-232, and RS-485 adapters.
- Modbus TCP over explicit hosts or explicitly configured bounded local CIDRs.
- Standard Modbus Read Device Identification (`0x2B / 0x0E`) when supported.
- Conservative read-only family fingerprints for older devices with weak identification.
- Runtime Modbus operations limited to holding-register reads (`0x03`), input-register reads (`0x04`), and Read Device Identification (`0x2B / 0x0E`).

### Controller identity and runtime ownership

- Persistent physical-controller inventory separated from connection endpoints.
- Generated immutable `controller_uid` values for application-facing identity.
- Evidence-derived `controller_id` aliases retained across identity promotion.
- Historical `device_id` membership preserved without rewriting raw telemetry foreign keys.
- One watcher lifecycle/polling session per physical controller even when USB/TCP endpoints change.
- Multiple observed connections retained while one current polling connection is selected deterministically.
- In-memory lifecycle tracking with degraded/offline states, stale-client cleanup, reconnect counters, endpoint-change counters, and bounded exponential backoff.

### Telemetry, history, and performance

- SQLite/WAL persistence using non-blocking `aiosqlite` access.
- Immutable poll samples plus raw/decoded register observations.
- Persisted device-intelligence snapshots and poll errors.
- Controller-scoped history that transparently spans pre-migration `device_id` segments while preserving `source_device_id` provenance.
- Raw and bucketed multi-register history (`1m`, `5m`, `15m`, `1h`, `1d`).
- Numeric statistics, text/state transition statistics, history summaries, and streaming CSV/JSONL export.
- Poll-performance telemetry including latency percentiles, deadline misses, request/byte rates, failures, and RTU bus-utilization estimates.
- Controlled `benchmark-polling` command for testing safe full-profile intervals without modifying controller settings.
- Optional TriStar MPPT LiveView retained-history backfill that supplements full-day gaps with provenance-aware daily records rather than fabricating raw poll samples.

### Catalog, intelligence, and verification

- Morningstar-wide declarative catalog with product-specific register maps, scaling, enums, alarms, faults, metadata, communications capabilities, firmware gates, and source references.
- Device intelligence combining identification, targeted metadata reads, firmware compatibility, capability negotiation, confidence scoring, and post-poll plausibility validation.
- Exact read-only Modbus capture for TCP and RTU, preserving request/response frames, PDUs, request shape, timing, and failures.
- Strict capture replay through the same production protocol parsers used for live devices.
- Live/replay verification reports plus a separate catalog verification-evidence registry.
- Automated catalog-maintenance tooling for approved Morningstar source validation, conservative PDF extraction, advisory diffs, and reviewed provenance.

The latest published release is **v0.3.0**. The current `main` branch contains substantial post-v0.3 development, including capture/replay verification, lifecycle/reconnect work, rich history/export, retained daily-history backfill, polling-performance measurement, persistent controller inventory, immutable controller UIDs, and controller-scoped data APIs. Documentation in this repository describes current `main` unless a section explicitly says otherwise.

## Package layout

```text
src/morningstar_modbus/
├── catalog/                     # vendor-derived profiles + independent verification evidence
├── intelligence/                # identity, firmware compatibility, confidence, validation
├── maintenance/                 # approved-source validation and advisory PDF/spec scanning
├── transport.py / protocol.py   # read-only Modbus RTU/TCP framing and I/O
├── discovery.py                 # endpoint discovery + product intelligence
├── controller_inventory.py      # evidence-derived physical-controller inventory
├── controller_scope.py          # immutable controller UID registry + aliases
├── controller_data.py           # controller-scoped read/query model
├── controller_api.py            # controller-first FastAPI routes
├── controller_history_*.py      # retained LiveView daily-history parsing/storage/backfill
├── storage.py / history.py      # raw telemetry storage, queries, stats, aggregation/export
├── polling.py                   # poll traffic/performance measurement and benchmark logic
├── polling_storage.py           # persisted poll-performance samples
├── lifecycle.py                 # in-memory retry/reconnect state machine
├── watcher.py                   # discovery, polling, reconnect, persistence orchestration
├── capture.py / replay.py       # read-only evidence capture and strict replay
├── verification.py              # live/replay verification reports
├── api.py                       # FastAPI application + legacy device-scoped routes
└── cli.py                       # CLI orchestration
```

See [`docs/README.md`](docs/README.md) for the full documentation index.

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
```

For official vendor-document scanning:

```bash
python -m pip install -e '.[maintenance]'
```

On Linux, make sure the service account can open the serial adapter, commonly by adding it to the `dialout` or equivalent serial-device group.

Configuration defaults, validation rules, discovery limits, backfill settings, and benchmark thresholds are documented in [`docs/configuration.md`](docs/configuration.md).

## CLI

Discover configured devices:

```bash
morningstar-modbus --config config.toml discover
```

Perform one raw read without writing to SQLite:

```bash
morningstar-modbus read \
  --transport tcp \
  --target 192.168.1.50 \
  --unit-id 1 \
  --function holding \
  --address 0x0018 \
  --count 4
```

### Capture a read-only hardware session

```bash
morningstar-modbus capture \
  --device /dev/ttyUSB0 \
  --transport serial \
  --output captures/ts-mppt-60
```

For TCP:

```bash
morningstar-modbus capture \
  --device 192.168.1.50 \
  --transport tcp \
  --unit-id 1 \
  --output captures/ts-mppt-60-tcp
```

A capture bundle separates transport evidence from decoded telemetry: `transactions.jsonl` contains ordered transport exchanges, while `registers.json` contains raw register words and decoded named values from the profile poll.

Structured identifiers are redacted by default. `--include-identifiers` retains structured target/serial metadata, but raw protocol frames can themselves contain identifying values and must still be reviewed before publication.

### Verify attached hardware

```bash
morningstar-modbus verify --device /dev/ttyUSB0 --transport serial
morningstar-modbus verify --device 192.168.1.50 --transport tcp --json
```

Capture the verification exchange at the same time:

```bash
morningstar-modbus verify \
  --device /dev/ttyUSB0 \
  --transport serial \
  --capture captures/verified-ts-mppt-60
```

`verify` reports profile/family, model, firmware/hardware revision, transport/unit ID, intelligence status/confidence, block availability, named-register coverage, warnings, and a final verification result. It exits with status `0` when the result is `verified` and status `2` otherwise.

### Replay a captured session

```bash
morningstar-modbus replay \
  tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29
```

Replay is strict: request function, address, count, and ordering must match the recording.

### Benchmark polling

Test full-profile polling intervals against an attached controller:

```bash
morningstar-modbus --config config.toml benchmark-polling \
  --device /dev/ttyUSB0 \
  --transport serial
```

The benchmark tests configured stages from slower to faster, stops after the first unsafe stage, and reports the fastest passing interval. It performs the same read-only profile polls as normal monitoring and does not change controller settings or rewrite `config.toml`.

Benchmark samples are persisted by default under `mode=benchmark`; use `--no-persist` for a temporary run. See [`docs/polling-performance.md`](docs/polling-performance.md).

### Run continuously

```bash
morningstar-modbus --config config.toml watch   # discovery + polling + persistence
morningstar-modbus --config config.toml serve   # HTTP API over an existing database
morningstar-modbus --config config.toml run     # watcher and API together
```

By default the API binds to `127.0.0.1:8080`.

## Controller identity model

Normal applications should use the physical-controller API rather than persisting an endpoint-derived device ID.

```text
controller_uid      immutable application identity
      |
      +-- controller_id aliases (endpoint / USB serial / Morningstar serial evidence)
      |
      +-- canonical_device_id   current telemetry owner
      |
      `-- history_device_ids    preserved pre-migration telemetry owners
```

`controller_uid` is generated once and remains stable when an IP address changes, Linux re-enumerates `/dev/ttyUSB*`, or stronger identity evidence promotes a controller from endpoint/USB fallback to a Morningstar serial identity.

Raw controller-scoped history preserves `source_device_id`, so unified timelines do not erase where evidence was originally stored. Existing `/v1/devices/...` routes remain supported for backward compatibility and raw storage inspection.

See [`docs/canonical-device-identity.md`](docs/canonical-device-identity.md) and [`docs/controller-scoped-data.md`](docs/controller-scoped-data.md).

## Device lifecycle and retry policy

The watcher tracks a detailed **in-memory** lifecycle per physical controller:

```text
discovered → connecting → online → degraded → offline → rediscovering → online
```

It records consecutive failures, reconnect count, endpoint-change count, last discovery time, last successful poll time, offline-since time, and retry delay. A missing controller is not polled through a stale endpoint, and failed/stale clients are closed before reconnect.

```toml
[watch]
failure_threshold = 3
retry_backoff_initial_seconds = 2.0
retry_backoff_max_seconds = 60.0
```

The detailed `DeviceLifecycle` object is not persisted or exposed directly through FastAPI. SQLite does persist simpler current `devices.status`/`last_seen`/`last_error` state and current/previous controller-connection inventory, including offline state across watcher startup/shutdown.

## HTTP API

`GET /v1/controllers` is the preferred inventory surface. Each controller record includes immutable `controller_uid`, the current evidence-derived `controller_id`, canonical/history device IDs, metadata, status, and connection history.

### Controller-first routes

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/controllers` | Physical-controller inventory with immutable UIDs and connections |
| `GET /v1/controllers/{controller_uid}` | One physical controller |
| `GET /v1/controllers/{controller_uid}/latest` | Latest sample across all historical device IDs |
| `GET /v1/controllers/{controller_uid}/samples` | Poll-sample history |
| `GET /v1/controllers/{controller_uid}/registers/{name}/history` | Single-register raw history |
| `GET /v1/controllers/{controller_uid}/registers/history` | Multi-register raw/bucketed history |
| `GET /v1/controllers/{controller_uid}/registers/stats` | Numeric/state statistics |
| `GET /v1/controllers/{controller_uid}/history/summary` | Sample/register/error/latency coverage summary |
| `GET /v1/controllers/{controller_uid}/history/controller-daily` | Retained/backfilled controller daily records |
| `GET /v1/controllers/{controller_uid}/history/controller-daily/summary` | Daily-history coverage and last sync |
| `GET /v1/controllers/{controller_uid}/history/export` | Streaming CSV/JSONL telemetry export |
| `GET /v1/controllers/{controller_uid}/polling/performance` | Poll-performance summary |
| `GET /v1/controllers/{controller_uid}/polling/history` | Raw poll-performance records |

Known historical `controller_id` aliases are also resolvable by the controller repository for compatibility, but applications should persist the immutable `controller_uid` returned by `/v1/controllers`.

### Catalog and compatibility routes

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness and package version |
| `GET /v1/catalog` | Compact Morningstar catalog summary and verification metadata |
| `GET /v1/catalog/{profile_name}` | Detailed profile/register definition and verification metadata |
| `GET /v1/devices` | Raw persisted device/endpoint rows |
| `GET /v1/devices/{device_id}` | One raw persisted device row; path form supports IDs containing `/` |
| `GET /v1/devices/latest?device_id=...` | Latest sample for one device ID |
| `GET /v1/devices/intelligence?device_id=...` | Persisted identity/firmware/capability evidence |
| `GET /v1/devices/register-map?device_id=...` | Effective firmware-filtered register map |
| `GET /v1/devices/profile/validation?device_id=...` | Intelligence confidence/status/evidence/warnings |
| `GET /v1/devices/...` history/polling routes | Backward-compatible device-scoped versions of history/performance APIs |
| `GET /docs` | Swagger/OpenAPI UI |

Full parameters, limits, time semantics, error behavior, export formats, and device/controller route mapping are documented in [`docs/api-reference.md`](docs/api-reference.md).

## History and retained controller records

Time-series ranges use timezone-aware RFC 3339/ISO-8601 timestamps and half-open semantics:

```text
from <= observed_at < to
```

Controller-scoped history combines all preserved `history_device_ids` **before** bucket/statistics calculation. Raw points retain `source_device_id`; aggregated buckets intentionally represent the physical controller timeline.

For supported Ethernet TriStar MPPT controllers, optional LiveView backfill retrieves retained daily summaries in a background task after a successful live poll. Those records remain separate from `poll_samples`; a daily summary is never expanded into fabricated high-frequency observations.

See [`docs/telemetry-history.md`](docs/telemetry-history.md) and [`docs/controller-history-backfill.md`](docs/controller-history-backfill.md).

## Evidence and fixture policy

The project keeps these evidence classes separate:

- **vendor-documented** — grounded in indexed Morningstar source material;
- **software-tested** — exercised by ordinary unit/integration tests;
- **fixture-verified** — exercised through a committed capture/replay fixture;
- **physical-device-verified** — confirmed by a reviewed recording from known hardware/firmware.

The checked-in TriStar MPPT firmware-29 fixture is `synthetic-spec-derived`; it provides deterministic replay coverage but does **not** claim physical hardware verification.

See [`docs/hardware-verification.md`](docs/hardware-verification.md).

## Official Morningstar source maintenance

The authoritative source index is [`docs/vendor/morningstar/sources.json`](docs/vendor/morningstar/sources.json). Complete Morningstar PDFs are not republished in this repository; local/CI scans obtain approved artifacts from Morningstar and retain SHA-256 provenance.

```bash
python -m morningstar_modbus.maintenance validate
python -m morningstar_modbus.maintenance scan
python -m morningstar_modbus.maintenance scan --use-cache
```

See [`docs/catalog-maintenance.md`](docs/catalog-maintenance.md) and [`catalog-proposals/README.md`](catalog-proposals/README.md).

## Development and validation

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```
