# MorningstarModbusAPI

MorningstarModbusAPI is a read-only Morningstar Modbus data service for USB / RS-232 / RS-485 (RTU) and Modbus TCP/IP devices.

Its job is deliberately narrow: discover supported Morningstar devices, identify them conservatively, read and decode telemetry, retain both raw and interpreted values in SQLite, and expose the result through a stable HTTP API.

The project does **not** expose Modbus write operations. Vendor specifications may document write-capable registers and coils, but the runtime service remains a read-only boundary.

## Current main-branch capabilities

- Automatic PySerial USB/serial enumeration.
- Modbus RTU over USB serial adapters, RS-232, and RS-485 adapters.
- Modbus TCP over explicit hosts or explicitly configured bounded local CIDRs.
- Standard Modbus Read Device Identification (`0x2B / 0x0E`) when supported.
- Conservative read-only family fingerprints for older devices that do not provide useful identification.
- A Morningstar-wide declarative device catalog with product-specific register maps, scaling, enums, alarms, faults, metadata, communications capabilities, and source references.
- Firmware-aware register and block gating through `since_firmware` / `until_firmware` metadata.
- Device intelligence that combines identity, targeted metadata reads, firmware compatibility, capability negotiation, confidence scoring, and post-poll plausibility validation.
- Continuous rediscovery and reconnect through the watcher.
- Stable serial identity based on USB serial metadata where available, so reconnecting on a different `/dev/ttyUSB*` path does not create a new logical device.
- SQLite/WAL telemetry history using non-blocking `aiosqlite` access.
- A separate persisted device-intelligence record so confidence/identity changes do not rewrite telemetry history.
- FastAPI JSON endpoints plus automatic OpenAPI documentation.
- Automated catalog-maintenance tooling that validates source coverage, downloads official Morningstar source documents, extracts conservative register observations, creates advisory diffs, and enforces reviewed provenance for catalog changes.

The latest published release is **v0.2.0**. `main` also contains the catalog-maintenance layer merged after that release.

## Package layout

```text
src/morningstar_modbus/
├── catalog/         # declarative Morningstar register/source truth
├── intelligence/    # identity, firmware compatibility, confidence, validation
├── maintenance/     # official-source validation and advisory PDF/spec scanning
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

Perform one raw Modbus TCP read:

```bash
morningstar-modbus read \
  --transport tcp \
  --target 192.168.1.50 \
  --unit-id 1 \
  --function holding \
  --address 0x0018 \
  --count 4
```

Perform one raw serial read:

```bash
morningstar-modbus read \
  --transport serial \
  --target /dev/ttyUSB0 \
  --unit-id 1 \
  --baudrate 9600 \
  --stop-bits 2 \
  --address 0x0000 \
  --count 16
```

Watch and persist without serving HTTP:

```bash
morningstar-modbus --config config.toml watch
```

Serve an existing database:

```bash
morningstar-modbus --config config.toml serve
```

Run discovery, polling, persistence, and API together:

```bash
morningstar-modbus --config config.toml run
```

By default the API binds to `127.0.0.1:8080`. Change `[api]` in the TOML configuration only when another host needs access.

## HTTP API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness and package version |
| `GET /v1/catalog` | Compact Morningstar catalog summary |
| `GET /v1/catalog/{profile_name}` | Detailed register/scaling/state/fault definition for one profile |
| `GET /v1/devices` | Discovered devices and current status |
| `GET /v1/devices/{device_id}` | Device metadata/status; path form supports IDs containing `/` |
| `GET /v1/devices/latest?device_id=...` | Latest persisted telemetry sample |
| `GET /v1/devices/samples?device_id=...&limit=100` | Historical samples |
| `GET /v1/devices/registers/{name}/history?device_id=...` | Named-register time series |
| `GET /v1/devices/intelligence?device_id=...` | Persisted identity/firmware/capability evidence |
| `GET /v1/devices/register-map?device_id=...` | Effective firmware-filtered register map |
| `GET /v1/devices/profile/validation?device_id=...` | Confidence, status, evidence, and validation warnings |
| `GET /docs` | Swagger/OpenAPI UI |

Example:

```bash
curl http://127.0.0.1:8080/v1/catalog
curl http://127.0.0.1:8080/v1/devices
curl --get http://127.0.0.1:8080/v1/devices/intelligence \
  --data-urlencode 'device_id=tcp:192.168.1.50:502:unit:1'
```

## TCP discovery policy

The service does not sweep arbitrary networks by default. Configure exact hosts:

```toml
[tcp]
hosts = ["192.168.1.50", "192.168.1.51"]
```

Or explicitly opt into a local CIDR:

```toml
[tcp]
subnets = ["192.168.1.0/24"]
```

Networks larger than 4096 addresses are rejected.

## Device catalog and firmware intelligence

The catalog covers current and legacy Modbus-capable Morningstar families including GenStar MPPT, ReadyEdge, TriStar MPPT 150V/600V, TriStar PWM, ProStar MPPT/PWM, SunSaver MPPT/Duo, SureSine Classic/Gen2, and Relay Driver.

Relay Driver remains intentionally conservative: the profile exists for family selection and raw-block retention while exact named coverage stays pending until its vendor table is fully verified.

The intelligence resolver adds a runtime view of the physical device: model/family evidence, firmware and hardware metadata, effective firmware-gated register map, confidence/status, negotiated capabilities, and plausibility warnings.

See:

- [`docs/device-catalog.md`](docs/device-catalog.md)
- [`docs/device-intelligence.md`](docs/device-intelligence.md)

## Official Morningstar source maintenance

The authoritative source index is [`docs/vendor/morningstar/sources.json`](docs/vendor/morningstar/sources.json). Full Morningstar PDFs are not republished in this repository; the source index and vendor manifest point to Morningstar's official copies, while local/CI scans download exact artifacts into an ignored cache.

Validate the checked-in source/catalog relationship:

```bash
python -m morningstar_modbus.maintenance validate
```

Download the active official source set and generate an advisory report:

```bash
python -m morningstar_modbus.maintenance scan
```

Reuse existing cached artifacts:

```bash
python -m morningstar_modbus.maintenance scan --use-cache
```

The default cache is `docs/vendor/morningstar/cache/`; generated reports go to `catalog-maintenance-report/`. Both are git-ignored.

See [`docs/catalog-maintenance.md`](docs/catalog-maintenance.md) and [`docs/vendor/morningstar/README.md`](docs/vendor/morningstar/README.md).

## Development and validation

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

Catalog/source changes have an additional provenance gate. See [`catalog-proposals/README.md`](catalog-proposals/README.md).
