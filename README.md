# MorningstarModbusAPI

MorningstarModbusAPI is a read-only Morningstar Modbus data service for USB / RS-232 / RS-485 (RTU) and Modbus TCP/IP devices.

Its job is deliberately narrow: discover supported Morningstar devices, identify them conservatively, read and decode telemetry, retain raw and interpreted values in SQLite, and expose the result through a stable HTTP API. The project also includes a hardware-verification and capture/replay layer so protocol behavior can be tested against recorded Modbus traffic instead of only hand-written mocks.

The project does **not** expose Modbus write operations. Vendor specifications may document write-capable registers and coils, but the runtime service remains a read-only boundary.

## Current capabilities

- Automatic PySerial USB/serial enumeration.
- Modbus RTU over USB serial adapters, RS-232, and RS-485 adapters.
- Modbus TCP over explicit hosts or explicitly configured bounded local CIDRs.
- Standard Modbus Read Device Identification (`0x2B / 0x0E`) when supported.
- Conservative read-only family fingerprints for older devices that do not provide useful identification.
- A Morningstar-wide declarative device catalog with product-specific register maps, scaling, enums, alarms, faults, metadata, communications capabilities, and source references.
- Firmware-aware register and block gating through `since_firmware` / `until_firmware` metadata.
- Device intelligence combining identity, metadata reads, firmware compatibility, capability negotiation, confidence scoring, and post-poll plausibility validation.
- Exact read-only Modbus capture for TCP and RTU, including raw request/response frames, timing, decoded words, and failures.
- Strict capture replay through the same production protocol parsers used for live devices.
- Hardware verification reports that distinguish vendor documentation, software/replay coverage, fixture evidence, and physical-device evidence.
- Explicit device lifecycle tracking with reconnect/backoff behavior and stale-endpoint removal.
- SQLite/WAL telemetry history using non-blocking `aiosqlite` access.
- A separate persisted device-intelligence record so confidence/identity changes do not rewrite telemetry history.
- FastAPI JSON endpoints plus automatic OpenAPI documentation.
- Automated catalog-maintenance tooling that validates source coverage, downloads official Morningstar source documents, extracts conservative register observations, creates advisory diffs, and enforces reviewed provenance for catalog changes.

The latest published release is **v0.3.0**.

## Package layout

```text
src/morningstar_modbus/
├── catalog/         # declarative Morningstar register/source truth + verification evidence
├── intelligence/    # identity, firmware compatibility, confidence, validation
├── maintenance/     # official-source validation and advisory PDF/spec scanning
├── capture.py       # read-only capture bundle writer
├── replay.py        # strict capture replay client
├── verification.py  # hardware/replay verification report generation
├── lifecycle.py     # device lifecycle, failures, reconnect/backoff state
├── api.py           # FastAPI presentation layer
├── discovery.py     # transport discovery + intelligence resolution
├── storage.py       # SQLite/WAL persistence
├── watcher.py       # polling, reconnect, intelligence refresh
└── ...
```

See [`docs/README.md`](docs/README.md) for the complete documentation index.

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

Structured identifiers are redacted by default. Use `--include-identifiers` only when the resulting bundle will remain appropriately controlled. Raw protocol frames can themselves contain identifying values and must still be reviewed before publication.

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

A verification command exits with status `0` when the report result is `verified` and status `2` otherwise.

### Replay a captured session

```bash
morningstar-modbus replay \
  tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29
```

Replay is strict: request function, address, count, and ordering must match the recording. This makes fixtures useful as protocol regressions rather than loose canned responses.

### Run continuously

```bash
morningstar-modbus --config config.toml watch
morningstar-modbus --config config.toml serve
morningstar-modbus --config config.toml run
```

By default the API binds to `127.0.0.1:8080`. Change `[api]` in the TOML configuration only when another host needs access.

## Device lifecycle and retry policy

The watcher tracks devices through:

```text
discovered → connecting → online → degraded → offline → rediscovering → online
```

A device that disappears from the latest discovery pass is no longer polled through a stale endpoint. Failed clients are closed before retry so a later attempt starts with a fresh connection. Retry timing is configurable:

```toml
[watch]
failure_threshold = 3
retry_backoff_initial_seconds = 2.0
retry_backoff_max_seconds = 60.0
```

## HTTP API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness and package version |
| `GET /v1/catalog` | Compact Morningstar catalog summary, including verification metadata |
| `GET /v1/catalog/{profile_name}` | Detailed register/scaling/state/fault definition for one profile |
| `GET /v1/devices` | Discovered devices and current persisted status |
| `GET /v1/devices/{device_id}` | Device metadata/status; path form supports IDs containing `/` |
| `GET /v1/devices/latest?device_id=...` | Latest persisted telemetry sample |
| `GET /v1/devices/samples?device_id=...&limit=100` | Historical samples |
| `GET /v1/devices/registers/{name}/history?device_id=...` | Named-register time series |
| `GET /v1/devices/intelligence?device_id=...` | Persisted identity/firmware/capability evidence |
| `GET /v1/devices/register-map?device_id=...` | Effective firmware-filtered register map |
| `GET /v1/devices/profile/validation?device_id=...` | Confidence, status, evidence, and validation warnings |
| `GET /docs` | Swagger/OpenAPI UI |

## Evidence and fixture policy

A supported profile can have several different evidence levels. They are intentionally not interchangeable:

- **vendor-documented**: the register definition is grounded in the indexed Morningstar source material;
- **software-tested**: ordinary unit/integration tests exercise the code path;
- **fixture-verified**: a committed capture/replay fixture exercises the production parsing/decoding path;
- **physical-device-verified**: a reviewed recording from known hardware/firmware confirms the observed behavior.

The checked-in TriStar MPPT firmware-29 fixture is explicitly `synthetic-spec-derived`; it provides deterministic replay coverage but does **not** claim physical hardware verification.

See [`docs/hardware-verification.md`](docs/hardware-verification.md) for the capture format, publication checklist, verification interpretation, and fixture workflow.

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
