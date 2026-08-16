# Architecture

MorningstarModbusAPI is a read-only ingestion, identity-reconciliation, persistence, retained-history, analytics, and verification boundary between physical Morningstar devices and applications that consume telemetry.

The architecture keeps transport, vendor knowledge, runtime intelligence, physical-controller identity, polling/lifecycle management, persistence, retained-history recovery, reconciliation/energy analytics, system/site aggregation, capture/replay, API presentation, and vendor-source maintenance as separate layers.

## Runtime data flow

```text
USB / RS-232 / RS-485                         Ethernet
          |                                      |
          v                                      v
     Modbus RTU                             Modbus TCP
          |                                      |
          +--------------- discovery ------------+
                              |
                              v
                    catalog profile selection
                    | named registers
                    | reserved ranges
                              |
                              v
                 firmware-aware intelligence
                    | identity / metadata
                    | capabilities / confidence
                    | effective register map
                              |
                              v
                 physical-controller inventory
                    | serial/metadata evidence
                    | USB/endpoint fallbacks
                    | connection history
                              |
                              v
                 immutable controller registry
                    | controller_uid
                    | identity aliases
                    | historical device_ids
                              |
                              v
                  watcher + lifecycle/backoff
                    | one selected polling link
                    | reconnect / endpoint rebind
                    | auto/fixed poll cadence
                    | polling performance
                    | retained-history scheduling
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
      in-memory state                    SQLite / WAL
      auto tuning                        | raw poll/register history
                                        | errors/performance
                                        | controller identity/aliases
                                        | connection history/status
                                        | retained daily history
                                        | system/site state
                                             |
                  +--------------------------+--------------------------+
                  |                          |                          |
                  v                          v                          v
          device-scoped reads       controller-scoped reads       system/site reads
          raw compatibility         preferred physical view      normalized site view
                                             |
                                             +-- raw/bucketed history
                                             +-- retained daily evidence
                                             +-- day-level coverage/gaps
                                             +-- controller energy analytics
                                             |
                                             v
                                         FastAPI /v1
```

Raw `device_id` rows remain authoritative storage provenance. The physical controller (`controller_uid`) is the preferred application-facing entity. `system_uid` is a grouping layer above one or more controllers.

## Identity layers

Three controller/device identifiers intentionally coexist:

1. **`controller_uid`** — generated once for one physical controller and immutable;
2. **`controller_id`** — strongest current evidence-derived alias, which may be promoted;
3. **`device_id`** — raw telemetry-owning storage row retained for provenance and compatibility.

Identity evidence is conservative: controller serial when available, stable USB adapter serial + Modbus unit when controller metadata is unavailable, and exact endpoint identity as the fallback. Better evidence promotes the alias without changing the immutable UID.

Historical storage ownership is preserved through controller membership. Controller-scoped queries join all historical member device IDs instead of rewriting old foreign keys.

See [`canonical-device-identity.md`](canonical-device-identity.md) and [`controller-scoped-data.md`](controller-scoped-data.md).

## Catalog and intelligence

The catalog separates:

- `RegisterBlock` — contiguous read-only regions the runtime may read;
- `RegisterSpec` — semantic fields with decoder/unit/category metadata;
- `ReservedRegisterRange` — manufacturer-documented readable words intentionally left unnamed.

Raw block evidence may therefore include addresses that are intentionally reserved rather than semantically unmapped. Firmware gates are applied to blocks, named registers, and reserved ranges independently.

Runtime intelligence combines transport/device identification, catalog knowledge, firmware metadata, capability evidence, confidence, and plausibility checks into an effective device view.

See [`device-catalog.md`](device-catalog.md), [`device-intelligence.md`](device-intelligence.md), and [`catalog-maintenance.md`](catalog-maintenance.md).

## Lifecycle and endpoint selection

The watcher owns continuous discovery, controller reconciliation, one selected polling connection per physical controller, stale-client cleanup, retry/backoff, intelligence refresh, persistence, automatic cadence evaluation, and retained-history synchronization scheduling.

```text
discovered -> connecting -> online -> degraded -> offline -> rediscovering -> online
```

Important boundaries:

- Modbus communication failures drive degraded/offline lifecycle state;
- persistence failures are storage failures and do not retroactively make a successful Modbus read fail;
- endpoint replacement closes stale clients and retains physical-controller ownership;
- missing controllers are not polled through stale endpoints;
- reconnect success can schedule retained-history recovery without blocking the main poll loop.

## Polling versus persistence

Watcher polling can be fixed or automatically selected. Automatic tuning evaluates complete live polls and can advance through configured stages only when all present controllers satisfy the configured success/latency/deadline/request-failure/RTU-utilization criteria.

The persistence cadence is independent. Normal watcher history persistence cannot be configured below one second per physical controller, so sub-second live polls may affect lifecycle/intelligence/auto-tuning without becoming separate `poll_samples` rows.

SQLite uses WAL mode and non-blocking `aiosqlite` access.

See [`polling-performance.md`](polling-performance.md) and [`telemetry-history.md`](telemetry-history.md).

## Persistence groups

Major persisted groups include:

```text
devices
  |-- device_intelligence
  |-- poll_samples
  |     `-- register_values
  `-- poll_errors

controller identity
  |-- controller_identities
  |-- controller_device_members
  |-- controller_connections / location / evidence
  |-- physical_controllers
  `-- controller_identity_aliases

poll_performance_samples

controller retained history
  |-- controller_daily_history
  `-- controller_history_syncs

system/site data
  |-- membership / normalized semantics
  |-- topology / component graph
  |-- events
  `-- system energy/power views derived from authoritative evidence
```

Schema evolution is additive where practical. Historical raw observations are not rewritten simply to simplify a newer query layer.

## Retained-history architecture

Retained-history providers are separate from ordinary Modbus polling. A provider may retrieve daily data retained inside a controller after startup/reconnect, but the resulting rows remain a distinct source class.

```text
successful live poll
        |
        +--> normal persistence if cadence is due
        |
        `--> background retained-history provider
                  |
                  v
            controller_daily_history
```

The verified TriStar MPPT Ethernet backend uses LiveView history. The project does not guess undocumented historical Modbus addresses for unsupported transports/families.

See [`controller-history-backfill.md`](controller-history-backfill.md).

## v0.6 reconciliation analytics

v0.6 adds a read-time analytics layer above raw polling and retained daily evidence. It does not create a third synthetic history source.

```text
raw persisted poll history ---------+
                                     +--> ControllerHistoryAnalytics
retained controller daily history --+       |-- day-level live/evidence coverage
                                             |-- recovered/partial/missing gaps
                                             |-- bounded output_power integration
                                             |-- controller-reported daily Wh
                                             `-- discrepancy + quality/provenance
```

Coverage is deliberately day-level because the service cannot prove how many high-frequency samples should have existed during every outage. A recovered gap means complete retained daily evidence exists for a day with no persisted local samples; it does not mean minute/second observations were reconstructed.

Local energy integration uses trapezoidal integration only across adjacent `output_power` samples whose separation is no greater than the configured `max_gap_seconds`. Larger gaps are skipped. Controller-reported daily Wh and locally integrated Wh remain independent measurements.

See [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).

## System/site architecture

The system layer sits above immutable controller scopes. It normalizes source-specific semantics into site-level views while preserving contributor quality and provenance.

Depending on available controller evidence, system APIs can expose:

- normalized current metrics and history;
- `complete` / `partial` / `empty` quality;
- component graph and typed relationships;
- topology and bridge candidates;
- power flow;
- energy ledger/balance;
- unified event timeline;
- SSE telemetry/events.

Authoritative source-specific metering such as verified GenStar system energy/balance fields is preferred over inferred substitutes when available. Derived system values remain explicitly derived rather than promoted to vendor facts.

See [`system-api.md`](system-api.md) and [`component-graph.md`](component-graph.md).

## Capture, replay, and verification

Capture/replay records exact read-only Modbus exchanges separately from decoded register results. Strict replay uses the same production parsers as live devices so fixtures function as protocol regressions rather than loose canned responses.

Verification evidence is tiered and remains distinct from runtime identity confidence. See [`hardware-verification.md`](hardware-verification.md).

## Vendor-source maintenance

Official-source maintenance is a sidecar to runtime operation. Source artifacts are fetched/validated, conservatively scanned, and compared against catalog declarations without allowing automated extraction to silently redefine runtime semantics.

See [`catalog-maintenance.md`](catalog-maintenance.md).

## API presentation layers

The API exposes three intentional scopes:

1. `/v1/devices/...` — exact raw storage segment compatibility;
2. `/v1/controllers/...` — preferred physical-controller view, including retained history and v0.6 analytics;
3. `/v1/systems/...` — normalized multi-controller/site view.

The route layer validates inputs and presents the underlying read models; it does not perform controller mutation.

## Read-only safety boundary

No architecture layer exposes controller register writes, coil writes, reset/equalize triggers, arbitrary function-code passthrough, or configuration mutation. Retained-history synchronization is read-only, reconciliation is read-time analysis, and energy accounting does not modify controller state or raw historical observations.
