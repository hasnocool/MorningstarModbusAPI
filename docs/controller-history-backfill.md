# Controller-retained history backfill

MorningstarModbusAPI can supplement local telemetry gaps with daily records retained inside supported Morningstar controllers. Retained history is deliberately separate from raw polling history: a controller daily record is never inserted as a fabricated high-frequency `poll_samples` observation.

For new integrations, retained history should normally be read through the immutable physical-controller API. Legacy device-scoped routes remain available for exact raw storage ownership.

## Supported source

The currently verified backend targets Ethernet-connected `tristar_mppt` devices such as the TS-MPPT-60/45 family and reads the controller's built-in LiveView datalog at `/datalog.html`.

The controller can retain roughly 200 daily records depending on logger configuration and available memory. `max_days` is therefore a processing/safety cap, not a retention guarantee.

The project does **not** guess undocumented historical Modbus register indexing. Serial-only retained-history retrieval remains unsupported until a verified read-only protocol is available.

## Recovered fields and provenance

When present in LiveView, retained records can include event count/hourmeter, min/max battery voltage, max array voltage/output power, daily Ah/Wh, battery temperature limits, Absorption/Float/Equalize duration, faults, alarms, and the original parsed datalog row.

Each row preserves provenance including source, source path, retrieval timestamp, day offset, completeness, inferred day boundaries, and raw source fields. The retained record remains identifiable as controller evidence rather than local polling evidence.

## Non-blocking reconnect behavior

A retained-history sync is scheduled after a successful normal live Modbus poll. The sync runs in its own asyncio task, so HTTP backfill I/O never blocks the Modbus polling loop.

```text
controller offline
      |
      v
controller rediscovered
      |
      v
successful live Modbus poll
      |
      +---- normal watcher persistence if cadence is due
      |
      `---- background retained-history sync
                 |
                 v
          parse retained days
                 |
                 v
       upsert daily history rows
                 |
                 v
       record sync result/status
```

The trigger is the live Modbus result, not whether that specific poll was persisted. A controller can therefore schedule reconnect backfill even when live polling is faster than normal database persistence cadence.

Scheduling is keyed by immutable physical-controller identity. Repeated syncs are idempotent at daily-record granularity.

## Gap semantics

A complete retained day with zero persisted local `poll_samples` can supplement a full-day visibility gap, but it does not reconstruct intra-day observations.

Important distinctions:

- `live_sample_count` refers to persisted local poll samples inside the retained day's boundaries;
- `fills_full_day_gap=true` means complete retained daily evidence exists while persisted local samples are absent;
- the current day is incomplete and is not treated as a recovered complete day;
- retained daily evidence says nothing about exact five-second/minute telemetry that was never persisted;
- calendar-day mapping is auditable through the stored day offset, retrieval time, timezone-derived boundaries, and raw source fields.

Use an IANA `calendar_timezone` such as `America/Vancouver` when local-day/DST alignment matters; `local` uses the host timezone.

## Preferred retained-history API

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
```

Daily `from`/`to` ranges use `YYYY-MM-DD` and inclusive-start / exclusive-end semantics.

Legacy storage-level routes remain available:

```http
GET /v1/devices/history/controller-daily?device_id=DEVICE_ID
GET /v1/devices/history/controller-daily/summary?device_id=DEVICE_ID
```

## v0.6 reconciliation layer

Backfill answers **what the controller retained**. The v0.6 analytics layer answers **what that retained evidence means for continuity and energy quality**.

```http
GET /v1/controllers/{controller_uid}/history/coverage
GET /v1/controllers/{controller_uid}/history/gaps
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

The relationship is:

```text
persisted live poll history -----------+
                                        |
controller-retained daily history -----+--> read-time reconciliation analytics
                                             |-- live-vs-daily day coverage
                                             |-- recovered / partial / missing gaps
                                             |-- controller-reported daily energy
                                             |-- bounded local output_power integration
                                             `-- discrepancy + quality/provenance
```

The analytics layer never copies retained rows into `poll_samples`. It joins evidence at read time and reports the source explicitly.

See [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).

## Configuration

```toml
[backfill]
enabled = true
on_startup = true
on_reconnect = true
max_days = 200
calendar_timezone = "local"
http_port = 80
http_path = "/datalog.html"
timeout_seconds = 3.0
max_response_bytes = 1048576
```

A slow/unreachable retained-history source does not block live telemetry. Response size and processed-day count are bounded.

## Failure handling

Live telemetry remains the priority. If a retained-history source is unavailable, times out, exceeds configured response limits, or changes to an unrecognized format, the background sync records the failure and exits without changing raw poll history. A later restart or reconnect can retry.

## Provenance boundary

Use retained history to answer questions such as what daily min/max/energy/event summary the controller retained, how many complete retained days are available, and whether a full-day persisted-visibility gap has daily controller evidence.

Do **not** use it to claim exact intra-day telemetry that was never collected or to infer that no unstored in-memory reads occurred.

For route/query details see [`api.md`](api.md), for raw persistence semantics see [`telemetry-history.md`](telemetry-history.md), and for v0.6 reconciliation/energy semantics see [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).
