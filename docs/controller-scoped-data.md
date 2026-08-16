# Immutable controller identity and controller-scoped data

MorningstarModbusAPI treats the physical Morningstar controller as the stable application-facing entity while preserving endpoint/device rows as raw storage provenance.

## Identity model

There are three related identifiers:

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

The old alias remains resolvable. Identity promotion changes which alias is current, not which physical controller the application refers to.

## Additive schema and historical ownership

The controller identity layer adds persistent physical-controller records and identity aliases while retaining the existing device, connection, location/evidence, raw poll/register history, controller-retained daily history, error, and polling-performance rows.

Historical foreign keys are not rewritten merely to make queries convenient. Raw observations remain owned by their original `device_id`.

## Unified physical-controller history

A physical controller can have historical data under several device IDs. Controller-scoped queries resolve the immutable UID to all historical members and query them as one ordered dataset.

Raw observations retain their original owner:

```json
{
  "controller_uid": "ctrl_8b17...",
  "source_device_id": "serial:/dev/ttyUSB0:unit:1",
  "observed_at": "2026-08-14T10:00:00+00:00",
  "value": 13.42
}
```

Controller-scoped aggregation combines member histories before calculating buckets/statistics, so results describe the physical-controller timeline rather than merging independently aggregated endpoint summaries.

## Retained daily evidence

Controller-retained daily history is also resolved through the immutable physical-controller scope. A retained row may have been attached to a historical `device_id`, but controller routes follow the physical controller and select the relevant retained evidence across its member rows.

Retained daily evidence remains a separate provenance class from raw polling. It is never expanded into fabricated high-frequency observations.

## v0.6 reconciliation and energy analytics

The v0.6 analytics layer is controller-scoped for the same reason raw history is controller-scoped: endpoint identity changes must not split continuity and energy accounting for one physical controller.

New controller routes include:

```http
GET /v1/controllers/{controller_uid}/history/coverage
GET /v1/controllers/{controller_uid}/history/gaps
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

The analytics layer combines evidence only at read time:

```text
controller_uid
    |
    +-- historical device member A ---- raw poll history
    +-- historical device member B ---- raw poll history
    +-- retained daily rows ------------ controller evidence
    |
    `--> reconciliation analytics
           |-- days with persisted live samples
           |-- recovered / partial / missing gaps
           |-- controller-reported daily Wh
           |-- locally integrated output_power Wh
           `-- discrepancy + quality/provenance
```

A `recovered` day means no persisted local poll sample exists for that day but a complete retained daily record does. It does not mean intra-day samples have been reconstructed.

## Controller-first API

`GET /v1/controllers` includes both `controller_uid` and compatibility `controller_id` information.

Controller-scoped routes include:

- `GET /v1/controllers/{controller_uid}`
- `GET /v1/controllers/{controller_uid}/latest`
- `GET /v1/controllers/{controller_uid}/samples`
- `GET /v1/controllers/{controller_uid}/registers/{name}/history`
- `GET /v1/controllers/{controller_uid}/registers/history`
- `GET /v1/controllers/{controller_uid}/registers/stats`
- `GET /v1/controllers/{controller_uid}/history/summary`
- `GET /v1/controllers/{controller_uid}/history/controller-daily`
- `GET /v1/controllers/{controller_uid}/history/controller-daily/summary`
- `GET /v1/controllers/{controller_uid}/history/coverage`
- `GET /v1/controllers/{controller_uid}/history/gaps`
- `GET /v1/controllers/{controller_uid}/energy/daily`
- `GET /v1/controllers/{controller_uid}/energy/summary`
- `GET /v1/controllers/{controller_uid}/history/export`
- `GET /v1/controllers/{controller_uid}/polling/performance`
- `GET /v1/controllers/{controller_uid}/polling/history`

The legacy `/v1/devices/...` API remains available and keeps raw device-scoped behavior.

## Runtime ownership

The watcher receives immutable controller UIDs from `ControllerRegistry`. Endpoint selection, stale-client cleanup, retry/backoff, polling, and retained-history scheduling therefore remain owned by the physical controller even if identity evidence is promoted.

`benchmark-polling` likewise associates persisted benchmark evidence with controller identity rather than treating a transient endpoint string as the application's physical identity.

## Exports and provenance

Raw controller exports include both `controller_uid` and `source_device_id`. Aggregated exports include `controller_uid`; an aggregate may span several historical device rows by design.

Retained daily and reconciliation/energy responses publish explicit source/quality fields instead of silently collapsing controller evidence and local polling into one value.

## Relationship to system/site scope

`system_uid` is a separate grouping layer above one or more immutable controller UIDs. System metrics, component graphs, power flow, energy ledger, events, and SSE are derived from controller scopes rather than replacing them.

Use controller routes when the question is about one physical controller. Use system routes when the question is about a site or coordinated set of controllers.

## Safety boundary

Controller identity, retained history, reconciliation, and energy analytics are read-only/query features. They do not add Modbus write operations, controller configuration, resets, equalization triggers, coil writes, or arbitrary function-code passthrough.

See [`api.md`](api.md), [`controller-history-backfill.md`](controller-history-backfill.md), and [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).
