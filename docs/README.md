# MorningstarModbusAPI documentation index

| Document | Scope |
| --- | --- |
| [`architecture.md`](architecture.md) | Runtime layers, capture/replay path, in-memory device lifecycle, persistence boundaries, and read-only safety model |
| [`agent-system.md`](agent-system.md) | Shared coding-agent control tower, portable skills, harness adapters, specialist agents, and maintenance rules |
| [`hardware-verification.md`](hardware-verification.md) | Physical capture, replay, verification reports, fixture publication, evidence levels, and sanitization |
| [`telemetry-history.md`](telemetry-history.md) | Raw telemetry retention, time ranges, multi-register history, aggregation, statistics, and streaming export |
| [`controller-history-backfill.md`](controller-history-backfill.md) | Provenance-aware recovery of controller-retained daily history after startup/reconnect without fabricating raw samples |
| [`polling-performance.md`](polling-performance.md) | Full-profile polling instrumentation, persisted performance metrics, RTU utilization estimates, and safe interval benchmarking |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, firmware gates, verification registry, coverage, and extension rules |
| [`device-intelligence.md`](device-intelligence.md) | Runtime identity resolution, metadata, confidence, capabilities, validation, and effective firmware register maps |
| [`catalog-maintenance.md`](catalog-maintenance.md) | Official-source download/validation, conservative PDF extraction, advisory diffing, provenance, and CI review gates |

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
        |             |
        v             v
runtime intelligence   polling performance rows
        |             |
        v             v
watcher + in-memory lifecycle/backoff
        |
        v
SQLite/WAL persistence
        |
        +----> raw/latest API
        |
        +----> history query/aggregation/export
        |
        +----> polling performance/history API
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

Capture/replay is part of the runtime verification path, while vendor-document maintenance remains a separate sidecar. Verification evidence is deliberately kept outside vendor-derived family modules. The raw history layer queries existing immutable poll/register rows and does not replace them with lossy rollups. Controller-retained daily records are persisted separately with explicit source/retrieval provenance. Polling instrumentation observes the same read-only Modbus exchanges used by normal profile polling and stores performance separately from controller telemetry.

## Evidence model

| Tier | Meaning |
| --- | --- |
| **vendor-documented** | Morningstar PDF specifies the register and scaling |
| **software-tested** | Unit/replay test passes against the specification |
| **fixture-verified** | Deterministic replay fixture decodes correctly |
| **physical-device-verified** | Sanitized capture from known hardware confirms behavior |

A profile must not be promoted across tiers without matching evidence. The catalog reports the current tier for each profile.

## Version note

The latest published GitHub release is `v0.3.0`. The current development line includes hardware verification/capture/replay, lifecycle changes, richer time-series query/export, controller-retained daily-history backfill, and polling-performance instrumentation added after that release, so these documents describe current development rather than only the latest tagged release.
