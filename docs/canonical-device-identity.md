# Canonical controller identity and endpoint reconciliation

MorningstarModbusAPI keeps raw connection/device rows for storage provenance while modelling the physical Morningstar controller separately from its current USB/TCP endpoint.

The identity system now has three distinct identifiers:

- **`controller_uid`** — generated once and immutable; this is the application-facing physical-controller identifier;
- **`controller_id`** — the current strongest evidence-derived identity alias and retained compatibility field;
- **`device_id`** — the raw telemetry-owning row used by existing device-scoped APIs and historical foreign keys.

See [`controller-scoped-data.md`](controller-scoped-data.md) for controller-first query behavior.

## Identity hierarchy

Evidence-derived controller aliases continue to use the conservative hierarchy:

1. Morningstar controller serial number when available;
2. USB adapter serial + Modbus unit when controller metadata is unavailable;
3. exact endpoint identity as the final fallback.

For example:

```text
controller_uid: ctrl_8b17...

aliases:
  usb:adapter-1:unit:1
  morningstar:tristar_mppt:ts123456   <- current strongest alias
```

`controller_id` can therefore change when identity evidence improves. `controller_uid` does not.

Serial-less hardware is not merged merely because model, profile, firmware, or Modbus unit happen to match.

## Persistent schema

The persisted controller inventory uses:

- `controller_identities` — the current evidence-derived controller identity and selected canonical `device_id`;
- `controller_device_members` — legacy/historical device IDs that belong to the controller;
- `controller_connections` — known endpoint identities and current presence;
- `controller_connection_locations` — concrete IP/serial path history;
- `controller_identity_evidence` — endpoint, USB serial, product, model, and controller-serial observations;
- `physical_controllers` — immutable `controller_uid`, canonical telemetry device ID, and current alias;
- `controller_identity_aliases` — historical/current evidence-derived aliases mapped to the immutable UID.

Existing databases are bootstrapped without rewriting telemetry. For a controller that already has several endpoint-backed IDs, the most recently seen existing row remains the canonical `device_id`; older IDs remain history members.

No `poll_samples`, `register_values`, controller daily history, polling-performance records, or error rows are rewritten.

## Identity promotion

A controller may initially be seen only through a USB adapter or endpoint and later expose its Morningstar serial number.

Previously this promotion changed the controller's application-facing identity. The immutable UID layer now preserves the old alias and associates the new stronger alias with the same `controller_uid`.

```text
first observation
  ctrl_8b17... -> usb:adapter-1:unit:1

later observation
  ctrl_8b17... -> morningstar:tristar_mppt:ts123456
                   ^ current alias
```

Both aliases remain resolvable to the same controller UID.

## Reconnect continuity

Discovery resolves observed endpoints to a physical controller before polling. The watcher groups observations by immutable controller UID and keeps one selected connection for normal polling.

```text
USB/TCP observations
        |
        v
controller registry
        |
        +-- immutable controller_uid
        +-- current controller_id alias
        +-- canonical device_id
        |
        v
one watcher lifecycle / polling session
        |
        +-- telemetry
        +-- polling performance
        `-- retained-history backfill
```

If the selected endpoint changes, the stale client is closed and the existing `DeviceLifecycle` object moves to the replacement endpoint. IP changes, `/dev/ttyUSB*` re-enumeration, and identity promotion therefore do not create a new runtime controller lifecycle.

## Multiple simultaneous connections

A physical controller may be visible over serial and Ethernet at the same time. All observed connections remain in the inventory, while the watcher selects one normal polling endpoint to avoid duplicate telemetry.

Selection remains:

1. keep the current endpoint while it is still available;
2. otherwise prefer TCP;
3. then serial with stable USB serial identity;
4. then other serial.

## Endpoint reuse protection

A previously known endpoint is not sufficient proof of controller identity. If an IP/endpoint is reused and a different known Morningstar controller serial is observed, the new hardware is separated rather than inheriting the previous controller's history.

## API behavior

`GET /v1/controllers` is the physical-controller inventory API. Records include:

- `controller_uid` — immutable application-facing identity;
- `controller_id` — current evidence-derived alias;
- `canonical_device_id` / `current_device_id` — device ID used for future telemetry;
- `history_device_ids` — canonical plus preserved legacy IDs containing historical rows;
- current/previous connections and controller metadata.

Controller-first history/query endpoints are rooted at `/v1/controllers/{controller_uid}/...` and automatically span `history_device_ids` while preserving `source_device_id` on raw evidence.

`GET /v1/devices` and the existing `/v1/devices/...` routes remain available for backward compatibility and raw endpoint/device inspection.

## Lifecycle status

Offline persistence remains unchanged:

- previous stored online/error state is cleared when the watcher starts;
- a controller is marked offline when its selected discovered connection disappears;
- shutdown marks canonical controller rows offline;
- freshness guards prevent stale stored state from presenting as currently online.

Detailed lifecycle transitions/counters remain owned by the in-memory `DeviceLifecycle` state machine. The immutable UID layer changes identity ownership, not the lifecycle state model.

## Read-only boundary

This identity work does not add Modbus writes, resets, configuration, equalization triggers, coil writes, or generic function-code passthrough. MorningstarModbusAPI remains a read-only telemetry/evidence boundary.
