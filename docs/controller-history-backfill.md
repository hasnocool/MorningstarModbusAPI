# Controller-retained history backfill

MorningstarModbusAPI can supplement local telemetry gaps with the daily records retained inside a
TriStar MPPT controller. This is deliberately separate from raw polling history: a controller daily
record is never inserted as a fabricated high-frequency `poll_samples` observation.

## Supported source

The first backend targets Ethernet-connected `tristar_mppt` devices such as the TS-MPPT-60. These
controllers expose their built-in LiveView datalog at `/datalog.html`. Morningstar documents the
LiveView datalog fields and identifies the `Day` value as a day offset (`-4` means four days ago).
The controller can retain up to roughly 200 daily records, depending on which optional logger fields
are enabled.

The historical Modbus indexing mechanism is not publicly documented in the normal TriStar MPPT
register map, so this implementation does **not** guess undocumented register addresses. Serial-only
controllers remain unsupported by this backend until a verified read-only retrieval protocol is
available.

## What is recovered

When present in LiveView, the parser preserves these daily fields:

- event count and hourmeter;
- minimum and maximum battery voltage;
- maximum array voltage and output power;
- daily charge Ah and Wh;
- minimum and maximum battery temperature;
- Absorption, Float, and Equalize minutes;
- faults and alarms;
- the original text for every parsed datalog row.

The raw LiveView values are stored in `raw_json` alongside normalized numeric fields. Provenance also
includes the source, source path, retrieval timestamp, and original `day_offset`.

## Reconnect behavior

A history sync is scheduled only after a normal live poll succeeds. It runs in its own asyncio task,
so backfill HTTP I/O never blocks the Modbus polling loop.

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

By default a sync is attempted once on process startup for each supported controller and again after
a device recovers from missing/degraded/offline state. Repeated syncs are idempotent because daily
records use `(device_id, controller_day)` as their primary key.

## Gap semantics

`controller_daily_history.live_sample_count` records how many normal poll samples fall inside the
controller day's stored UTC start/end boundaries at synchronization time. A completed controller day
with zero live samples is exposed as `fills_full_day_gap=true`.

This does not imply that missing five-second or one-minute observations were reconstructed. The
controller record is a daily summary and remains explicitly identified as `source=liveview-http`.
The current day (`day_offset=0`) is stored as incomplete and is never counted as a filled full-day
gap.

The controller provides relative day offsets rather than an independently verified calendar date.
`controller_day` is therefore inferred from the configured calendar timezone and the reported offset.
Each row also stores its exact UTC day-start/day-end boundaries, `day_offset`, UTC `retrieved_at`, and
raw source fields so the mapping is auditable. Set `calendar_timezone` to an IANA name such as
`America/Vancouver` for DST-aware historical day boundaries; `local` uses the host timezone.

## API

List retained/backfilled daily records:

```http
GET /v1/devices/history/controller-daily?device_id=DEVICE_ID
```

Optional `from` and `to` use `YYYY-MM-DD` with inclusive start / exclusive end semantics. `limit`
defaults to 200 and is capped at 500.

Inspect coverage and the latest synchronization result:

```http
GET /v1/devices/history/controller-daily/summary?device_id=DEVICE_ID
```

The summary includes record count, completed days, completed full-day gaps supplemented by controller
history, oldest/newest retained dates, last retrieval time, and the most recent sync status/error.

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

`max_days` is a safety/processing cap, not a guarantee that the controller has that many records.
The actual retention depth depends on controller configuration and available onboard logger memory.

## Failure handling

Live telemetry remains the priority. If the LiveView page is unavailable, times out, grows beyond the
configured response cap, or changes to an unrecognized format, the background sync records an error
in `controller_history_syncs` and exits without changing raw poll history. A later restart or
reconnection will attempt synchronization again.
