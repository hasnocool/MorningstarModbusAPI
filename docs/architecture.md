# Architecture

MorningstarModbusAPI is a read-only ingestion, identity-reconciliation, persistence, and verification boundary between physical Morningstar devices and applications that consume telemetry.

The design deliberately separates transport, product knowledge, runtime intelligence, physical-controller identity, capture/replay, lifecycle management, polling policy, persistence, query/aggregation, API presentation, and vendor-source maintenance so each can evolve without weakening the read-only boundary.

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
                     | named registers
                     | reserved ranges
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
                     | numeric or automatic cadence
                     | polling performance
                               |
                     raw + decoded live values
                               |
                +--------------+--------------+
                |                             |
                v                             v
       in-memory lifecycle /           persistence limiter
       intelligence / auto tune        normal poll-driven >= 1 s/controller
                                              |
                                              v
                                         SQLite / WAL
                     | raw persisted poll/register history
                     | device intelligence
                     | controller identity/aliases
                     | connection history/status
                     | persisted polling performance
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

## Catalog semantics: readable blocks, named fields, and reserved words

The catalog separates three concepts that must not be conflated:

- `RegisterBlock` — a contiguous read-only region the runtime is allowed to read;
- `RegisterSpec` — a semantic single- or multi-word field with name/decoder/unit/category metadata;
- `ReservedRegisterRange` — manufacturer-documented word(s) inside a readable block that are intentionally unnamed.

A full block poll preserves every successfully read word as raw evidence. A raw alias such as `holding_0x003F` therefore may exist even when the address is **not** an unmapped semantic field. If the catalog declares that address reserved, applications should classify it as reserved rather than invent a name.

Firmware gates apply independently to blocks, named registers, and reserved ranges. `effective_register_map()` returns the firmware-applicable view with separate `blocks`, `registers`, and `reserved_ranges` arrays.

For the TriStar MPPT 150V v11 profile, the current source-backed reserved spans are:

- `0x0005-0x0017`;
- `0x002D`;
- `0x003F`;
- `0x004A`;
- `0xE0C4-0xE0CB`.

The adjacent TS-MPPT `hardware_version` field at `0xE0CD` uses the catalog `byte_pair_version` decoder, interpreting the upper byte as major and lower byte as minor (for example `0x0101` -> `1.1`).

See [`device-catalog.md`](device-catalog.md) and [`device-intelligence.md`](device-intelligence.md).

## Runtime lifecycle and endpoint selection

The watcher owns continuous discovery, one selected polling connection per physical controller, retry/backoff, stale-client cleanup, intelligence refresh, persistence, automatic cadence evaluation, and backfill scheduling.

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
- **actual Modbus poll failures** transition through `degraded` to `offline` according to `failure_threshold`;
- failed clients are closed so the next eligible attempt creates a fresh connection;
- retry delay grows exponentially between the configured initial and maximum bounds;
- successful recovery resets failure/backoff state and can increment reconnect count;
- a database persistence failure after a successful Modbus read is logged separately and does **not** convert that read into a lifecycle failure.

Runtime ownership follows immutable controller UID even though transport clients, trackers, and lifecycle objects are associated with the selected endpoint key internally.

The detailed lifecycle object is not persisted as a separate event/state machine and is not exposed directly through FastAPI. SQLite persists simpler device/controller presence plus identity, connection, telemetry, history, and performance records.

## Poll scheduling and automatic interval selection

`watch.poll_interval_seconds` can be a positive number or `"auto"`.

With a numeric interval, the watcher uses that value as its target start-to-start cadence. With automatic mode, `AutoPollIntervalController` uses the same measured criteria as the explicit benchmark workflow:

```text
auto fallback baseline
        |
        | collect complete profile polls for every present controller
        v
all controllers pass?
        |
        +-- no -> remain at fallback
        |
        `-- yes
             |
             v
configured benchmark stages, slowest -> fastest
             |
             +-- all pass -> advance
             `-- any fail -> lock last proven-safe interval
```

With the default configuration this is effectively `5.0 -> 1.0 -> 0.5 -> 0.25` seconds, subject to the configured success-rate, p95-latency, deadline-miss, request-failure, and RTU-utilization thresholds.

Automatic calibration is global because the watcher interval is global. Every currently present physical controller must complete/pass a stage before the watcher advances. A change in the selected controller/endpoint/profile/transport signature resets automatic calibration to the conservative fallback so evidence from a previous topology is not reused blindly.

The tuner observes every live in-memory poll result even when persistence is slower.

See [`polling-performance.md`](polling-performance.md).

## Persistence model and cadence

SQLite uses WAL mode and non-blocking `aiosqlite` access. Persistence is additive and persisted raw observations remain authoritative for historical queries.

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

Live polling and poll-driven persistence have separate cadences. `database.telemetry_write_interval_seconds` cannot be below `1.0` second. `PollPersistenceLimiter` applies that interval per physical controller to normal watcher persistence.

For example:

```text
0.0 s  Modbus poll -> persist snapshot/performance/intelligence success
0.2 s  Modbus poll -> in-memory only
0.4 s  Modbus poll -> in-memory only
0.6 s  Modbus poll -> in-memory only
0.8 s  Modbus poll -> in-memory only
1.0 s  Modbus poll -> persist again
```

Intermediate polls remain real controller reads. They still affect lifecycle, refreshed in-memory intelligence, poll traffic measurements, and automatic interval evaluation; they simply do not create extra `poll_samples`/`register_values` rows.

The limiter is a write-amplification/history-cadence policy, not a claim that ordinary SQLite WAL transactions would inherently corrupt merely because commits were attempted faster than once per second.

A normal successful persistence cycle writes the telemetry sample first, then separately attempts controller-connection success, watcher performance, and refreshed intelligence. Failure to persist one of these pieces is logged as storage failure and does not retroactively change the successful Modbus lifecycle result.

The watcher limiter is **not** a literal global database commit-rate cap. Event-driven discovery/reconciliation/presence state, startup/shutdown offline updates, retained-history backfill, and explicit `benchmark-polling` evidence persistence use their own paths. `benchmark-polling --no-persist` disables benchmark sample storage.

The system does **not** destructively rewrite old `poll_samples`, `register_values`, errors, retained daily history, or polling-performance rows merely to improve identity. Instead, the controller scope maps the physical controller to every telemetry-owning member ID.

See [`telemetry-history.md`](telemetry-history.md) and [`polling-performance.md`](polling-performance.md).

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

Watcher performance samples are persisted on the normal watcher persistence cadence; therefore API `poll_rate_hz` for `mode=watch` describes persisted performance rows, not necessarily every faster live in-memory poll. The automatic tuner receives the live samples directly and is not limited to persisted rows.

The `benchmark-polling` command uses the same profile polling path and, when persistence is enabled, registers the observation through the physical-controller registry so benchmark data follows the same controller identity as the watcher. Benchmark persistence is intentionally independent of the watcher cadence limiter.

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
 named / reserved / other address spaces
               |
               v
advisory diff / provenance review
               |
               v
manual catalog + test change
```

The maintenance scanner does not automatically edit family modules and does not run inside the polling service. A reviewed vendor row that is explicitly reserved can justify a `ReservedRegisterRange`; it should not be converted into a speculative semantic `RegisterSpec` merely to eliminate a raw alias.

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

`morningstar_modbus.catalog` is declarative product truth. Vendor-derived family modules define read blocks, semantic register specs, documented reserved ranges, decoders/scaling, units, states, alarm/fault bitfields, aliases, capabilities, metadata, firmware gates, and source IDs.

Independent fixture/hardware verification evidence lives outside vendor-derived family definitions.

### Intelligence

`morningstar_modbus.intelligence` resolves connected hardware using Device Identification, catalog aliases, conservative fingerprints, targeted metadata, firmware compatibility, observed capabilities, confidence scoring, and plausibility checks. It also produces the effective firmware-aware read/register/reserved map exposed by the device register-map API.

### Controller identity

- `controller_inventory.py` owns evidence-derived controller identity, endpoint reconciliation, membership, connection/location history, and endpoint-reuse protection.
- `controller_scope.py` assigns immutable controller UIDs and retains identity aliases across promotion.
- `controller_data.py` resolves controller scope into unified reads over the authoritative stores.
- `controller_api.py` exposes controller-first HTTP routes without duplicating storage/product logic.

### Verification

`verification.py` runs the normal resolver/profile against a live or replay client and returns session-level identity, firmware/hardware information, intelligence status/confidence, block availability, named-register coverage, warnings in JSON, and a final result.

This report is distinct from the catalog verification registry returned by `/v1/catalog` and `/v1/catalog/{profile_name}`.

### Watcher and lifecycle

`watcher.py` owns continuous discovery, physical-controller grouping, connection selection, polling, reconnect, intelligence refresh, automatic interval evaluation, rate-limited normal poll persistence, performance persistence, backfill scheduling, and in-memory lifecycle transitions.

### Storage and API

- `storage.py` owns raw device/poll/register/error persistence and device-scoped queries.
- `polling_storage.py` owns persisted polling-performance samples.
- `controller_history_storage.py` owns retained daily-history records and sync provenance.
- `api.py` builds the FastAPI application and preserves legacy device/catalog routes.
- `controller_api.py` adds controller-first routes.

FastAPI exposes persisted state; it does not fabricate the watcher-only detailed lifecycle state or the instantaneous in-memory auto-poll calibration state.

## Read-only safety boundary

The runtime implements only the Modbus operations needed for discovery and telemetry: holding-register reads (`0x03`), input-register reads (`0x04`), and Read Device Identification (`0x2B / 0x0E`). Capture, automatic polling evaluation, and polling instrumentation observe those operations; replay reproduces them. None creates a write path.

Official Morningstar specifications also describe writable registers/coils, but those definitions do not imply runtime write support.

## Failure model

- Missing optional metadata does not invalidate an otherwise successful telemetry poll.
- Unknown devices fall back to conservative generic read-only behavior rather than forced product classification.
- Implausible decoded telemetry can mark a selected intelligence profile `invalid` while preserving raw data.
- Firmware newer than a profile's verification ceiling can be surfaced as `newer-firmware-unverified` while maintaining raw read access.
- Capture/replay mismatches fail loudly instead of returning approximate responses.
- Identity ambiguity is not silently merged when evidence is insufficient.
- Endpoint reuse accompanied by a conflicting known controller serial does not inherit the previous controller's history.
- Device/controller absence and repeated **Modbus** poll failures cause lifecycle transitions/backoff rather than endless polling against a dead endpoint.
- Database persistence failures are logged separately; they do not make a successful Modbus poll a lifecycle failure.
- Because watcher persistence is rate-limited, not every live Modbus failure necessarily becomes a persisted `poll_errors`/performance row.
- Oversized normal JSON history queries fail with bounded API errors instead of consuming unbounded memory; streaming export remains available.

## Extending the service

A new product family should be added by extending the catalog and tests, not by embedding product-specific conditionals in transport, watcher, or API code. Vendor-derived register/reserved changes should point to official source IDs and follow `catalog-proposals/` provenance rules. Fixture/hardware verification metadata should be updated separately only when the evidence justifies it.
