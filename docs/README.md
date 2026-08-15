# MorningstarModbusAPI documentation index

These documents describe the current merged `main` development line. The latest published release is still `v0.3.0`, so some capabilities documented here are newer than the latest tag.

## Recommended reading

If you are integrating the service rather than modifying it internally:

1. [`../README.md`](../README.md) — installation, CLI, capability overview, and the preferred controller-first model.
2. [`api.md`](api.md) — HTTP routes, identifiers, history query semantics, limits, exports, and examples.
3. [`controller-scoped-data.md`](controller-scoped-data.md) — why `controller_uid` is the stable application identifier and how legacy history is unified.
4. [`telemetry-history.md`](telemetry-history.md) — raw history, aggregation/statistics semantics, and retention guarantees.
5. [`controller-history-backfill.md`](controller-history-backfill.md) — controller-retained daily history and its provenance limits.

If you are developing the project itself, start with [`architecture.md`](architecture.md) and the root [`AGENTS.md`](../AGENTS.md).

## Documentation map

| Document | Scope |
| --- | --- |
| [`api.md`](api.md) | Controller-first and legacy HTTP API, identifiers, time ranges, resolutions, query limits, exports, errors, and examples |
| [`architecture.md`](architecture.md) | Runtime layers, controller identity/UID flow, lifecycle, persistence, query paths, backfill, capture/replay, and read-only safety |
| [`agent-system.md`](agent-system.md) | Shared coding-agent control tower, portable skills, harness adapters, specialist agents, and maintenance rules |
| [`hardware-verification.md`](hardware-verification.md) | Physical capture, replay, verification reports, fixture publication, evidence levels, and sanitization |
| [`telemetry-history.md`](telemetry-history.md) | Raw telemetry retention, device/controller scopes, time ranges, aggregation, statistics, and streaming export |
| [`controller-history-backfill.md`](controller-history-backfill.md) | Provenance-aware recovery of controller-retained daily history after startup/reconnect without fabricating raw samples |
| [`polling-performance.md`](polling-performance.md) | Full-profile polling instrumentation, persisted performance metrics, RTU utilization estimates, and safe interval benchmarking |
| [`canonical-device-identity.md`](canonical-device-identity.md) | Evidence-derived physical-controller identity, canonical telemetry IDs, connection history, endpoint reconciliation, and migration behavior |
| [`controller-scoped-data.md`](controller-scoped-data.md) | Immutable controller UIDs, identity aliases, unified multi-device history, source provenance, and controller-first API routes |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, firmware gates, verification registry, coverage, and extension rules |
| [`device-intelligence.md`](device-intelligence.md) | Runtime identity resolution, metadata, confidence, capabilities, validation, and effective firmware register maps |
| [`catalog-maintenance.md`](catalog-maintenance.md) | Official-source download/validation, conservative PDF extraction, advisory diffs, provenance, and CI review gates |

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
        +----> polling performance
        |
        +----> optional retained-history backfill
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

Raw poll/register history remains authoritative. Controller-retained daily records are persisted separately with explicit source/retrieval provenance and are not expanded into fabricated raw samples. Polling instrumentation observes the same read-only profile polling path and stores performance separately from controller telemetry.

Persistent identity prevents future IP/USB locator changes from creating another telemetry history segment. Immutable controller UIDs remain stable even when identity evidence is promoted, and controller-scoped reads combine all historical member device IDs while preserving `source_device_id` on raw observations.

## Identity terminology

| Term | Meaning |
| --- | --- |
| `controller_uid` | Immutable generated ID for the physical controller; preferred for applications |
| `controller_id` | Current strongest evidence-derived identity alias; may change as stronger evidence appears |
| `device_id` | Raw telemetry-owning storage row retained for compatibility/provenance |

Do not treat these as interchangeable. The controller-first API exists specifically so applications do not need to manually merge legacy device histories.

## Evidence model

| Tier | Meaning |
| --- | --- |
| **vendor-documented** | Morningstar source material specifies the register/behavior |
| **software-tested** | Unit/replay tests exercise the implementation |
| **fixture-verified** | A deterministic replay fixture decodes correctly |
| **physical-device-verified** | A reviewed capture from known hardware confirms behavior |

A profile must not be promoted across tiers without matching evidence. Catalog verification evidence is separate from controller identity/reconciliation confidence and runtime product-intelligence confidence.

## Version note

The latest published GitHub release is `v0.3.0`. The current merged development line includes hardware verification/capture/replay, reconnect/lifecycle improvements, richer time-series query/export, controller-retained daily-history backfill, polling-performance instrumentation, physical-controller inventory, persistent canonical identity, immutable controller UIDs, and controller-scoped history added after that release.
