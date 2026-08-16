---
name: testing-and-ci
description: Build deterministic MorningstarModbusAPI regression coverage and validate Ruff, pytest, CI, catalog provenance, identity continuity, system quality, and read-only safety against the exact branch head.
---

# Testing and CI

Use targeted tests while iterating, then repository-wide validation before claiming completion.

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

Inspect current workflows for the supported Python matrix and special gates; do not hard-code stale assumptions.

## Regression priorities

- read-only protocol boundary;
- catalog addresses/word widths/decoders/reserved ranges/firmware gates;
- immutable `controller_uid` and endpoint/history continuity;
- reconnect cleanup/backoff;
- raw telemetry/source provenance;
- retained-history provider behavior;
- system aggregation and complete/partial/empty quality;
- topology inference confidence;
- ReadyEdge Connected Product reconciliation and duplicate prevention;
- component relationships/evidence;
- observed/derived/unknown power and energy semantics;
- API validation/SSE/error behavior;
- catalog provenance gate when vendor-derived files change;
- agent-system inventory/frontmatter when agent files change.

Tests should normally not require Internet or physical hardware. Use deterministic fixtures/replay when suitable.
Never make a failing check disappear by deleting coverage or weakening assertions without a justified behavior
change.
