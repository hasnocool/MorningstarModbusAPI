# MorningstarModbusAPI documentation index

These documents describe the current merged `main` line and the runtime behavior published in `v0.5.0`. Feature branches may add development-only documents before the next published release.

## Recommended reading

If you are integrating the service rather than modifying it internally:

1. [`../README.md`](../README.md) — installation, CLI, capability overview, preferred controller-first model, register semantics, and polling/persistence behavior.
2. [`api.md`](api.md) — HTTP routes, identifiers, effective register maps, history query semantics, limits, exports, and examples.
3. [`system-api.md`](system-api.md) — normalized multi-controller system/site metrics, quality, topology, event timeline, SSE, retained-history providers, and optional SNMP trap ingestion.
4. [`controller-scoped-data.md`](controller-scoped-data.md) — why `controller_uid` is the stable application identifier and how legacy history is unified.
5. [`telemetry-history.md`](telemetry-history.md) — persisted history, polling-vs-storage cadence, aggregation/statistics semantics, and retention guarantees.
6. [`polling-performance.md`](polling-performance.md) — automatic watcher cadence, persisted polling metrics, benchmarking, and RTU-utilization limits.
7. [`controller-history-backfill.md`](controller-history-backfill.md) — controller-retained daily history and its provenance limits.

If you are developing the project itself, start with [`architecture.md`](architecture.md) and the root [`AGENTS.md`](../AGENTS.md).

## Documentation map

| Document | Scope |
| --- | --- |
| [`api.md`](api.md) | Controller-first and legacy HTTP API, identifiers, effective register maps/reserved ranges, time ranges, resolutions, query limits, exports, errors, and examples |
| [`system-api.md`](system-api.md) | Multi-controller system/site aggregation, normalized semantics, quality, topology, events, SSE, retained-history provider architecture, and SNMP trap ingestion |
| [`architecture.md`](architecture.md) | Runtime layers, controller identity/UID flow, lifecycle, auto polling, persistence cadence, query paths, backfill, capture/replay, and read-only safety |
| [`agent-system.md`](agent-system.md) | Shared coding-agent control tower, portable skills, harness adapters, specialist agents, and maintenance rules |
| [`hardware-verification.md`](hardware-verification.md) | Physical capture, replay, verification reports, fixture publication, evidence levels, lifecycle/persistence distinctions, and sanitization |
| [`telemetry-history.md`](telemetry-history.md) | Persisted telemetry retention, device/controller scopes, polling-vs-storage cadence, time ranges, aggregation, statistics, and streaming export |
| [`controller-history-backfill.md`](controller-history-backfill.md) | Provenance-aware recovery of controller-retained daily history after startup/reconnect without fabricating raw samples |
| [`polling-performance.md`](polling-performance.md) | Full-profile polling instrumentation, automatic interval selection, persisted performance metrics, RTU utilization estimates, persistence cadence, and safe benchmarking |
| [`canonical-device-identity.md`](canonical-device-identity.md) | Evidence-derived physical-controller identity, canonical telemetry IDs, connection history, endpoint reconciliation, and migration behavior |
| [`controller-scoped-data.md`](controller-scoped-data.md) | Immutable controller UIDs, identity aliases, unified multi-device history, source provenance, and controller-first API routes |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, named and reserved register semantics, firmware gates, verification registry, coverage, and extension rules |
| [`device-intelligence.md`](device-intelligence.md) | Runtime identity resolution, metadata, confidence, capabilities, validation, and effective firmware register/reserved maps |
| [`catalog-maintenance.md`](catalog-maintenance.md) | Official-source download/validation, conservative PDF extraction, reserved/address-space classification, advisory diffs, provenance, and CI review gates |

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
        +----> retained-history provider registry
        |
        v
SQLite/WAL persistence
        |
        +----> raw endpoint/device APIs
        |
        +----> controller-scoped history/query/aggregation/export
        |
        +----> polling performance/history API
        |
        +----> physical controller inventory API
        |
        +----> normalized system/site aggregation
        |       |-- quality-aware metrics/history
        |       |-- topology/bridge candidates
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

Capture/replay is part of the runtime verification path, while vendor-document maintenance remains a separate sidecar. Verification evidence is deliberately kept outside vendor-derived family modules.

Raw persisted poll/register history remains authoritative for historical queries. Live Modbus polling can run faster than storage: normal watcher poll-driven persistence is limited by `database.telemetry_write_interval_seconds` and cannot be configured below one second per physical controller. Intermediate polls still affect live lifecycle/intelligence and automatic interval selection but do not create extra history rows.

Controller-retained records remain separate source classes with explicit source/retrieval provenance and are never expanded into fabricated raw samples. The provider registry lets future verified Morningstar logger backends reuse watcher scheduling without inventing undocumented retrieval methods.

Persistent identity prevents future IP/USB locator changes from creating another application-facing controller. Immutable controller UIDs remain stable even when identity evidence is promoted, and controller-scoped reads combine all historical member device IDs while preserving `source_device_id` on raw observations.

The system/site layer is derived from those controller scopes. Additive metrics are summed only when their normalized semantics declare that operation; bus voltage/temperature/SOC use representative aggregations instead. Aggregate responses expose contributors, expected contributors, source observations, and `complete`/`partial`/`empty` quality rather than hiding missing controllers.

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

## Evidence model

| Tier | Meaning |
| --- | --- |
| **vendor-documented** | Morningstar source material specifies the register/behavior |
| **software-tested** | Unit/replay tests exercise the implementation |
| **fixture-verified** | A deterministic replay fixture decodes correctly |
| **physical-device-verified** | A reviewed capture from known hardware confirms behavior |

A profile must not be promoted across tiers without matching evidence. Catalog verification evidence is separate from controller identity/reconciliation confidence and runtime product-intelligence confidence.

Cross-product system semantics and inferred bridge candidates are also kept separate from vendor-derived catalog facts. An inferred shared TCP/multi-unit topology is useful evidence but is not promoted to a claimed physical bridge without stronger verification.

## Version note

The latest published GitHub release is `v0.5.0`. It includes the v0.4.0 controller-first identity/history, reconnect, polling-performance, retained-history, capture/replay, and register-semantics baseline plus the normalized multi-controller system/site API, quality-aware aggregate metrics/history, topology and unified events, SSE streaming, retained-history provider architecture, optional inbound SNMP trap ingestion, expanded GenStar logger coverage, and the domain-oriented package reorganization. The system/site API is now released behavior rather than development-only functionality.
