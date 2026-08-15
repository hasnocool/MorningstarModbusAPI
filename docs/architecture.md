# Architecture

MorningstarModbusAPI is a read-only ingestion, identity-reconciliation, persistence, and verification boundary between physical Morningstar devices and applications that consume telemetry.

The design deliberately separates transport, product knowledge, runtime intelligence, physical-controller identity, capture/replay, lifecycle management, persistence, query/aggregation, API presentation, and vendor-source maintenance so each can evolve without weakening the read-only boundary.

## Runtime data flow

```text
USB / RS-232 / RS-485                           Ethernet
          |                                        |
          v                                        v
     Modbus RTU                               Modbus TCP
          |                                        |
          +---------------- discovery -------------+
                               |
                               v
                     catalog profile selection
                               |
                               v
                   firmware-aware intelligence
                     | identity / metadata
                     | confidence / capabilities
                     | effective register map
                               |
                               v
                    controller identity inventory
                     | controller serial evidence
                     | USB/endpoint fallbacks
                     | connection/location history
                               |
                               v
                    immutable controller registry
                     | controller_uid
                     | identity aliases
                     | canonical device_id
                     | historical device_ids
                               |
                               v
                     watcher + lifecycle/backoff
                     | one selected polling link
                     | reconnect / endpoint rebind
                     | polling performance
                               |
                     raw + decoded values
                               |
                               v
                        SQLite / WAL
                     | raw poll/register history
                     | device intelligence
                     | controller identity/aliases
                     | connection history/status
                     | polling performance
                     | retained daily history
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
          device-scoped queries       controller-scoped queries
          (compatibility/raw)         (preferred application view)
                 |                           |
                 +-------------+-------------+
                               |
                               v
                          FastAPI /v1
```

The physical controller is the preferred application-facing entity. Raw `device_id` rows remain important storage provenance and backward-compatible API identifiers.

## Identity layers

Three identifiers intentionally coexist:

1. **`controller_uid`** — generated once for one physical controller and treated as immutable;
2. **`controller_id`** — strongest current evidence-derived identity alias, which can be promoted as better evidence becomes available;
3. **`device_id`** — raw telemetry-owning storage row retained for backward compatibility and provenance.

Evidence-derived identity follows a conservative hierarchy:

1. Morningstar controller serial when available;
2. stable USB adapter serial + Modbus unit when controller metadata is unavailable;
3. exact endpoint identity as the final fallback.

A controller can therefore begin as an endpoint/USB identity and later gain a controller serial without changing `controller_uid`. Historical aliases remain resolvable.

The registry also preserves pre-canonical telemetry ownership through `controller_device_members`. Controller-scoped reads join all of those member IDs instead of rewriting old foreign keys.

See [`canonical-device-identity.md`](canonical-device-identity.md) and [`controller-scoped-data.md`](controller-scoped-data.md).

## Runtime lifecycle and endpoint selection

The watcher owns continuous discovery, one selected polling connection per physical controller, retry/backoff, stale-client cleanup, intelligence refresh, persistence, and backfill scheduling.

The lifecycle state machine is:

```text
discovered
    ↓
connecting
    ↓
online
    ↓
degraded
    ↓
offline
    ↓
rediscovering
    ↓
online
```

`DeviceLifecycle` tracks state, consecutive failures, reconnect count, endpoint changes, `last_discovered`, `last_success`, `offline_since`, retry delay, and an internal monotonic retry deadline.

Important behavior:

- discovery observations are reconciled to immutable controller UIDs before polling selection;
- a physical controller can retain several known serial/TCP connections, but only one is selected for normal polling;
- the current endpoint is preserved while present; when selection is needed the watcher prefers TCP, then serial with a stable USB serial, then other serial;
- endpoint changes close stale clients before replacement and increment the endpoint-change counter;
- the existing lifecycle object is moved to the replacement endpoint so reconnect state is not discarded;
- missing controllers enter rediscovery behavior and are excluded from polling through stale endpoints;
- poll failures transition through `degraded` to `offline` according to `failure_threshold`;
- failed clients are closed so the next eligible attempt creates a fresh connection;
- retry delay grows exponentially between the configured initial and maximum bounds;
- successful recovery resets failure/backoff state and can increment reconnect count.

Runtime ownership follows immutable controller UID even though transport clients, trackers, and lifecycle objects are associated with the selected endpoint key internally.

The detailed lifecycle object is not persisted as a separate event/state machine and is not exposed directly through FastAPI. SQLite persists simpler device/controller presence plus identity, connection, telemetry, history, and performance records.

## Persistence model

SQLite uses WAL mode and non-blocking `aiosqlite` access. Persistence is additive and raw observations remain authoritative.

Major data groups are:

```text
devices
  ├── device_intelligence
  ├── poll_samples
  │     └── register_values
  └── poll_errors

controller_identities
  ├── controller_device_members
  ├── controller_connections
  ├── controller_connection_locations
  └── controller_identity_evidence

physical_controllers
  └── controller_identity_aliases

poll_performance_samples

controller_daily_history
controller_history_syncs
```

The system does **not** destructively rewrite old `poll_samples`, `register_values`, errors, retained daily history, or polling-performance rows merely to improve identity. Instead, the controller scope maps the physical controller to every telemetry-owning member ID.

## Controller-scoped query layer

`ControllerDataRepository` is the preferred read model for physical-controller applications.

```text
controller_uid
     |
     v
ControllerScope
     |
     +-- canonical_device_id
     +-- history_device_ids[]
     |
     v
query raw authoritative tables
     |
     +-- samples/latest
     +-- register history
     +-- aggregation/statistics
     +-- summaries/export
     +-- retained daily history
     `-- polling performance
```

Raw controller-scoped results expose `source_device_id`, preserving which raw row originally owned the observation. Aggregation combines member histories **before** bucket/statistics calculation, so counts, numeric averages, and text-state transitions represent the physical-controller timeline rather than a merge of separately aggregated endpoint results.

The legacy device-scoped query layer remains available and intentionally continues to operate on exactly one `device_id`.

See [`api.md`](api.md) and [`telemetry-history.md`](telemetry-history.md).

## Controller-retained daily-history backfill

Supported TriStar MPPT Ethernet controllers expose retained daily data through the built-in LiveView datalog page. That recovery path is intentionally separate from normal Modbus polling:

```text
successful live Modbus poll
          |
          v
backfill scheduling policy
          |
          v
controller LiveView HTTP datalog
          |
          v
parse + provenance
          |
          v
controller_daily_history
```

Backfill is scheduled after live polling succeeds on startup/reconnect, so a slow/unavailable HTTP page does not delay normal telemetry acquisition. Retained daily records can describe periods with no raw samples, but they are never expanded into fabricated per-poll Modbus rows.

See [`controller-history-backfill.md`](controller-history-backfill.md).

## Polling-performance path

Transport clients accept a read-only exchange observer. During normal watcher polling or explicit benchmarking, `PollTrafficTracker` derives request counts, success/failure counts, byte counts, poll latency, deadline behavior, and estimated RTU wire utilization.

Performance samples are stored separately from controller telemetry. The `benchmark-polling` command uses the same profile polling path and, when persistence is enabled, registers the observation through the physical-controller registry so benchmark data follows the same controller identity as the watcher.

See [`polling-performance.md`](polling-performance.md).

## Capture and replay path

Transport clients can also accept an observer that records completed read-only Modbus exchanges. The observer does not alter the request path; it records evidence produced by the same transport implementation used in normal operation.

```text
live transport request
        |
        +----> device
        |       |
        |       v
        |    response
        |       |
        v       v
 transport parser/validation
        |
        +----> normal caller
        |
        +----> capture observer
                  |
                  v
             bundle writer
                  |
                  v
 manifest / identity / transactions / registers / expected
                  |
                  v
             ReplayModbusClient
                  |
                  v
     production protocol parsers
                  |
                  v
 catalog → intelligence → validation → persistence/API tests
```

Replay is strict: function code, register address, count, and transaction ordering must match the captured session.

### Capture bundle boundary

A capture bundle contains:

- `manifest.json`: schema/provenance, endpoint metadata, profile/model/firmware context, transaction count, and privacy flags;
- `identification.json`: structured Modbus Device Identification;
- `transactions.jsonl`: ordered transport records containing request/response frames and PDUs, function/address/count, latency, and errors;
- `registers.json`: raw register words and decoded named values produced by the profile poll;
- `expected.json`: replay-oriented expectations for profile/family/model/firmware/status/confidence/named registers.

Decoded register values live in `registers.json`, not in each transaction record. Structured identifiers are redacted by default, but raw protocol frames can still contain identifiers and must be reviewed before publication.

## Maintenance sidecar

The official-source maintenance pipeline remains outside the runtime/capture path:

```text
docs/vendor/morningstar/sources.json
               |
               v
approved Morningstar HTTPS documents
               |
               v
maintenance download + PDF extraction
               |
               v
conservative register observations
               |
               v
advisory diff / provenance review
               |
               v
manual catalog + test change
```

The maintenance scanner does not automatically edit family modules and does not run inside the polling service.

## Layer responsibilities

### Transport and discovery

- `protocol.py`, `transport.py` implement read-only Modbus framing and RTU/TCP clients.
- TCP uses native asyncio streams.
- serial protocols use PySerial behind the existing executor boundary.
- standard Modbus Device Identification is attempted when available.
- conservative family fingerprints are used only where distinctive enough to avoid guessing.
- TCP discovery is constrained to explicit hosts or explicitly configured bounded CIDRs.
- optional exchange observers support capture and polling instrumentation without a second protocol implementation.

### Catalog

`morningstar_modbus.catalog` is declarative product truth. Vendor-derived family modules define register blocks, decoders/scaling, units, states, alarm/fault bitfields, aliases, capabilities, metadata, firmware gates, and source IDs.

Independent fixture/hardware verification evidence lives outside vendor-derived family definitions.

### Intelligence

`morningstar_modbus.intelligence` resolves connected hardware using Device Identification, catalog aliases, conservative fingerprints, targeted metadata, firmware compatibility, observed capabilities, confidence scoring, and plausibility checks.

### Controller identity

- `controller_inventory.py` owns evidence-derived controller identity, endpoint reconciliation, membership, connection/location history, and endpoint-reuse protection.
- `controller_scope.py` assigns immutable controller UIDs and retains identity aliases across promotion.
- `controller_data.py` resolves controller scope into unified reads over the authoritative stores.
- `controller_api.py` exposes controller-first HTTP routes without duplicating storage/product logic.

### Verification

`verification.py` runs the normal resolver/profile against a live or replay client and returns session-level identity, firmware/hardware information, intelligence status/confidence, block availability, named-register coverage, warnings in JSON, and a final result.

This report is distinct from the catalog verification registry returned by `/v1/catalog` and `/v1/catalog/{profile_name}`.

### Watcher and lifecycle

`watcher.py` owns continuous discovery, physical-controller grouping, connection selection, polling, reconnect, intelligence refresh, performance persistence, backfill scheduling, and in-memory lifecycle transitions.

### Storage and API

- `storage.py` owns raw device/poll/register/error persistence and device-scoped queries.
- `polling_storage.py` owns polling-performance samples.
- `controller_history_storage.py` owns retained daily-history records and sync provenance.
- `api.py` builds the FastAPI application and preserves legacy device/catalog routes.
- `controller_api.py` adds controller-first routes.

FastAPI exposes persisted state; it does not fabricate the watcher-only detailed lifecycle state.

## Read-only safety boundary

The runtime implements only the Modbus operations needed for discovery and telemetry: holding-register reads (`0x03`), input-register reads (`0x04`), and Read Device Identification (`0x2B / 0x0E`). Capture and polling instrumentation observe those operations; replay reproduces them. None creates a write path.

Official Morningstar specifications also describe writable registers/coils, but those definitions do not imply runtime write support.

## Failure model

- Missing optional metadata does not invalidate an otherwise successful telemetry poll.
- Unknown devices fall back to conservative generic read-only behavior rather than forced product classification.
- Implausible decoded telemetry can mark a selected intelligence profile `invalid` while preserving raw data.
- Firmware newer than a profile's verification ceiling can be surfaced as `newer-firmware-unverified` while maintaining raw read access.
- Capture/replay mismatches fail loudly instead of returning approximate responses.
- Identity ambiguity is not silently merged when evidence is insufficient.
- Endpoint reuse accompanied by a conflicting known controller serial does not inherit the previous controller's history.
- Device/controller absence and repeated poll failures cause lifecycle transitions/backoff rather than endless polling against a dead endpoint.
- Oversized normal JSON history queries fail with bounded API errors instead of consuming unbounded memory; streaming export remains available.

## Extending the service

A new product family should be added by extending the catalog and tests, not by embedding product-specific conditionals in transport, watcher, or API code. Vendor-derived register changes should point to official source IDs and follow `catalog-proposals/` provenance rules. Fixture/hardware verification metadata should be updated separately only when the evidence justifies it.
