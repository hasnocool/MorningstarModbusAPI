# HTTP API guide

MorningstarModbusAPI exposes a read-only FastAPI service over persisted telemetry, physical-controller identity, controller-retained history, reconciliation analytics, energy accounting, polling performance, catalog metadata, device intelligence, and normalized system/site data.

For new integrations, prefer the **controller-first API** under `/v1/controllers` and persist `controller_uid`. Use `/v1/systems` for multi-controller/site views. The older `/v1/devices` routes remain available for raw storage-level compatibility.

## Start here

```bash
morningstar-modbus --config config.toml run
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/v1/controllers
curl http://127.0.0.1:8080/v1/catalog
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8080/docs`.

## Identifiers

| Field | Meaning | Recommendation |
| --- | --- | --- |
| `controller_uid` | Immutable generated identity for one physical controller | **Persist this in new applications** |
| `controller_id` | Current strongest evidence-derived alias | Diagnostics/compatibility; may change as evidence improves |
| `device_id` | Raw telemetry-owning storage row / historical endpoint segment | Use only when intentionally querying one storage segment |
| `system_uid` | Persistent grouping above one or more physical controllers | System/site API |

Controller-scoped reads resolve all historical member `device_id` values and preserve `source_device_id` on raw observations.

## Controller-first API

### Inventory and live telemetry

```http
GET /v1/controllers
GET /v1/controllers/{controller_uid}
GET /v1/controllers/{controller_uid}/latest
GET /v1/controllers/{controller_uid}/samples
```

### Register history and statistics

```http
GET /v1/controllers/{controller_uid}/registers/{name}/history
GET /v1/controllers/{controller_uid}/registers/history
GET /v1/controllers/{controller_uid}/registers/stats
```

Multi-register history supports repeated `name` parameters and resolutions including `raw`, `1m`, `5m`, `15m`, `1h`, and `1d`. Raw controller-scoped points include `source_device_id`; aggregated points represent the unified physical-controller timeline.

### Raw history summary and export

```http
GET /v1/controllers/{controller_uid}/history/summary
GET /v1/controllers/{controller_uid}/history/export
```

Exports support streaming `csv` and `jsonl`. Normal JSON history responses are bounded; use streaming export for large ranges.

## Controller-retained daily history

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
```

These routes expose separately persisted controller-retained daily records from verified retained-history providers. They do **not** reconstruct missing high-frequency Modbus samples.

For the TriStar MPPT LiveView backend, a complete retained day may provide fields such as daily Wh/Ah, min/max battery voltage, max array voltage/output power, temperatures, charge-stage durations, alarms, and faults. Provider availability depends on controller family/transport and verified retrieval support.

See [`controller-history-backfill.md`](controller-history-backfill.md).

## v0.6 history reconciliation and coverage

### Day-level evidence coverage

```http
GET /v1/controllers/{controller_uid}/history/coverage
```

Optional `from` and `to` parameters use `YYYY-MM-DD` with inclusive-start / exclusive-end semantics.

The response deliberately distinguishes:

- **realtime coverage** — days containing one or more persisted `poll_samples` rows;
- **daily evidence coverage** — days containing persisted live samples or a complete controller-retained daily record;
- **recovered days** — days with no persisted live samples but complete retained evidence;
- **missing days** — days with neither live samples nor complete retained evidence;
- the latest retained-history synchronization result.

This is day-level evidence coverage, not a claim that every expected sub-minute sample exists.

### Gap reconciliation

```http
GET /v1/controllers/{controller_uid}/history/gaps
```

A gap is a calendar day with zero persisted live samples. Consecutive days with the same status are grouped.

Statuses:

| Status | Meaning |
| --- | --- |
| `recovered` | No persisted live samples, but a complete controller daily record exists |
| `partial` | No persisted live samples and only incomplete retained evidence exists |
| `missing` | Neither persisted live samples nor retained evidence exists |

Recovered gaps remain daily summaries and are never expanded into synthetic raw telemetry.

See [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).

## v0.6 controller energy accounting

### Daily energy

```http
GET /v1/controllers/{controller_uid}/energy/daily
```

The API keeps independent measurements separate:

- `controller_reported_wh` — energy reported by the controller's retained daily logger;
- `integrated_output_wh` — local trapezoidal integration of persisted `output_power` observations.

`max_gap_seconds` controls the largest interval that local integration may bridge. The default is `300` seconds and accepted values are `1..3600`. Longer intervals are skipped rather than assuming power was constant during an outage.

When both measurements exist, the API reports `difference_wh` and `difference_percent`. Quality fields describe sample count, integrated time, skipped between-sample time, retained-record completeness, and provenance classes.

### Energy range summary

```http
GET /v1/controllers/{controller_uid}/energy/summary
```

This aggregates controller-reported and locally integrated Wh over the requested date range while retaining independent source/day counts. One source is never silently substituted for the other.

## Polling performance

```http
GET /v1/controllers/{controller_uid}/polling/performance
GET /v1/controllers/{controller_uid}/polling/history
```

`mode` accepts `watch`, `benchmark`, or `all`. Watcher polling may run faster than persisted performance/history rows because normal persistence cadence is independently limited.

See [`polling-performance.md`](polling-performance.md).

## System/site API

The `/v1/systems` surface provides normalized multi-controller/site data above immutable controller identities. It includes quality-aware aggregate telemetry/history and, where configured/supported, component graph, topology, power-flow, energy-ledger/balance, unified events, and SSE streams.

See [`system-api.md`](system-api.md) and [`component-graph.md`](component-graph.md) for the canonical route and semantics reference.

## Legacy device-scoped API

The `/v1/devices/...` API remains available for raw storage-level compatibility:

```http
GET /v1/devices
GET /v1/devices/{device_id}
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
GET /v1/devices/intelligence?device_id=...
GET /v1/devices/register-map?device_id=...
GET /v1/devices/profile/validation?device_id=...
```

These routes intentionally query exactly one raw `device_id`. Prefer controller routes for the user concept "this physical controller".

## Catalog API and register semantics

```http
GET /v1/catalog
GET /v1/catalog/{profile_name}
GET /v1/devices/register-map?device_id=...
```

The catalog distinguishes named semantic registers, manufacturer-documented reserved ranges, and genuinely unknown/unmapped raw addresses. Reserved words should not be assigned invented semantic names.

See [`device-catalog.md`](device-catalog.md) and [`device-intelligence.md`](device-intelligence.md).

## Time-range semantics

Timestamp-based history routes use normalized UTC timestamps and half-open ranges:

```text
from <= observed_at < to
```

Timestamps must include a timezone. Daily retained/reconciliation/energy routes use `YYYY-MM-DD` and the same inclusive-start / exclusive-end concept at day resolution.

## Query limits and errors

Normal JSON history endpoints are bounded. Oversized responses return `413`; narrow the range, request fewer registers, use a coarser resolution, or use streaming export.

| Status | Meaning |
| --- | --- |
| `400` | Invalid timestamp/date, range, order, resolution, mode, gap threshold, export format, or other query input |
| `404` | Unknown controller/device/catalog profile, missing intelligence, or no latest sample where one was requested |
| `413` | A bounded JSON history query exceeds the allowed point count |

## Polling versus persistence

The HTTP API exposes persisted observations. Live Modbus polling can run faster than SQLite writes. `database.telemetry_write_interval_seconds` has a minimum of `1.0` second per physical controller, while automatic or numeric polling may operate faster.

Retained-history synchronization has its own persistence path. Reconciliation and energy analytics join sources only at read time; they do not modify raw `poll_samples`.

## Read-only safety boundary

The HTTP API exposes observation, identity, history, reconciliation, energy analysis, diagnostics, catalog, verification, and system/site data only. It does not expose write-register operations, coil writes, reset/equalize triggers, configuration mutation, or arbitrary Modbus function-code passthrough.
