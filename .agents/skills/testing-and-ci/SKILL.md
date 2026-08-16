---
name: testing-and-ci
description: Design deterministic MorningstarModbusAPI regression coverage and validate changes with configured Ruff, pytest, Python matrix, provenance gates, replay fixtures, controller identity, system quality, and exact-head GitHub Actions evidence.
---

# Testing and CI

Use this skill for every implementation/fix/refactor before claiming completion.

## Read configuration

Inspect current:

- `pyproject.toml` for Python, pytest, Ruff, extras;
- `.github/workflows/ci.yml` for actual matrix/commands;
- specialized workflows such as catalog maintenance when affected.

Do not hard-code an old matrix into new automation.

## Development setup

Typical setup:

```bash
python -m pip install -e '.[dev]'
```

Vendor-source scanner work may also need maintenance dependencies.

## Iteration strategy

1. Reproduce bug or define expected behavior with the narrowest deterministic test.
2. Run target test/module while iterating.
3. Run nearby subsystem tests.
4. Run Ruff.
5. Run full test suite before repository-wide completion claims.

Normal final validation:

```bash
ruff check .
pytest -q
```

If local execution is unavailable, use CI evidence and state exactly which checks were observed.

## Test style

- Keep tests deterministic, isolated, and CI-friendly.
- Prefer production parser/replay/service paths over copied implementation logic.
- Normal CI must not require Internet or physical hardware.
- Use temporary SQLite DB/files for persistence/export tests.
- Use configured async pytest patterns.
- Assert external behavior plus key invariants such as cleanup, read-only safety, identity, provenance, and unknowns.
- Add regression tests for a bug class, not only the exact sample.

## Core regression priorities

As relevant, cover:

- strict read-only protocol surface;
- catalog address/function/word width/decoder/reserved/firmware semantics;
- immutable `controller_uid`, identity promotion, endpoint movement, historical device-ID continuity;
- reconnect cleanup/backoff;
- raw telemetry and `source_device_id` provenance;
- retained-history provider behavior;
- event provenance;
- system complete/partial/empty quality and expected contributors;
- metric-specific cross-controller aggregation;
- transport topology inference confidence;
- ReadyEdge Connected Product descriptor decoding and serial reconciliation;
- duplicate prevention and reported-only component fallback;
- component relationship evidence;
- observed/derived/unknown power and energy semantics;
- API validation/SSE/error behavior;
- agent skill/specialist inventory when agent files change.

## Hardware and replay

Replay fixtures validate deterministic software behavior, not physical hardware. CI must not depend on a real
Morningstar controller. Keep evidence levels explicit.

## Catalog changes

Catalog/source-index changes can require catalog/intelligence tests, maintenance/provenance tests, and a proposal
record. Run dedicated provenance validation rather than only general pytest.

## Persistence/system/API changes

For persistence test fresh and existing-style DB assumptions. For system work test missing/stale/partial sources
and no-double-count behavior. For power work test that unavailable battery/load/generator values remain unknown.
For API work cover validation/errors/limits, not just happy paths.

## CI review

When a PR is open, check CI on the **current head SHA**. Old green runs are insufficient after head moves.

For failure:

1. inspect failed job/step/log;
2. classify code/test/environment/flaky/tooling cause;
3. fix root cause;
4. rerun relevant test if possible;
5. push and verify a new green run.

Do not disable tests/lint or loosen assertions merely to turn CI green.

## Completion evidence

Report exactly what ran or was observed. Do not say "all checks" when only targeted tests ran.
