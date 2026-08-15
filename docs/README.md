# Documentation index

This directory documents the current `main` architecture of MorningstarModbusAPI.

| Document | Scope |
| --- | --- |
| [`architecture.md`](architecture.md) | Runtime layers, concurrency, persistence boundaries, discovery/polling flow, and read-only safety model |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, register decoding, firmware gates, coverage, and extension rules |
| [`device-intelligence.md`](device-intelligence.md) | Runtime identity resolution, metadata, confidence, capabilities, validation, and effective firmware register maps |
| [`catalog-maintenance.md`](catalog-maintenance.md) | Official-source download/validation, conservative PDF extraction, advisory diffing, provenance, and CI review gates |
| [`vendor/morningstar/README.md`](vendor/morningstar/README.md) | Vendor source policy and how to obtain official Morningstar source documents |
| [`vendor/morningstar/REFERENCE.md`](vendor/morningstar/REFERENCE.md) | Concise implementation-oriented protocol notes derived from official Morningstar documents |
| [`vendor/morningstar/pdfs/README.md`](vendor/morningstar/pdfs/README.md) | Human-readable manifest of official PDF filenames/URLs used by the catalog |
| [`vendor/morningstar/sources.json`](vendor/morningstar/sources.json) | Machine-readable authoritative source index |
| [`../catalog-proposals/README.md`](../catalog-proposals/README.md) | Required provenance format for reviewed catalog/source-index changes |

## Layer ownership

```text
transport/discovery
       |
       v
catalog declarations ---- official source index
       |                        |
       v                        v
runtime intelligence      maintenance scanner
       |                        |
       v                        v
watcher/polling           advisory report
       |
       v
SQLite/WAL persistence
       |
       v
FastAPI /v1
```

The runtime service never depends on the maintenance scanner. Maintenance tooling can download and inspect official source documents, but it does not rewrite catalog modules automatically.

## Version note

The latest published GitHub release is `v0.2.0`. `main` includes additional catalog-maintenance functionality merged after that release, so these documents describe `main` rather than only the latest tagged release.
