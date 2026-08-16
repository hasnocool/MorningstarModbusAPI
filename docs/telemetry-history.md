# Telemetry history and time-series API

MorningstarModbusAPI stores each **persisted telemetry snapshot** as an immutable `poll_samples` row and stores its decoded/raw register observations in `register_values`. Historical query APIs read those persisted rows directly; they do not replace them with lossy rollups.

Live Modbus polling and persistent history cadence are intentionally separate. A controller may be read faster than the database is updated. `[database].telemetry_write_interval_seconds` has a minimum of `1.0`, so normal poll-driven history is persisted no faster than once per second per physical controller even when live polling is sub-second.

Intermediate live polls still drive runtime lifecycle/intelligence and automatic interval evaluation but do not necessarily become history rows.

## Query scopes

There are two raw-history scopes:

- **controller-scoped** — preferred for applications; combines every historical `device_id` belonging to one physical controller;
- **device-scoped** — compatibility/raw view over exactly one telemetry-owning `device_id`.

Raw ownership remains device-based:

```text
devices
   |
   v
poll_samples
   |  observed_at / latency / profile
   v
register_values
      register_name / address / function
      raw words / numeric or text value / unit
```

Physical-controller scope is layered over those immutable rows:

```text
controller_uid
    |
    +-- canonical_device_id
    `-- history_device_ids[]
              |
              v
        authoritative raw rows
```

Existing histories are not rewritten. Controller-scoped raw results expose `source_device_id` so storage provenance remains visible.

## Raw and aggregated history

Controller routes:

```http
GET /v1/controllers/{controller_uid}/samples
GET /v1/controllers/{controller_uid}/registers/{name}/history
GET /v1/controllers/{controller_uid}/registers/history
GET /v1/controllers/{controller_uid}/registers/stats
GET /v1/controllers/{controller_uid}/history/summary
GET /v1/controllers/{controller_uid}/history/export
```

Device compatibility routes provide the same raw-storage concepts under `/v1/devices/...` with a `device_id`.

Multi-register history supports resolutions such as `raw`, `1m`, `5m`, `15m`, `1h`, and `1d`. Numeric buckets expose count/min/max/avg/first/last; text/state buckets expose sample count, first/last state, and transitions.

Controller member histories are combined **before** bucketing/statistics so endpoint changes do not split one physical-controller timeline.

## Time ranges

Timestamp-based history endpoints use RFC 3339 / ISO-8601 timestamps with explicit timezone and half-open semantics:

```text
from <= observed_at < to
```

Daily retained-history/reconciliation/energy routes use `YYYY-MM-DD` with the same inclusive-start / exclusive-end concept at day resolution.

## Streaming export and guardrails

Large controller/device history exports support streaming `csv` and `jsonl` responses. Normal JSON history endpoints are bounded; oversized requests return `413`, so callers should narrow ranges, request fewer registers, use coarser resolution, or use streaming export.

Raw controller exports include both `controller_uid` and `source_device_id`. Aggregated controller exports include `controller_uid` and may intentionally span several historical source device rows.

## Controller-retained daily history is a separate source

Supported retained-history providers persist controller daily records separately from raw Modbus polling:

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
```

These records can provide daily evidence for periods where local polling history is absent, but they are never expanded into fake `poll_samples` or `register_values` rows.

Typical retained evidence can include controller-reported daily Wh/Ah, voltage limits, array/output maxima, temperatures, charge-stage durations, alarms, faults, and retrieval/source metadata.

See [`controller-history-backfill.md`](controller-history-backfill.md).

## v0.6 evidence coverage and gap reconciliation

v0.6 adds a read-time layer that compares persisted live history with retained daily evidence:

```http
GET /v1/controllers/{controller_uid}/history/coverage
GET /v1/controllers/{controller_uid}/history/gaps
```

Coverage is intentionally **day-level evidence coverage**, not high-frequency sample completeness.

A day can be:

- covered by persisted live samples;
- `recovered` by a complete retained controller daily record despite zero persisted live samples;
- `partial` when only incomplete retained daily evidence exists;
- `missing` when neither source exists.

This layer does not insert rows or alter historical ownership. It joins evidence at read time.

## v0.6 power-to-energy integration

Power and energy remain distinct physical quantities. Historical power statistics must not be relabeled as energy.

v0.6 introduces explicit timestamp-aware controller energy accounting:

```http
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

The API preserves two independent sources when available:

- **controller-reported daily energy** — retained `charge_wh` evidence from the controller;
- **locally integrated energy** — trapezoidal integration of persisted `output_power` observations.

Local integration is gap-bounded. Adjacent power samples are integrated only when their separation is less than or equal to `max_gap_seconds` (default `300`, accepted range `1..3600`). Larger intervals are skipped rather than assuming constant power through an outage.

When both sources exist, discrepancy fields help identify incomplete persistence, long sampling gaps, integration bias, or source differences. Quality metadata reports sample counts, integrated time, skipped time, retained-record completeness, and provenance.

See [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).

## Authority and provenance rules

The history model deliberately keeps these concepts separate:

| Source | What it proves |
| --- | --- |
| persisted `poll_samples` / `register_values` | A local observation was actually persisted at that timestamp |
| controller-retained daily record | The controller retained a daily summary for that controller day |
| locally integrated `output_power` | An estimate calculated only across persisted observations and accepted time gaps |
| system/site derived metric | A normalized/derived view above one or more controllers with explicit quality |

None of these silently replaces another.

A persisted history gap does not prove no in-memory Modbus reads occurred. A retained daily record does not prove exact intra-day behavior. A local integral does not become vendor-reported energy. A system aggregate does not become a vendor register fact.

## Indexing and migration safety

Schema evolution remains additive where practical. Identity improvements add mapping tables rather than destructively rewriting historical telemetry foreign keys. Primary access patterns are indexed around device/time scans, register/sample scans, controller membership resolution, retained-history device/day scans, and polling-performance history.

## Retention policy

The history layer does not automatically delete or irreversibly downsample persisted raw telemetry. The independent poll/persistence cadence limits unnecessary growth before rows are committed.

Future archival/materialized-rollup/pruning policies can be added separately when real database growth and deployment requirements justify them.

For the complete HTTP route reference, see [`api.md`](api.md). For controller identity see [`controller-scoped-data.md`](controller-scoped-data.md). For polling cadence see [`polling-performance.md`](polling-performance.md).
