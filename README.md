# MorningstarModbusAPI

A small, read-only Morningstar Modbus data service for **USB / RS-232 / RS-485 (RTU)** and **Modbus TCP/IP** controllers.

It is designed to do one job well:

> discover Morningstar/Modbus devices, continuously read them, preserve the readings in SQLite, and expose those readings through a stable HTTP API for other applications.

The backend design is derived from the proven transport and scaling patterns in `hasnocool/TriStarMPPT`, but this repository deliberately leaves out the dashboard, analytics, automation, and controller-specific application layers.

## Features

- Automatic USB/serial enumeration through PySerial.
- Modbus RTU over USB serial adapters, RS-232, or RS-485 adapters.
- Modbus TCP over explicit hosts or bounded local CIDRs.
- Standard Modbus device identification (`0x2B / 0x0E`) when supported.
- Fallback endpoint verification via a read-only holding-register probe.
- Continuous rediscovery and reconnect by the watcher.
- Stable serial identity using USB serial metadata when available, so a replugged adapter can move from one `/dev/ttyUSB*` path to another without becoming a new logical device.
- SQLite/WAL telemetry history using non-blocking `aiosqlite` access.
- Raw register retention plus a built-in decoded **TriStar MPPT** profile.
- FastAPI JSON API and automatic OpenAPI docs.
- No Modbus write functions in the initial release.

## Install

Python 3.12+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp config.example.toml config.toml
```

On Linux, make sure the service account can open your serial adapter, commonly by adding it to the `dialout` or equivalent serial-device group.

## CLI

### Discover configured devices

```bash
morningstar-modbus --config config.toml discover
```

### One raw Modbus TCP read

```bash
morningstar-modbus read \
  --transport tcp \
  --target 192.168.1.50 \
  --unit-id 1 \
  --function holding \
  --address 0x0018 \
  --count 4
```

### One raw USB/RS-485/RS-232 read

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

### Watch and persist only

```bash
morningstar-modbus --config config.toml watch
```

### Serve existing database only

```bash
morningstar-modbus --config config.toml serve
```

### Run the complete service

```bash
morningstar-modbus --config config.toml run
```

By default the API binds only to `127.0.0.1:8080`. Change `[api]` in the TOML file if another machine should ingest it.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness/version |
| `GET /v1/devices` | All discovered devices |
| `GET /v1/devices/{device_id}` | Device metadata and status |
| `GET /v1/devices/{device_id}/latest` | Latest poll with register values |
| `GET /v1/devices/{device_id}/samples?limit=100` | Poll history |
| `GET /v1/devices/{device_id}/registers/{name}/history` | Time series for a named register |
| `GET /docs` | Swagger/OpenAPI UI |

Example:

```bash
curl http://127.0.0.1:8080/v1/devices
curl 'http://127.0.0.1:8080/v1/devices/tcp:192.168.1.50:502:unit:1/latest'
```

## TCP discovery

The service intentionally does **not** sweep arbitrary networks by default. Add exact controllers:

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

## Data model

SQLite stores:

- device transport/identity and online/error state;
- poll timestamps and latency;
- raw register words;
- decoded numeric or text values;
- units and register addresses;
- poll errors.

The watcher never requires an API consumer to be online. Consumers can restart independently and query the retained history later.

## TriStar MPPT profile

When Modbus device identification contains Morningstar + TriStar/TS-MPPT, the watcher reads the same primary RAM block used by the established TriStar backend and publishes useful names including:

- `battery_voltage`
- `battery_terminal_voltage`
- `battery_sense_voltage`
- `array_voltage`
- `battery_charge_current`
- `array_current`
- `heatsink_temp`
- `battery_temp`
- `charge_state`
- `target_voltage`
- `input_power`
- `output_power`
- `daily_charge_wh`

All raw words are retained alongside those decoded fields.

## Vendor documentation

Official Morningstar source documents are indexed under [`docs/vendor/morningstar/`](docs/vendor/morningstar/README.md). The repository keeps a verified source catalog and concise implementation notes without vendoring the full vendor PDFs.

Fetch the current official documents into a local ignored cache when needed:

```bash
python tools/fetch_morningstar_docs.py
```

Use `python tools/fetch_morningstar_docs.py --list` to inspect the source catalog without downloading files.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

See [docs/architecture.md](docs/architecture.md) for the runtime design.
