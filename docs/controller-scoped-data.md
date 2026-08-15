# Immutable controller identity and controller-scoped data

MorningstarModbusAPI treats the physical Morningstar controller as the stable application-facing entity while preserving the existing endpoint/device rows as raw storage provenance.

## Identity model

There are now three related identifiers:

- `controller_uid` — generated once and immutable; applications should persist this identifier;
- `controller_id` — the current strongest evidence-derived identity alias, such as a Morningstar serial identity;
- `device_id` — the raw telemetry-owning row retained for backward compatibility and provenance.

A controller can start with weak evidence and later gain stronger evidence without changing its UID:

```text
ctrl_8b17...
    |
    +-- old alias: usb:adapter-1:unit:1
    |
    `-- current alias: morningstar:tristar_mppt:ts123456
```

The old alias remains resolvable. Identity promotion changes which alias is current, not which physical controller the application is referring to.

## Additive schema

This feature adds:

- `physical_controllers` — immutable UID, canonical telemetry device ID, current identity alias, first/last seen;
- `controller_identity_aliases` — all evidence-derived controller IDs that have referred to the same immutable UID.

The existing `controller_identities`, `controller_device_members`, connection/location/evidence tables, `devices`, raw poll/register history, retained daily history, errors, and polling-performance rows are not rewritten.

## Unified history

A physical controller can have historical data under several device IDs from before canonical identity was introduced. Controller-scoped queries resolve the UID to all `controller_device_members` and query those rows as one ordered dataset.

Raw observations retain their original owner as `source_device_id`:

```json
{
  "controller_uid": "ctrl_8b17...",
  "source_device_id": "serial:/dev/ttyUSB0:unit:1",
  "observed_at": "2026-08-14T10:00:00+00:00",
  "value": 13.42
}
```

This gives consumers one continuous controller timeline without mutating evidence.

Controller-scoped aggregation combines member histories before calculating buckets/statistics, so numeric counts/averages and text transition counts are computed over the physical controller timeline rather than merged from already-aggregated endpoint results.

## Controller-first API

`GET /v1/controllers` now includes both `controller_uid` and the compatibility `controller_id`.

Controller-scoped routes use the immutable UID:

- `GET /v1/controllers/{controller_uid}`
- `GET /v1/controllers/{controller_uid}/latest`
- `GET /v1/controllers/{controller_uid}/samples`
- `GET /v1/controllers/{controller_uid}/registers/{name}/history`
- `GET /v1/controllers/{controller_uid}/registers/history`
- `GET /v1/controllers/{controller_uid}/registers/stats`
- `GET /v1/controllers/{controller_uid}/history/summary`
- `GET /v1/controllers/{controller_uid}/history/controller-daily`
- `GET /v1/controllers/{controller_uid}/history/controller-daily/summary`
- `GET /v1/controllers/{controller_uid}/history/export`
- `GET /v1/controllers/{controller_uid}/polling/performance`
- `GET /v1/controllers/{controller_uid}/polling/history`

The legacy `/v1/devices/...` API remains available and keeps its existing device-scoped behavior.

## Runtime ownership

The watcher now receives immutable controller UIDs from `ControllerRegistry`. Its existing endpoint selection, stale-client cleanup, retry/backoff, and history-backfill behavior remains unchanged, but lifecycle ownership no longer resets merely because identity evidence is promoted from endpoint/USB fallback to a Morningstar controller serial.

`benchmark-polling` also registers persistent benchmark results through the controller registry rather than inserting an endpoint-key device directly.

## Provenance and migration behavior

No historical foreign keys are rewritten. Existing installations are bootstrapped by associating each current persisted controller identity with a generated immutable UID. If stronger identity evidence appears later, the current alias changes while the UID and canonical telemetry ownership remain stable.

Raw exports include both `controller_uid` and `source_device_id`. Aggregated exports include `controller_uid`; the aggregate can span multiple source device IDs by design.

## Safety boundary

This is an identity/query architecture change only. It does not add Modbus write operations, controller configuration, resets, equalization triggers, coil writes, or arbitrary function-code passthrough. The service remains read only.
