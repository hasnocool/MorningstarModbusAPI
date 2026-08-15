# Documentation index

This directory documents the current MorningstarModbusAPI architecture and operational workflows.

| Document | Scope |
| --- | --- |
| [`architecture.md`](architecture.md) | Runtime layers, capture/replay path, in-memory device lifecycle, persistence boundaries, and read-only safety model |
| [`agent-system.md`](agent-system.md) | Shared coding-agent control tower, portable skills, harness adapters, specialist agents, and maintenance rules |
| [`hardware-verification.md`](hardware-verification.md) | Physical capture, replay, verification reports, fixture publication, evidence levels, and sanitization |
| [`telemetry-history.md`](telemetry-history.md) | Raw telemetry retention, time ranges, multi-register history, aggregation, statistics, and streaming export |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, firmware gates, verification registry, coverage, and extension rules |
| [`device-intelligence.md`](device-intelligence.md) | Runtime identity resolution, metadata, confidence, capabilities, validation, and effective firmware register maps |
| [`catalog-maintenance.md`](catalog-maintenance.md) | Official-source download/validation, conservative PDF extraction, advisory diffing, provenance, and CI review gates |
| [`vendor/morningstar/README.md`](vendor/morningstar/README.md) | Vendor source policy and how to obtain official Morningstar source documents |
| [`vendor/morningstar/REFERENCE.md`](vendor/morningstar/REFERENCE.md) | Concise implementation-oriented protocol notes derived from official Morningstar documents |
| [`vendor/morningstar/pdfs/README.md`](vendor/morningstar/pdfs/README.md) | Human-readable manifest of official PDF filenames/URLs used by the catalog |
| [`vendor/morningstar/sources.json`](vendor/morningstar/sources.json) | Machine-readable authoritative source index |
| [`../catalog-proposals/README.md`](../catalog-proposals/README.md) | Required provenance format for reviewed vendor-derived catalog/source-index changes |

## Layer ownership

```text
physical Morningstar device
          |
          v
transport/discovery -----> capture recorder -----> capture bundle
          |                                       |
          v                                       v
catalog declarations <---- replay client <---------+
          |
          v
runtime intelligence
          |
          v
watcher + in-memory lifecycle/backoff
          |
          v
SQLite/WAL persistence
          |
          +----> raw/latest API
          |
          +----> history query/aggregation/export
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

Capture/replay is part of the runtime verification path, while vendor-document maintenance remains a separate
sidecar. Verification evidence is deliberately kept outside vendor-derived family modules. The history layer
queries existing immutable poll/register rows and does not replace them with lossy rollups.

## Evidence model

The project distinguishes four questions:

1. **Is the behavior documented by Morningstar?**
2. **Does the software have ordinary automated coverage?**
3. **Can a deterministic capture fixture reproduce the behavior through production parsers?**
4. **Has the behavior been observed on identified physical hardware/firmware?**

A positive answer at one level does not imply the next. Synthetic fixtures must never be relabeled as
physical-device evidence.

## Runtime status versus lifecycle

The watcher keeps the detailed six-state lifecycle in memory and logs it during discovery/poll failures. SQLite
currently persists a simpler device status (`online` or `error`) together with `last_seen` and `last_error`; there
is not yet a dedicated lifecycle API or lifecycle table unless the checked-out development branch explicitly adds
one.

## Coding-agent governance

Repository-aware coding agents should start from root [`../AGENTS.md`](../AGENTS.md). Detailed task procedures
are shared under [`../.agents/skills/`](../.agents/skills/) and adapted for Claude/OpenClaude, GitHub Copilot,
OpenCode, Pi, OMP, and ChatGPT/Codex without duplicating project truth. See [`agent-system.md`](agent-system.md).

The agent system itself is covered by `tests/test_agent_system.py` so missing adapters/skills, duplicate skill IDs,
incomplete routing, and temporary PR/SHA pinning are caught by normal CI.

## Version note

The latest published GitHub release is `v0.3.0`. The current development line includes hardware verification/
capture/replay, lifecycle changes, and the richer time-series query/export layer added after that release, so
these documents describe current development rather than only the latest tagged release.
