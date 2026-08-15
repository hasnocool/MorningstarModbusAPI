# MorningstarModbusAPI

MorningstarModbusAPI is a read-only Morningstar Modbus telemetry service for USB / RS-232 / RS-485 (RTU) and Modbus TCP/IP devices.

It discovers Morningstar hardware, identifies it conservatively, reads and decodes telemetry, persists raw and interpreted observations in SQLite, reconciles changing USB/IP endpoints into stable physical-controller identities, and exposes both controller-first and legacy device-scoped HTTP APIs. The project also includes polling-performance instrumentation, controller-retained daily-history backfill, hardware verification, and exact capture/replay tooling.

The project does **not** expose Modbus write operations. Vendor specifications may document writable registers and coils, but the runtime remains a read-only boundary.

> **Development status:** the latest published release is **v0.3.0**. Current `main` contains substantial merged work after that release, including lifecycle/reconnect improvements, richer history queries/exports, controller-retained daily-history backfill, polling benchmarking, physical-controller identity, immutable controller UIDs, and controller-scoped history.

## Current capabilities

- Automatic PySerial USB/serial enumeration.
- Modbus RTU over USB serial adapters, RS-232, and RS-485 adapters.
- Modbus TCP over explicit hosts or explicitly configured bounded local CIDRs.
- Standard Modbus Read Device Identification (`0x2B / 0x0E`) when supported.
- Conservative read-only family fingerprints for older devices that do not provide useful identification.
- A Morningstar-wide declarative catalog with product-specific register maps, scaling, enums, alarms, faults, metadata, communications capabilities, firmware gates, and source references.
- Device intelligence combining identity, metadata reads, firmware compatibility, capability negotiation, confidence scoring, and post-poll plausibility validation.
- Persistent physical-controller inventory with connection history and endpoint-reuse protection.
- Generated immutable `controller_uid` values that survive DHCP changes, USB path changes, transport changes, and identity-evidence promotion.
- Controller-scoped history that combines pre-migration `device_id` segments while preserving `source_device_id` provenance.
- In-memory lifecycle tracking with stale-client cleanup, reconnect detection, bounded exponential backoff, and one selected polling connection per physical controller.
- SQLite/WAL telemetry history using non-blocking `aiosqlite` access.
- Multi-register history, numeric/state-aware aggregation, statistics, summaries, and streaming CSV/JSONL export.
- Polling-performance instrumentation plus a safe staged `benchmark-polling` command.
- Provenance-aware recovery of supported controller-retained daily history after startup/reconnect without fabricating raw poll samples.
- Exact read-only Modbus capture for TCP and RTU, preserving request/response frames, PDUs, request shape, timing, and failures.
- Strict capture replay through the same production protocol parsers used for live devices.
- Hardware/replay verification reports plus a separate catalog verification-evidence registry.
- FastAPI JSON endpoints plus automatic OpenAPI documentation.
- Automated catalog-maintenance tooling for official-source validation, conservative PDF extraction, advisory diffs, and reviewed provenance.

## Identity model: controllers vs devices

The service now has three related identifiers:

| Identifier | Meaning | Stability / intended use |
| --- | --- | --- |
| `controller_uid` | One physical Morningstar controller | Immutable; preferred application identifier |
| `controller_id` | Strongest current evidence-derived identity alias | May be promoted as better identity evidence appears |
| `device_id` | Raw telemetry-owning storage row / historical endpoint identity | Preserved for backward compatibility and provenance |

For new integrations, start with `GET /v1/controllers` and persist `controller_uid`. Controller-scoped history automatically spans all historical member `device_id` values for that physical controller. The older `/v1/devices/...` API remains available when an application intentionally needs one raw storage segment.

See [`docs/controller-scoped-data.md`](docs/controller-scoped-data.md) and [`docs/api.md`](docs/api.md).

## Package layout

```text
src/morningstar_modbus/
├── catalog/                         # vendor-derived profiles + independent verification evidence
├── intelligence/                    # identity, firmware compatibility, confidence, validation
├── maintenance/                     # official-source validation and advisory PDF/spec scanning
├── api.py                            # legacy/device API + app construction
├── controller_api.py                 # controller-first FastAPI routes
├── controller_scope.py               # immutable controller UID registry + alias resolution
├── controller_inventory.py           # evidence-derived identity + connection inventory
├── controller_data.py                # controller-scoped history/query/aggregation layer
├── controller_history_*.py           # retained daily-history retrieval/storage/backfill
├── polling.py / polling_storage.py   # performance metrics and benchmark persistence
├── capture.py                        # read-only capture bundle writer
├── replay.py                         # strict capture replay client
├── verification.py                   # live/replay verification report generation
├── lifecycle.py                      # in-memory lifecycle and retry/backoff state
├── discovery.py                      # transport discovery + intelligence resolution
├── storage.py                        # raw SQLite/WAL telemetry persistence
├── watcher.py                        # discovery, identity reconciliation, polling, reconnect, backfill
└── ...
```

See [`docs/README.md`](docs/README.md) for the documentation index.

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

## CLI

Discover configured devices:

```bash
morningstar-modbus --config config.toml discover
```

Perform one raw Modbus read without database persistence:

```bash
morningstar-modbus read \
  --transport tcp \
  --target 192.168.1.50 \
  --unit-id 1 \
  --function holding \
  --address 0x0018 \
  --count 4
```

### Run continuously

```bash
morningstar-modbus --config config.toml watch
morningstar-modbus --config config.toml serve
morningstar-modbus --config config.toml run
```

- `watch` discovers/polls/persists without starting HTTP.
- `serve` serves an existing database without polling hardware.
- `run` starts watcher and API together.

By default the API binds to `127.0.0.1:8080`.

### Benchmark safe polling intervals

Before lowering the normal poll interval, measure a real controller with the same read-only profile path:

```bash
morningstar-modbus --config config.toml benchmark-polling \
  --device /dev/ttyUSB0 \
  --transport serial \
  --samples 12
```

The benchmark tests configured stages from slower to faster and stops at the first stage that violates configured success, latency, deadline, request-failure, or RTU bus-utilization thresholds. Persisted benchmark samples are associated with the same immutable physical-controller identity used by the watcher.

See [`docs/polling-performance.md`](docs/polling-performance.md).

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

A capture bundle separates transport evidence from decoded telemetry: `transactions.jsonl` contains ordered transport exchanges, while `registers.json` contains the raw register words and decoded named values produced by the profile poll.

Structured identifiers are redacted by default. Use `--include-identifiers` only when appropriate. Raw protocol frames can themselves contain identifying values and must still be reviewed before publication.

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

`verify` reports profile/family, model, firmware/hardware revision, transport/unit ID, intelligence status/confidence, block availability, named-register coverage, and a final result. JSON output additionally includes warning messages. Catalog verification evidence is a separate surface exposed through `/v1/catalog` and `/v1/catalog/{profile_name}`.

The command exits with status `0` when the report result is `verified` and status `2` otherwise.

### Replay a captured session

```bash
morningstar-modbus replay \
  tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29
```

Replay is strict: request function, address, count, and ordering must match the recording. This makes fixtures protocol regressions rather than loose canned responses.

## Device lifecycle and reconnect policy

The watcher maintains an in-memory lifecycle for the currently selected polling connection of each physical controller:

```text
discovered → connecting → online → degraded → offline → rediscovering → online
```

It tracks consecutive failures, reconnect count, endpoint-change count, discovery/success timestamps, offline duration, and retry delay. Missing controllers are not polled through stale endpoints, stale clients are closed before replacement, and retries use bounded exponential backoff.

A physical controller can be visible over more than one transport. Connection history is preserved, but normal polling selects only one current connection to avoid duplicate telemetry. When a known controller moves to a new IP or serial path, future telemetry continues under its canonical telemetry ID and immutable `controller_uid`.

```toml
[watch]
failure_threshold = 3
retry_backoff_initial_seconds = 2.0
retry_backoff_max_seconds = 60.0
```

The detailed `DeviceLifecycle` object is still runtime-only. SQLite persists simpler online/error/offline device/controller presence plus identity, connection, telemetry, history, and performance data.

## Controller-retained daily-history backfill

Supported TriStar MPPT Ethernet controllers can expose retained daily records through their built-in LiveView datalog page. Backfill is deliberately separate from raw Modbus polling:

- normal live polling remains authoritative raw telemetry;
- backfill runs after a successful poll on startup/reconnect;
- retained daily records are stored with retrieval/source provenance;
- a retained day can fill a full-day visibility gap, but it is **not** converted into fake per-poll register samples.

Configuration lives under `[backfill]` in `config.example.toml`.

See [`docs/controller-history-backfill.md`](docs/controller-history-backfill.md).

## HTTP API

For new applications, prefer the **controller-first** API. It remains continuous even when old telemetry exists under several endpoint-backed device IDs.

### Controller-first routes

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/controllers` | Physical-controller inventory with immutable UID, identity aliases, status, and connection history |
| `GET /v1/controllers/{controller_uid}` | One physical controller |
| `GET /v1/controllers/{controller_uid}/latest` | Latest telemetry across all historical member device IDs |
| `GET /v1/controllers/{controller_uid}/samples` | Unified sample timeline |
| `GET /v1/controllers/{controller_uid}/registers/{name}/history` | One register across the physical-controller timeline |
| `GET /v1/controllers/{controller_uid}/registers/history` | Multi-register raw or bucketed history |
| `GET /v1/controllers/{controller_uid}/registers/stats` | Numeric/state-aware statistics |
| `GET /v1/controllers/{controller_uid}/history/summary` | Coverage/sample/error summary |
| `GET /v1/controllers/{controller_uid}/history/controller-daily` | Controller-retained daily history |
| `GET /v1/controllers/{controller_uid}/history/controller-daily/summary` | Retained-history coverage summary |
| `GET /v1/controllers/{controller_uid}/history/export` | Streaming CSV/JSONL history export |
| `GET /v1/controllers/{controller_uid}/polling/performance` | Polling-performance summary |
| `GET /v1/controllers/{controller_uid}/polling/history` | Polling-performance samples |

Raw controller-scoped history includes `source_device_id`, so combining old storage segments does not erase provenance.

### Catalog and compatibility routes

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness and package version |
| `GET /v1/catalog` | Compact Morningstar catalog summary including verification metadata |
| `GET /v1/catalog/{profile_name}` | Detailed profile/register definition plus verification metadata |
| `GET /v1/devices` | Raw persisted endpoint/device records for backward compatibility |
| `GET /v1/devices/{device_id}` | One raw persisted device row; path form supports IDs containing `/` |
| `GET /v1/devices/latest?device_id=...` | Latest sample for one raw device ID |
| `GET /v1/devices/samples?device_id=...` | Samples for one raw device ID |
| `GET /v1/devices/registers/{name}/history?device_id=...` | One raw-device register series |
| `GET /v1/devices/registers/history?device_id=...` | Multi-register history for one raw device ID |
| `GET /v1/devices/registers/stats?device_id=...` | Register statistics for one raw device ID |
| `GET /v1/devices/history/summary?device_id=...` | One raw-device history summary |
| `GET /v1/devices/history/controller-daily?device_id=...` | Retained daily records attached to one device ID |
| `GET /v1/devices/history/export?device_id=...` | Streaming raw-device history export |
| `GET /v1/devices/polling/performance?device_id=...` | Raw-device polling summary |
| `GET /v1/devices/polling/history?device_id=...` | Raw-device polling samples |
| `GET /v1/devices/intelligence?device_id=...` | Persisted identity/firmware/capability evidence |
| `GET /v1/devices/register-map?device_id=...` | Effective firmware-filtered register map |
| `GET /v1/devices/profile/validation?device_id=...` | Confidence, intelligence status, evidence, and warnings |
| `GET /docs` | Swagger/OpenAPI UI |

See [`docs/api.md`](docs/api.md) for query semantics, resolutions, limits, exports, identifiers, and examples.

## Evidence and fixture policy

The project keeps these evidence classes separate:

- **vendor-documented**: grounded in indexed Morningstar source material;
- **software-tested**: exercised by ordinary unit/integration tests;
- **fixture-verified**: exercised through a committed capture/replay fixture;
- **physical-device-verified**: confirmed by a reviewed recording from known hardware/firmware.

The checked-in TriStar MPPT firmware-29 fixture is `synthetic-spec-derived`; it provides deterministic replay coverage but does **not** claim physical hardware verification. The independent verification registry currently marks TriStar MPPT document/software evidence as verified, fixture evidence as synthetic, and hardware evidence as pending.

See [`docs/hardware-verification.md`](docs/hardware-verification.md).

## Official Morningstar source maintenance

The authoritative source index is [`docs/vendor/morningstar/sources.json`](docs/vendor/morningstar/sources.json). Complete Morningstar PDFs are not republished in this repository; local/CI scans obtain exact artifacts from Morningstar and retain SHA-256 provenance.

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

The normal CI matrix validates the supported Python versions defined in `.github/workflows/ci.yml`.
