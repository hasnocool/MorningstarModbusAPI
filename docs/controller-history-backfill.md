# Controller-retained history backfill

MorningstarModbusAPI can supplement local telemetry gaps with daily records retained inside a TriStar MPPT controller. This is deliberately separate from raw polling history: a controller daily record is never inserted as a fabricated high-frequency `poll_samples` observation.

For new integrations, retained history should normally be read through the immutable physical-controller API. Legacy device-scoped routes remain available for exact raw storage ownership.

## Supported source

The first backend targets Ethernet-connected `tristar_mppt` devices such as the TS-MPPT-60/45 family. These controllers expose their built-in LiveView datalog at `/datalog.html`. Morningstar documents the LiveView datalog fields and identifies the `Day` value as a day offset (`-4` means four days ago).

The controller can retain roughly 200 daily records depending on enabled logger fields and available onboard logger memory. The configured `max_days` is therefore a processing/safety cap rather than a guarantee of retention depth.

The historical Modbus indexing mechanism is not publicly documented in the normal TriStar MPPT runtime register map, so this implementation does **not** guess undocumented register addresses. Serial-only controllers remain unsupported by this backend until a verified read-only retrieval protocol is available.

## What is recovered

When present in LiveView, the parser preserves daily fields including:

- event count and hourmeter;
- minimum and maximum battery voltage;
- maximum array voltage and output power;
- daily charge Ah and Wh;
- minimum and maximum battery temperature;
- Absorption, Float, and Equalize minutes;
- faults and alarms;
- original parsed datalog row content.

The raw LiveView values are stored in `raw_json` alongside normalized fields. Provenance also includes source, source path, retrieval timestamp, original `day_offset`, completeness, and inferred UTC day boundaries.

## Reconnect behavior

A history sync is scheduled only after a normal live Modbus poll succeeds. It runs in its own asyncio task, so backfill HTTP I/O never blocks the Modbus polling loop.

```text
controller offline
      |
      v
controller rediscovered
      |
      v
successful live Modbus poll -----> normal poll stored immediately
      |
      `---- background LiveView sync
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

By default a sync is attempted once on process startup for each supported physical controller and again after it recovers from missing/degraded/offline state.

Watcher scheduling is keyed by immutable controller identity, while retained rows remain stored against the canonical/raw telemetry device relationship for compatibility. Controller-scoped read queries resolve those records back through the physical-controller scope.

Repeated syncs are idempotent because daily records use `(device_id, controller_day)` as their primary key.

## Gap semantics

`controller_daily_history.live_sample_count` records how many normal poll samples fall inside the controller day's stored UTC start/end boundaries at synchronization time. A completed controller day with zero live samples is exposed as `fills_full_day_gap=true`.

This does **not** imply that missing five-second or one-minute observations were reconstructed. The controller record is a daily summary and remains explicitly identified as `source=liveview-http`.

The current day (`day_offset=0`) is stored as incomplete and is never counted as a filled full-day gap.

The controller provides relative day offsets rather than an independently verified absolute calendar date. `controller_day` is therefore inferred from the configured calendar timezone and the reported offset. Each row also stores exact UTC day-start/day-end boundaries, `day_offset`, UTC `retrieved_at`, and raw source fields so the mapping is auditable.

Set `calendar_timezone` to an IANA name such as `America/Vancouver` for DST-aware historical day boundaries; `local` uses the host timezone.

## Preferred controller API

List retained/backfilled daily records for one physical controller:

```http
GET /v1/controllers/{controller_uid}/history/controller-daily
```

Optional `from` and `to` use `YYYY-MM-DD` with inclusive-start / exclusive-end semantics. `limit` defaults to 200 and is capped at 500.

Inspect controller-wide retained-history coverage and the latest synchronization result:

```http
GET /v1/controllers/{controller_uid}/history/controller-daily/summary
```

The controller-scoped view follows the immutable physical controller even if older retained-history rows were attached to different historical `device_id` values.

## Legacy device API

Raw storage-level routes remain available:

```http
GET /v1/devices/history/controller-daily?device_id=DEVICE_ID
GET /v1/devices/history/controller-daily/summary?device_id=DEVICE_ID
```

These are intentionally scoped to one raw `device_id`. Prefer the controller routes when the user concept is one physical controller across endpoint/history changes.

## Summary fields

The retained-history summary includes information such as:

- record count;
- completed days;
- completed full-day gaps supplemented by controller history;
- oldest/newest retained dates;
- last retrieval time;
- most recent sync status and error, if any.

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

Operational notes:

- backfill is independent of the normal Modbus poll interval;
- a slow/unreachable LiveView page does not block live telemetry acquisition;
- `max_response_bytes` bounds the HTTP body accepted from the controller;
- `max_days` limits processing but cannot create records that the controller no longer retains.

## Failure handling

Live telemetry remains the priority. If the LiveView page is unavailable, times out, exceeds the configured response cap, or changes to an unrecognized format, the background sync records an error in `controller_history_syncs` and exits without changing raw poll history.

A later restart or reconnection can attempt synchronization again. Existing successful raw telemetry remains untouched regardless of backfill failure.

## Provenance boundary

Controller-retained history is a distinct source class from live Modbus samples. It should be used to answer questions such as:

- what daily min/max/energy/event summary did the controller retain for a day we missed locally?
- how many complete days are available from the controller's onboard history?
- did a restart/reconnect recover a full-day visibility gap?

It should **not** be used to claim exact intra-day telemetry that the controller did not retain.

For route/query details see [`api.md`](api.md). For the relationship between retained history and raw telemetry, see [`telemetry-history.md`](telemetry-history.md).
