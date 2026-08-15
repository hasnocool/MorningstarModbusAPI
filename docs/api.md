# HTTP API guide

MorningstarModbusAPI exposes a read-only FastAPI service over persisted telemetry, controller identity, history, polling performance, catalog metadata, and verification evidence.

For new integrations, use the **controller-first API** under `/v1/controllers`. The older `/v1/devices` routes remain supported for backward compatibility and raw storage-level inspection.

## Start here

Run the combined watcher/API process:

```bash
morningstar-modbus --config config.toml run
```

The default bind address is `127.0.0.1:8080`.

Useful discovery endpoints:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/v1/controllers
curl http://127.0.0.1:8080/v1/catalog
```

Interactive OpenAPI documentation is available at:

```text
http://127.0.0.1:8080/docs
```

## Which identifier should an application store?

Three identifiers can appear in responses:

| Field | Meaning | Recommendation |
| --- | --- | --- |
| `controller_uid` | Immutable generated identity for one physical controller | **Persist this in new applications** |
| `controller_id` | Current strongest evidence-derived identity alias | Useful for diagnostics; may be promoted as identity evidence improves |
| `device_id` | Raw telemetry-owning storage row / endpoint-era history segment | Use when intentionally querying one storage segment |

A physical controller may have several historical `device_id` values from before canonical identity reconciliation. Controller-scoped queries resolve those members automatically.

Although controller routes are named `{controller_uid}`, the registry also resolves known historical/current `controller_id` aliases for compatibility. Applications should still persist the immutable UID returned by `/v1/controllers`.

See [`controller-scoped-data.md`](controller-scoped-data.md) for the full identity model.

## Controller-first API

### Inventory

```http
GET /v1/controllers
GET /v1/controllers/{controller_uid}
```

The controller inventory is the preferred application-facing view. It includes the immutable UID, current evidence-derived identity, canonical telemetry owner, historical member device IDs, status, and connection history.

Example flow:

```bash
curl http://127.0.0.1:8080/v1/controllers
curl http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef
```

### Latest telemetry and samples

```http
GET /v1/controllers/{controller_uid}/latest
GET /v1/controllers/{controller_uid}/samples
```

Sample query:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/samples?limit=250&order=desc'
```

Controller-scoped samples can span multiple historical raw device IDs. Raw rows include `source_device_id` so provenance is retained.

### Single-register history

```http
GET /v1/controllers/{controller_uid}/registers/{name}/history
```

Example:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/registers/battery_voltage/history?limit=1000&order=asc'
```

### Multi-register history

```http
GET /v1/controllers/{controller_uid}/registers/history
```

Repeat the `name` query parameter to request several series:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/registers/history?name=battery_voltage&name=array_voltage&resolution=5m&order=asc'
```

Supported resolutions are:

- `raw`
- `1m`
- `5m`
- `15m`
- `1h`
- `1d`

Raw controller-scoped points include `source_device_id`. Aggregated points intentionally represent the physical-controller timeline as a whole, so they do not claim one source device ID.

### Register statistics

```http
GET /v1/controllers/{controller_uid}/registers/stats
```

Example:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/registers/stats?name=battery_voltage&name=charge_state'
```

Numeric and text/state registers use different semantics:

- numeric series include count, min/max/avg, first/last, extrema timestamps, duration, and delta where meaningful;
- text/state series include first/last, transition counts, duration, and state occurrence counts.

A sampled average is not automatically a time-weighted physical average.

### History summary

```http
GET /v1/controllers/{controller_uid}/history/summary
```

This reports observation coverage such as first/last sample, counts, latency summary, register-observation counts, error counts, and database size for the selected range.

### Controller-retained daily history

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
```

These routes expose separately persisted controller-retained daily records where the configured backfill source is supported. They are not synthetic replacements for missing raw Modbus samples.

See [`controller-history-backfill.md`](controller-history-backfill.md).

### Streaming export

```http
GET /v1/controllers/{controller_uid}/history/export
```

Supported formats:

- `format=csv`
- `format=jsonl`

Example:

```bash
curl -o telemetry.csv \
  'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/history/export?name=battery_voltage&name=array_voltage&resolution=1m&format=csv'
```

Exports stream rows rather than building the entire result in memory.

Raw controller exports include both `controller_uid` and `source_device_id`. Aggregated controller exports include `controller_uid` and can span several source device IDs.

### Polling performance

```http
GET /v1/controllers/{controller_uid}/polling/performance
GET /v1/controllers/{controller_uid}/polling/history
```

The `mode` query parameter accepts:

- `watch` — normal watcher polling;
- `benchmark` — samples from `benchmark-polling`;
- `all` — both modes.

Examples:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/polling/performance?mode=watch&window=300'

curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/polling/history?mode=benchmark&limit=100'
```

See [`polling-performance.md`](polling-performance.md).

## Time-range semantics

History routes that accept `from` and `to` use normalized UTC timestamps and a half-open range:

```text
from <= observed_at < to
```

Timestamps must include a timezone.

Example:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/registers/history?name=battery_voltage&from=2026-08-01T00:00:00-07:00&to=2026-08-02T00:00:00-07:00&resolution=15m'
```

Daily retained-history routes use `YYYY-MM-DD` dates instead of timestamps.

## Query limits and oversized responses

Normal JSON history endpoints are deliberately bounded. Current guardrails include:

- up to 50 requested register names per multi-register query;
- up to 20,000 JSON history points for the normal multi-register response;
- route-specific `limit` bounds on sample/history lists.

If a history query is too large, the API returns HTTP `413`. Narrow the time range, request fewer registers, use a coarser resolution, or use the streaming export endpoint.

## Common HTTP errors

| Status | Meaning |
| --- | --- |
| `400` | Invalid timestamp, range, order, resolution, mode, export format, or other query input |
| `404` | Unknown controller/device/catalog profile, or no latest sample where a latest record was requested |
| `413` | A bounded JSON history query exceeds the allowed point count |

The service does not return HTTP mutation endpoints because controller writes are outside the project contract.

## Legacy device-scoped API

The `/v1/devices/...` API remains available for applications that already use raw device IDs or need to inspect one telemetry-owning segment directly.

### Inventory and identity

```http
GET /v1/devices
GET /v1/devices/{device_id}
GET /v1/devices/intelligence?device_id=...
GET /v1/devices/register-map?device_id=...
GET /v1/devices/profile/validation?device_id=...
```

The `{device_id:path}` route intentionally supports device IDs containing `/`.

### Raw-device telemetry and history

```http
GET /v1/devices/latest?device_id=...
GET /v1/devices/samples?device_id=...
GET /v1/devices/registers/{name}/history?device_id=...
GET /v1/devices/registers/history?device_id=...
GET /v1/devices/registers/stats?device_id=...
GET /v1/devices/history/summary?device_id=...
GET /v1/devices/history/controller-daily?device_id=...
GET /v1/devices/history/controller-daily/summary?device_id=...
GET /v1/devices/history/export?device_id=...
GET /v1/devices/polling/performance?device_id=...
GET /v1/devices/polling/history?device_id=...
```

These routes deliberately remain scoped to exactly one `device_id`; they do not automatically merge pre-migration history segments. Prefer controller routes when the user concept is "this physical controller" rather than "this raw storage row".

## Catalog API

```http
GET /v1/catalog
GET /v1/catalog/{profile_name}
```

Catalog responses describe declarative product/register knowledge and independent verification metadata. They are separate from runtime controller/device intelligence.

## Read-only safety boundary

The HTTP API exposes observation, history, identity, diagnostics, catalog, and verification-related data only. It does not expose:

- write-register operations;
- coil writes;
- reset/equalize triggers;
- configuration mutation;
- arbitrary Modbus function-code passthrough.

The runtime Modbus operations remain limited to the read paths required for discovery and telemetry.
