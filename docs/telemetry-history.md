# Telemetry history and time-series API

MorningstarModbusAPI stores every successful poll as an immutable `poll_samples` row and stores every decoded/raw register observation for that poll in `register_values`. The history API queries that existing data directly; it does not replace raw observations with rollups.

## Storage model

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

The watcher appends a new sample on every successful poll. Historical queries therefore preserve the exact timestamp, Modbus address, holding/input function, raw register words, decoded value, and unit originally stored.

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

## Raw and aggregated resolutions

`GET /v1/devices/registers/history` supports these resolutions:

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

## Multi-register history

Request several chart series in one call by repeating `name`:

```http
GET /v1/devices/registers/history?device_id=DEVICE_ID&name=battery_voltage&name=array_voltage&name=charge_state&from=2026-08-14T00:00:00Z&to=2026-08-15T00:00:00Z&resolution=5m
```

The response groups observations into chart-friendly series:

```json
{
  "device_id": "...",
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

JSON history requests are capped at 20,000 returned points. If a request exceeds that limit, narrow the time range, request fewer registers, select a coarser resolution, or use streaming export.

## Single-register compatibility endpoint

The existing endpoint remains available:

```http
GET /v1/devices/registers/{name}/history
```

It now also accepts `from`, `to`, `order=asc|desc`, and `limit` while preserving the old `device_id` + `limit` behavior.

`GET /v1/devices/samples` accepts the same time-range and ordering filters for poll-level history.

## Statistics

```http
GET /v1/devices/registers/stats?device_id=DEVICE_ID&name=battery_voltage&name=charge_state&from=...&to=...
```

Numeric statistics include count, minimum, maximum, average, first, last, delta, timestamps for extrema/edges, and observed duration.

Text/state statistics include count, first/last state, transition count, per-state observation counts, and observed duration.

## History summary

```http
GET /v1/devices/history/summary?device_id=DEVICE_ID&from=...&to=...
```

The summary reports:

- first and last observations;
- poll sample count;
- register observation count;
- distinct register count;
- poll error count;
- minimum/maximum/average polling latency;
- observed duration;
- current SQLite database file size.

## Streaming export

Large exports use a streaming response so the service does not need to load the full result into memory.

Raw CSV:

```http
GET /v1/devices/history/export?device_id=DEVICE_ID&name=battery_voltage&format=csv&resolution=raw
```

Aggregated JSONL:

```http
GET /v1/devices/history/export?device_id=DEVICE_ID&name=battery_voltage&resolution=1h&format=jsonl
```

Supported formats are `csv` and `jsonl`. Register filters are optional for export; omitting `name` exports every register in the selected range.

Raw CSV is long-form rather than one-column-per-register so it remains stable as catalog profiles evolve:

```text
observed_at,device_id,register_name,address,function,raw,value,unit,kind
```

Aggregated exports contain bucket statistics/state transitions rather than raw words.

## Indexing and migration safety

Schema initialization uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`. Existing databases therefore gain the history-query indexes without destructive migration or rewriting historical telemetry.

The primary access patterns are indexed around device/time poll scans, register-name/sample scans, and device/time poll errors.

## Power versus energy

A power register measured in watts is not automatically an energy measurement. Aggregated `avg`, `min`, and `max` power values remain power statistics.

Energy integration such as Wh/kWh should be implemented separately with explicit integration semantics and coverage handling rather than relabeling an average power sample as energy.

## Retention policy

This layer does not delete or irreversibly downsample historical rows. Raw telemetry remains the source of truth. Optional retention, archival, materialized rollups, and pruning can be added later once real database growth is measured.
