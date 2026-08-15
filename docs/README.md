# Documentation index

This directory documents the current MorningstarModbusAPI architecture and operational workflows.

| Document | Scope |
| --- | --- |
| [`architecture.md`](architecture.md) | Runtime layers, capture/replay path, device lifecycle, concurrency, persistence boundaries, and read-only safety model |
| [`hardware-verification.md`](hardware-verification.md) | Physical capture, replay, verification reports, fixture publication, evidence levels, and sanitization |
| [`device-catalog.md`](device-catalog.md) | Declarative Morningstar product profiles, register decoding, firmware gates, coverage, and extension rules |
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
watcher + lifecycle/backoff
          |
          v
SQLite/WAL persistence
          |
          v
FastAPI /v1

catalog declarations ---- official source index
          |                       |
          v                       v
     catalog runtime        maintenance scanner
                                  |
                                  v
                            advisory report
```

Capture/replay is part of the runtime verification path, while vendor-document maintenance remains a separate sidecar. Neither path automatically rewrites vendor-derived family modules.

## Evidence model

The project distinguishes four questions:

1. **Is the behavior documented by Morningstar?**
2. **Does the software have ordinary automated coverage?**
3. **Can a deterministic capture fixture reproduce the behavior through production parsers?**
4. **Has the behavior been observed on identified physical hardware/firmware?**

A positive answer at one level does not automatically imply the next. In particular, synthetic fixtures must never be relabeled as physical-device evidence.

## Version note

The latest published GitHub release is `v0.3.0`. Hardware verification/capture/replay is being developed as the next feature layer on top of that release.
