# MorningstarModbusAPI

MorningstarModbusAPI is a read-only Morningstar Modbus data service for USB / RS-232 / RS-485 (RTU) and Modbus TCP/IP devices.

It discovers supported Morningstar devices, identifies them conservatively, reads and decodes telemetry, retains raw and interpreted values in SQLite, and exposes the result through a stable HTTP API. The project also includes hardware-verification and capture/replay tooling so protocol behavior can be regression-tested from recorded Modbus traffic instead of only hand-written mocks.

The project does **not** expose Modbus write operations. Vendor specifications may document write-capable registers and coils, but the runtime service remains a read-only boundary.

## Current capabilities

- Automatic PySerial USB/serial enumeration.
- Modbus RTU over USB serial adapters, RS-232, and RS-485 adapters.
- Modbus TCP over explicit hosts or explicitly configured bounded local CIDRs.
- Standard Modbus Read Device Identification (`0x2B / 0x0E`) when supported.
- Conservative read-only family fingerprints for older devices that do not provide useful identification.
- A Morningstar-wide declarative catalog with product-specific register maps, scaling, enums, alarms, faults, metadata, communications capabilities, firmware gates, and source references.
- Device intelligence combining identity, metadata reads, firmware compatibility, capability negotiation, confidence scoring, and post-poll plausibility validation.
- Exact read-only Modbus capture for TCP and RTU, preserving request/response frames, PDUs, request shape, timing, and failures.
- Strict capture replay through the same production protocol parsers used for live devices.
- Hardware/replay verification reports plus a separate catalog verification-evidence registry.
- Explicit in-memory device lifecycle tracking with reconnect/backoff behavior and stale-endpoint removal.
- SQLite/WAL telemetry history using non-blocking `aiosqlite` access.
- Separately persisted device-intelligence records so confidence/identity can change without rewriting telemetry history.
- FastAPI JSON endpoints plus automatic OpenAPI documentation.
- Automated catalog-maintenance tooling for official-source validation, conservative PDF extraction, advisory diffs, and reviewed provenance.

The latest published release is **v0.3.0**. The current `main` branch also includes hardware verification/capture/replay and lifecycle changes merged after that release.

## Package layout

```text
src/morningstar_modbus/
├── catalog/         # vendor-derived profiles + independent verification evidence
├── intelligence/    # identity, firmware compatibility, confidence, validation
├── maintenance/     # official-source validation and advisory PDF/spec scanning
├── capture.py       # read-only capture bundle writer
├── replay.py        # strict capture replay client
├── verification.py  # live/replay verification report generation
├── lifecycle.py     # in-memory device lifecycle and retry/backoff state
├── api.py           # FastAPI presentation layer
├── discovery.py     # transport discovery + intelligence resolution
├── storage.py       # SQLite/WAL persistence
├── watcher.py       # polling, reconnect, lifecycle, intelligence refresh
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

Perform one raw Modbus read:

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

### Run continuously

```bash
morningstar-modbus --config config.toml watch
morningstar-modbus --config config.toml serve
morningstar-modbus --config config.toml run
```

By default the API binds to `127.0.0.1:8080`.

## Device lifecycle and retry policy

The watcher tracks an **in-memory** lifecycle:

```text
discovered → connecting → online → degraded → offline → rediscovering → online
```

It records consecutive failures, reconnect count, endpoint-change count, last discovery time, last successful poll time, offline-since time, and retry delay. A missing device is not polled through its stale endpoint, and failed clients are closed before retry.

```toml
[watch]
failure_threshold = 3
retry_backoff_initial_seconds = 2.0
retry_backoff_max_seconds = 60.0
```

This detailed lifecycle is not currently persisted as its own SQLite record or exposed as a dedicated API object. The persisted `devices.status` field remains the simpler storage-level `online`/`error` view.

## HTTP API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness and package version |
| `GET /v1/catalog` | Compact Morningstar catalog summary including verification metadata |
| `GET /v1/catalog/{profile_name}` | Detailed profile/register definition plus verification metadata |
| `GET /v1/devices` | Persisted discovered-device records and storage-level status |
| `GET /v1/devices/{device_id}` | One persisted device record; path form supports IDs containing `/` |
| `GET /v1/devices/latest?device_id=...` | Latest persisted telemetry sample |
| `GET /v1/devices/samples?device_id=...&limit=100` | Historical samples |
| `GET /v1/devices/registers/{name}/history?device_id=...` | Named-register time series |
| `GET /v1/devices/intelligence?device_id=...` | Persisted identity/firmware/capability evidence |
| `GET /v1/devices/register-map?device_id=...` | Effective firmware-filtered register map |
| `GET /v1/devices/profile/validation?device_id=...` | Confidence, intelligence status, evidence, and warnings |
| `GET /docs` | Swagger/OpenAPI UI |

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
