# MorningstarModbusAPI documentation index

These documents describe the current merged `main` line and the runtime behavior published in `v0.6.0`. Historical release notes remain snapshots of the releases they describe.

## Recommended reading

If you are integrating the service rather than modifying it internally:

1. [`../README.md`](../README.md) — installation, CLI, capability overview, preferred controller-first model, register semantics, and polling/persistence behavior.
2. [`api.md`](api.md) — HTTP routes, identifiers, effective register maps, history query semantics, limits, exports, and examples.
3. [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md) — v0.6 controller history coverage, gap reconciliation, energy accounting, discrepancy metrics, and provenance semantics.
4. [`system-api.md`](system-api.md) — normalized multi-controller system/site metrics, quality, topology, power flow, energy ledger, event timeline, SSE, retained-history providers, and optional SNMP trap ingestion.
5. [`system-metering.md`](system-metering.md) — authoritative GenStar whole-system currents/counters, conflict resolution, power-flow inputs, and energy-ledger authority.
6. [`controller-scoped-data.md`](controller-scoped-data.md) — why `controller_uid` is the stable application identifier and how legacy history is unified.
7. [`telemetry-history.md`](telemetry-history.md) — persisted history, polling-vs-storage cadence, aggregation/statistics semantics, retained-history evidence, and retention guarantees.
8. [`controller-history-backfill.md`](controller-history-backfill.md) — controller-retained daily history, reconnect recovery, and provenance limits.
9. [`polling-performance.md`](polling-performance.md) — automatic watcher cadence, persisted polling metrics, benchmarking, and RTU-utilization limits.

If you are developing the project itself, start with [`architecture.md`](architecture.md), [`package-layout.md`](package-layout.md), and the root [`AGENTS.md`](../AGENTS.md).

## Documentation map

| Document | Scope |
| --- | --- |
| [`api.md`](api.md) | Controller-first, system, and legacy HTTP APIs; identifiers; history/energy surfaces; effective register maps/reserved ranges; query limits; exports; errors; examples |
| [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md) | Day-level evidence coverage, recovered/partial/missing gaps, controller-vs-local energy accounting, quality, discrepancy metrics, and provenance |
| [`system-api.md`](system-api.md) | Multi-controller system/site aggregation, normalized semantics, quality, component graph, power flow, energy ledger, topology, events, SSE, retained-history provider architecture, and SNMP trap ingestion |
| [`system-metering.md`](system-metering.md) | Source-backed GenStar system charge/battery/load currents, system/internal/shunt counters, conflict-aware whole-system authority, and energy-ledger rules |
| [`component-graph.md`](component-graph.md) | System component graph, typed relationships, power-flow views, and energy-ledger semantics |
| [`architecture.md`](architecture.md) | Runtime layers, controller identity/UID flow, lifecycle, auto polling, persistence cadence, retained history, reconciliation analytics, system aggregation, capture/replay, and read-only safety |
| [`package-layout.md`](package-layout.md) | Canonical domain package layout and dependency direction |
| [`agent-system.md`](agent-system.md) | Shared coding-agent control tower, portable skills, harness adapters, specialist agents, and maintenance rules |
| [`hardware-verification.md`](hardware-verification.md) | Physical capture, replay, verification reports, fixture publication, evidence levels, lifecycle/persistence distinctions, and sanitization |
| [`telemetry-history.md`](telemetry-history.md) | Persisted telemetry retention, device/controller scopes, polling-vs-storage cadence, aggregation, statistics, streaming export, retained-history evidence, and v0.6 reconciliation/energy boundaries |
| [`controller-history-backfill.md`](controller-history-backfill.md) | Provenance-aware recovery of controller-retained daily history after startup/reconnect without fabricating raw samples |
| [`polling-performance.md`](polling-performance.md) | Full-profile polling instrumentation, automatic interval selection, persisted performance metrics, RTU utilization estimates, persistence cadence, and safe benchmarking |
| [`canonical-device-identity.md`](canonical-device-identity.md) | Evidence-derived physical-controller identity, canonical telemetry IDs, connection history, endpoint reconciliation, and migration behavior |
| [`controller-scoped-data.md`](controller-scoped-data.md) | Immutable controller UIDs, identity aliases, unified multi-device history, source provenance, controller-first API routes, and history analytics |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, named and reserved register semantics, firmware gates, verification registry, coverage, and extension rules |
| [`device-intelligence.md`](device-intelligence.md) | Runtime identity resolution, metadata, confidence, capabilities, validation, and effective firmware register/reserved maps |
| [`catalog-maintenance.md`](catalog-maintenance.md) | Official-source download/validation, conservative PDF extraction, reserved/address-space classification, advisory diffs, provenance, and CI review gates |
| [`releases/README.md`](releases/README.md) | Release-note index; current release is `v0.6.0` |

---

## Data flow

```text
physical Morningstar device
        |
        v
transport/discovery -----> capture recorder -----> capture bundle
        |                                       |
        +----> poll traffic instrumentation      |
        |             |                          |
        v             v                          v
catalog declarations <---- replay client <---------+
 named registers
 reserved ranges
        |
        v
runtime intelligence
        |
        v
evidence-derived controller identity + connection inventory
        |
        v
immutable controller UID + identity aliases
        |
        v
watcher + selected polling connection + lifecycle/backoff
        |
        +----> automatic poll interval evaluation
        |
        +----> persistence limiter (normal poll-driven storage >= 1 s/controller)
        |
        +----> polling performance
        |
        +----> retained-history provider registry / reconnect backfill
        |
        v
SQLite/WAL persistence
        |
        +----> raw endpoint/device APIs
        |
        +----> controller-scoped history/query/aggregation/export
        |       |-- retained controller-daily evidence
        |       |-- day-level coverage and gap reconciliation
        |       `-- controller-vs-local energy accounting
        |
        +----> polling performance/history API
        |
        +----> physical controller inventory API
        |
        +----> normalized system/site aggregation
        |       |-- quality-aware metrics/history
        |       |-- component graph / topology
        |       |-- power flow / energy ledger
        |       |-- authoritative whole-system metering when source-backed
        |       |-- unified event timeline
        |       `-- SSE telemetry/events
        |
        +----> optional inbound SNMP trap events
        |
        v
FastAPI /v1

catalog declarations ---- official source index
        |                       |
        v                       v
   catalog runtime        maintenance scanner
        |                       |
        v                       v
verification registry        advisory report
```

Raw persisted poll/register history remains authoritative for observations actually made by the service. Live Modbus polling can run faster than storage: normal watcher poll-driven persistence is limited by `database.telemetry_write_interval_seconds` and cannot be configured below one second per physical controller. Intermediate polls still affect live lifecycle/intelligence and automatic interval selection but do not create extra history rows.

Controller-retained records remain a separate provenance class and are never expanded into fabricated raw samples. v0.6 adds a read-time reconciliation/analytics layer that can say a day is recovered by controller evidence, partial, or still missing, while preserving the distinction between daily retained evidence and high-frequency live polling.

Energy accounting likewise keeps independent sources separate. Controller-reported daily Wh is never silently replaced by a locally integrated power estimate; when both exist, the API can report their discrepancy and the quality/provenance of each source.

Persistent identity prevents future IP/USB locator changes from creating another application-facing controller. Immutable controller UIDs remain stable even when identity evidence is promoted, and controller-scoped reads combine all historical member device IDs while preserving `source_device_id` on raw observations.

The system/site layer is derived from those controller scopes. Additive metrics are summed only when their normalized semantics declare that operation; bus voltage/temperature/SOC use representative aggregations instead. Source-backed whole-system GenStar currents/counters are treated as non-additive system observations and use conflict-aware resolution rather than being summed across reporters. Aggregate responses preserve contributors, expected contributors, source observations, quality, and authority.

## Register terminology

| Term | Meaning |
| --- | --- |
| named register | Source-backed `RegisterSpec` with semantic name/decoder/unit/category |
| reserved range | Manufacturer-documented readable word(s) intentionally left unnamed; represented by `ReservedRegisterRange` |
| raw alias | Transport/evidence name such as `holding_0x003F`; not automatically proof of a missing mapping |
| unknown/unmapped | Raw address not covered by a named register or documented reserved range |

The effective register-map API publishes named registers and firmware-applicable `reserved_ranges` separately. Consumers should not invent names for reserved words.

## Identity terminology

| Term | Meaning |
| --- | --- |
| `controller_uid` | Immutable generated ID for the physical controller; preferred for applications |
| `controller_id` | Current strongest evidence-derived identity alias; may change as stronger evidence appears |
| `device_id` | Raw telemetry-owning storage row retained for compatibility/provenance |
| `system_uid` | Persistent application grouping above one or more immutable physical controllers |

Do not treat these as interchangeable. The controller-first API exists specifically so applications do not need to manually merge legacy device histories, while the system API provides an additional normalized multi-controller view.

## Evidence and quality terminology

| Term | Meaning |
| --- | --- |
| **vendor-documented** | Morningstar source material specifies the register/behavior |
| **software-tested** | Unit/replay tests exercise the implementation |
| **fixture-verified** | A deterministic replay fixture decodes correctly |
| **physical-device-verified** | A reviewed capture from known hardware confirms behavior |
| `live_poll` | Persisted local Modbus observation provenance |
| `controller_internal_logger` | Controller-retained daily evidence provenance |
| `recovered` gap | No persisted live samples for a day, but a complete retained daily record exists |
| `partial` gap | No persisted live samples and only incomplete retained daily evidence exists |
| `missing` gap | Neither persisted live samples nor retained evidence exists |
| `conflict` quality | Multiple whole-system reporters materially disagree, so no single value is asserted |

Catalog verification evidence is separate from controller identity/reconciliation confidence and runtime product-intelligence confidence. Cross-product system semantics and inferred bridge candidates are also kept separate from vendor-derived catalog facts.

## Version note

The latest published GitHub release is `v0.6.0`. It includes the v0.5.0 system/site and domain-package baseline plus controller history coverage, gap reconciliation, controller-vs-local daily energy accounting, system component graph/power-flow/energy-ledger improvements, and authoritative GenStar system metering/energy-balance work merged in the v0.6 release window. The service remains read-only and does not fabricate observations that were never collected.
