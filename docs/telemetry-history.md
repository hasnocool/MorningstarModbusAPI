# Telemetry history and time-series API

MorningstarModbusAPI stores every successful poll as an immutable `poll_samples` row and every decoded/raw register observation for that poll in `register_values`. History APIs query that existing data directly; they do not replace raw observations with lossy rollups.

There are two query scopes:

- **controller-scoped** — preferred for applications; combines every historical `device_id` belonging to one physical controller;
- **device-scoped** — compatibility/raw view over exactly one telemetry-owning `device_id`.

## Storage and scope model

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
    v
controller scope
    |
    +-- canonical_device_id
    `-- history_device_ids[]
              |
              v
        authoritative raw rows
```

The watcher appends future polls under the canonical telemetry device ID. Existing pre-canonical histories are not rewritten. Controller-scoped queries join all member device IDs and expose `source_device_id` on raw results so the original storage provenance remains visible.

See [`controller-scoped-data.md`](controller-scoped-data.md).

## Which API should I use?

For a physical controller whose IP/USB path may have changed over time, use:

```http
GET /v1/controllers/{controller_uid}/...
```

For one exact raw storage row, use:

```http
GET /v1/devices/...?device_id=DEVICE_ID
```

The controller routes prevent consumers from manually merging `history_device_ids` and are therefore the recommended integration surface.

## Time ranges

History endpoints accept optional `from` and `to` query parameters using RFC 3339 / ISO-8601 timestamps with an explicit timezone. Values are normalized to UTC.

Ranges use an inclusive start and exclusive end:

```text
from <= observed_at < to
```

Example:

```text
from=2026-08-14T00:00:00Z&to=2026-08-15T00:00:00Z
```

Invalid timestamps/ranges return HTTP `400` rather than being silently corrected.

## Raw and aggregated resolutions

Both controller- and device-scoped multi-register history support these resolutions:

| Resolution | Typical use |
| --- | --- |
| `raw` | Diagnostics and short windows |
| `1m` | Detailed charts |
| `5m` | Daily charts |
| `15m` | Multi-day charts |
| `1h` | Weeks or months |
| `1d` | Long-term trends |

Numeric register buckets return `count`, `min`, `max`, `avg`, `first`, and `last`. This preserves excursions that a simple average could hide.

Text/state registers are not averaged. Their buckets return sample count, first state, last state, and transition count.

For controller scope, member histories are combined **before** bucketing/statistics. This matters when a controller changed endpoint/device ID inside the requested time range: counts, averages, first/last values, and state transitions are calculated over one physical-controller timeline rather than by merging already-aggregated endpoint results.

## Controller-scoped multi-register history

Repeat `name` to request several chart series:

```http
GET /v1/controllers/{controller_uid}/registers/history?name=battery_voltage&name=array_voltage&name=charge_state&from=2026-08-14T00:00:00Z&to=2026-08-15T00:00:00Z&resolution=5m
```

The response includes controller scope metadata:

```json
{
  "controller_uid": "ctrl_...",
  "controller_id": "morningstar:tristar_mppt:ts123456",
  "canonical_device_id": "...",
  "history_device_ids": ["..."],
  "from": "2026-08-14T00:00:00+00:00",
  "to": "2026-08-15T00:00:00+00:00",
  "resolution": "5m",
  "series": [
    {
      "name": "battery_voltage",
      "unit": "V",
      "kind": "numeric",
      "points": [
        {
          "bucket_start": "2026-08-14T00:00:00Z",
          "count": 60,
          "min": 12.8,
          "max": 13.4,
          "avg": 13.1,
          "first": 12.9,
          "last": 13.3
        }
      ]
    }
  ]
}
```

At `resolution=raw`, each point also includes `source_device_id`.

## Device-scoped multi-register history

The compatibility endpoint remains:

```http
GET /v1/devices/registers/history?device_id=DEVICE_ID&name=battery_voltage&name=array_voltage&name=charge_state&from=2026-08-14T00:00:00Z&to=2026-08-15T00:00:00Z&resolution=5m
```

Its response is intentionally scoped to one `device_id` and does not merge other historical member IDs.

## Single-register history

Controller scope:

```http
GET /v1/controllers/{controller_uid}/registers/{name}/history
```

Device compatibility scope:

```http
GET /v1/devices/registers/{name}/history?device_id=DEVICE_ID
```

Both accept `from`, `to`, `order=asc|desc`, and bounded `limit` parameters.

Poll-level sample endpoints follow the same scope distinction:

```http
GET /v1/controllers/{controller_uid}/samples
GET /v1/devices/samples?device_id=DEVICE_ID
```

## Statistics

Controller scope:

```http
GET /v1/controllers/{controller_uid}/registers/stats?name=battery_voltage&name=charge_state&from=...&to=...
```

Device scope:

```http
GET /v1/devices/registers/stats?device_id=DEVICE_ID&name=battery_voltage&name=charge_state&from=...&to=...
```

Numeric statistics include count, minimum, maximum, average, first, last, delta, timestamps for extrema/edges, and observed duration.

Text/state statistics include count, first/last state, transition count, per-state observation counts, and observed duration.

These are statistics over sampled observations. For example, the numeric `avg` is not automatically a time-weighted physical average.

## History summary

Controller scope:

```http
GET /v1/controllers/{controller_uid}/history/summary?from=...&to=...
```

Device scope:

```http
GET /v1/devices/history/summary?device_id=DEVICE_ID&from=...&to=...
```

The summary reports observation/coverage information including:

- first and last observations;
- poll sample count;
- register observation count;
- distinct register count;
- poll error count;
- minimum/maximum/average polling latency;
- observed duration;
- current SQLite database file size.

Controller scope calculates these over all historical member IDs.

## Streaming export

Large exports use a streaming response so the service does not need to load the full result into memory.

Controller raw CSV:

```http
GET /v1/controllers/{controller_uid}/history/export?name=battery_voltage&format=csv&resolution=raw
```

Controller aggregated JSONL:

```http
GET /v1/controllers/{controller_uid}/history/export?name=battery_voltage&resolution=1h&format=jsonl
```

Device-scoped export remains available:

```http
GET /v1/devices/history/export?device_id=DEVICE_ID&name=battery_voltage&format=csv&resolution=raw
```

Supported formats are `csv` and `jsonl`. Register filters are optional; omitting `name` exports every register in the selected range.

Controller raw exports are long-form and include provenance:

```text
observed_at,controller_uid,source_device_id,register_name,address,function,raw,value,unit,kind
```

Device raw exports use:

```text
observed_at,device_id,register_name,address,function,raw,value,unit,kind
```

Aggregated exports contain bucket statistics/state transitions rather than raw words. Controller aggregates may span several `source_device_id` values by design.

## Query guardrails

Normal JSON history requests are deliberately bounded:

- at most 50 requested register names in a multi-register query;
- at most 20,000 returned history points in the normal JSON response;
- endpoint-specific limits for sample/single-register lists.

An oversized normal history query returns HTTP `413`. Narrow the range, request fewer registers, choose a coarser resolution, or use streaming export instead of increasing the in-memory response size.

## Controller-retained daily history is separate

Controller-retained daily records from supported LiveView devices are stored separately from raw Modbus polling. They can document days that are missing from the raw sample history, but they are never expanded into fake `poll_samples` / `register_values` rows.

Use:

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
```

See [`controller-history-backfill.md`](controller-history-backfill.md).

## Indexing and migration safety

Schema initialization remains additive (`CREATE TABLE/INDEX IF NOT EXISTS`) for the current storage design. Identity improvements add mapping tables instead of destructively rewriting historical telemetry foreign keys.

Primary access patterns are indexed around device/time poll scans, register-name/sample scans, polling-performance device/time scans, retained-history device/day scans, and controller membership/identity resolution.

## Power versus energy

A power register measured in watts is not automatically an energy measurement. Aggregated `avg`, `min`, and `max` power values remain power statistics.

Energy integration such as Wh/kWh requires explicit timestamp-aware integration and gap/coverage rules. It should not be implemented by relabeling average power samples as energy.

Controller-retained `charge_wh` values, where supported and correctly decoded from the controller's retained-history source, are separate source-provided daily energy records rather than integrations fabricated by this generic history layer.

## Retention policy

This layer does not delete or irreversibly downsample historical rows. Raw telemetry remains the source of truth. Optional retention, archival, materialized rollups, and pruning can be added later once real database growth is measured.

For the complete HTTP route/query reference, see [`api.md`](api.md).
