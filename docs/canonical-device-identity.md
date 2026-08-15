# Canonical controller identity and endpoint reconciliation

MorningstarModbusAPI now has two related inventory concepts:

- **connection/device rows** are the backward-compatible `devices.id` values used by existing telemetry APIs;
- **controller identity** represents the physical Morningstar controller independently of its current IP address, USB device path, or other connection locator.

The controller inventory introduced before this work grouped endpoint rows at query time. This layer persists that grouping and makes it part of the watcher reconnect path so future endpoint moves reuse one canonical telemetry ID instead of creating another history.

## Identity hierarchy

The same conservative hierarchy used by `/v1/controllers` remains authoritative:

1. Morningstar controller serial number when available;
2. USB adapter serial + Modbus unit when controller metadata is unavailable;
3. exact endpoint identity as the final fallback.

Controller-serial identity produces IDs such as:

```text
morningstar:tristar_mppt:ts123456
```

Serial-less hardware is not merged merely because model, profile, firmware, or Modbus unit happen to match.

## Additive persistent schema

Initialization creates these tables without rewriting telemetry:

- `controller_identities` — stable controller ID and its selected canonical `device_id`;
- `controller_device_members` — legacy/historical device IDs that belong to the controller;
- `controller_connections` — known endpoint identities and current presence;
- `controller_connection_locations` — concrete IP/serial path history, including locator changes hidden behind one stable USB-serial key;
- `controller_identity_evidence` — endpoint, USB serial, product, model, and controller-serial observations with confidence and counts.

Existing databases are bootstrapped from `devices` plus `device_intelligence`. For a pre-existing controller that already has several endpoint-backed IDs, the most recently seen existing row becomes the canonical `device_id`. Older IDs are retained as history members.

No `poll_samples`, `register_values`, controller daily history, polling-performance records, or error rows are rewritten.

## Future reconnect continuity

After bootstrap, discovery first resolves every observed endpoint to a controller identity. The watcher groups observations by controller before deciding what to poll.

```text
USB/TCP discovery observations
            |
            v
persisted controller identity
            |
      group by controller
            |
            +--- current endpoint still present? --- keep it
            |
            `--- otherwise choose TCP -> USB-serial serial -> other serial
            |
            v
      one polling session
            |
            v
canonical device_id
            |
            +--- telemetry
            +--- polling performance
            +--- controller daily-history backfill
```

If the selected endpoint changes, the stale client is closed and the existing `DeviceLifecycle` object is moved to the replacement endpoint. `endpoint_changes` increments while telemetry continues under the same canonical device ID.

This also handles a serial adapter whose USB serial is stable while Linux changes `/dev/ttyUSB0` to `/dev/ttyUSB1`: the stable endpoint key can remain the same, but the changed `Endpoint` object still forces stale-client replacement and the concrete locator is retained in location history.

## Multiple simultaneous connections

A physical controller may be discoverable over serial and Ethernet at the same time. Both connections are retained in `/v1/controllers`, but the watcher uses one selected connection for normal polling to avoid duplicate telemetry.

The current endpoint is preserved while it remains available. When selection is required, the preference is:

1. TCP;
2. serial with a stable USB serial;
3. other serial.

## Endpoint reuse protection

An endpoint is not automatically trusted merely because it was used before. If a reused IP/endpoint is now accompanied by a different known controller serial, it resolves to a different controller identity rather than inheriting the previous controller's telemetry.

The newly created canonical device ID uses a deterministic conflict-safe identifier when the raw endpoint stable key is already occupied.

## API behavior

`GET /v1/controllers` remains the physical-controller inventory API. Its records now include:

- `controller_id` — stable physical-controller identity;
- `canonical_device_id` / `current_device_id` — the device ID used for future telemetry;
- `history_device_ids` — canonical plus legacy endpoint-backed IDs that still contain historical rows;
- current/previous concrete connections;
- current connection count/status and controller metadata.

`GET /v1/devices` remains available for backward compatibility.

### Legacy history

The migration deliberately does not rewrite old foreign keys. A controller that already accumulated telemetry under several endpoint IDs can therefore have more than one value in `history_device_ids`. Future endpoint moves use `canonical_device_id`, so the split stops growing after migration.

Applications that need pre-migration history can use `history_device_ids` to retrieve the preserved legacy segments. A future controller-scoped history query layer can combine those IDs without mutating raw evidence.

## Lifecycle status

The offline persistence introduced with the controller inventory remains intact:

- previous stored online/error state is cleared when the watcher starts;
- a controller is marked offline when all discovered connections disappear;
- shutdown marks canonical controller rows offline;
- freshness guards prevent stale stored state from presenting as currently online.

Detailed lifecycle events/counters remain owned by the in-memory `DeviceLifecycle` state machine; this change does not create a competing persisted state machine.
