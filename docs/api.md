# HTTP API guide

MorningstarModbusAPI exposes a read-only FastAPI service over persisted telemetry, controller identity, history, polling performance, catalog metadata, effective register semantics, and verification evidence.

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

- `watch` — persisted samples from normal watcher polling;
- `benchmark` — samples from `benchmark-polling`;
- `all` — both modes.

Examples:

```bash
curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/polling/performance?mode=watch&window=300'

curl 'http://127.0.0.1:8080/v1/controllers/ctrl_0123456789abcdef0123456789abcdef/polling/history?mode=benchmark&limit=100'
```

Watcher performance rows follow the normal watcher persistence cadence. If the service is polling a controller faster than `database.telemetry_write_interval_seconds`, the API's watcher `poll_rate_hz` describes persisted performance rows and is not necessarily the instantaneous in-memory Modbus read rate used by automatic interval evaluation.

Explicit `benchmark-polling` persistence is separate and can record at the requested benchmark cadence. Use `--no-persist` to avoid storing benchmark samples.

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
| `404` | Unknown controller/device/catalog profile, missing intelligence, or no latest sample where a latest record was requested |
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

### Effective register map and reserved ranges

`GET /v1/devices/register-map?device_id=...` uses the persisted intelligence profile and firmware to build the effective catalog view for that exact device.

The response contains:

- `profile`, `family`, `catalog_revision`, and resolved `firmware`;
- firmware-applicable read `blocks`;
- firmware-applicable named `registers`;
- firmware-applicable `reserved_ranges`.

A reserved range is not a missing semantic mapping. It means Morningstar explicitly documents one or more words inside a readable block as reserved. Broad profile reads can still retain those words under raw evidence names such as `holding_0x003F`, but consumers should not assign a semantic label to them.

Example shape:

```json
{
  "profile": "tristar_mppt",
  "firmware": "32",
  "reserved_ranges": [
    {
      "address": 5,
      "count": 19,
      "function": "holding",
      "description": "Reserved RAM words 0x0005-0x0017 in the TriStar MPPT v11 map."
    }
  ],
  "registers": [
    {
      "name": "battery_voltage",
      "address": 24,
      "function": "holding",
      "words": 1,
      "decoder": "tristar_voltage",
      "unit": "V",
      "category": "telemetry"
    }
  ]
}
```

The actual response also includes firmware-gate fields on blocks/registers/reserved ranges. Frontends should prefer named registers for semantic telemetry, suppress duplicate raw aliases that overlap named or reserved addresses, and keep genuinely unknown raw addresses visible when diagnostic evidence is desired.

For the TriStar MPPT v11 catalog, documented reserved spans currently include `0x0005-0x0017`, `0x002D`, `0x003F`, `0x004A`, and `0xE0C4-0xE0CB`. These are source-backed catalog facts rather than heuristic UI exclusions.

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

Catalog responses describe declarative product/register knowledge and independent verification metadata. Detailed profile responses include named register definitions, read blocks, and any source-backed `reserved_ranges`. They are separate from runtime controller/device intelligence.

The detailed catalog is the family-level declaration; `/v1/devices/register-map` is the firmware-filtered device-specific effective view.

## Polling versus persistence

The HTTP service exposes persisted data. Normal watcher polling can happen more frequently than SQLite history/performance rows are written.

`database.telemetry_write_interval_seconds` has a minimum of `1.0` second and limits normal poll-driven persistence per physical controller. A numeric watcher interval such as `0.2` seconds or an automatically selected sub-second stage can therefore produce several live reads between persisted snapshots.

This distinction affects interpretation of latest/history/performance timestamps but not the read-only transport behavior. Event-driven presence/identity updates and retained-history backfill have their own persistence paths, and explicit benchmark persistence is independent of the watcher limiter.

A database persistence failure is logged as a storage problem; it does not retroactively make a successful Modbus read a controller communication failure or force lifecycle reconnect/backoff by itself.

## Read-only safety boundary

The HTTP API exposes observation, history, identity, diagnostics, catalog, and verification-related data only. It does not expose:

- write-register operations;
- coil writes;
- reset/equalize triggers;
- configuration mutation;
- arbitrary Modbus function-code passthrough.

The runtime Modbus operations remain limited to the read paths required for discovery and telemetry.
