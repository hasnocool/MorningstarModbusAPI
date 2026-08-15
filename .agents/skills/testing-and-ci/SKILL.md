---
name: testing-and-ci
description: Design deterministic MorningstarModbusAPI regression coverage and validate changes with the repository's configured Ruff, pytest, Python matrix, maintenance checks, replay fixtures, and GitHub Actions evidence.
---

# Testing and CI

Use this skill for every implementation/fix/refactor before claiming completion.

## Read the configuration

Inspect current:

- `pyproject.toml` for supported Python, pytest, Ruff, optional extras;
- `.github/workflows/ci.yml` for the actual CI matrix/commands;
- specialized workflows such as catalog maintenance when affected.

Do not hard-code an old Python matrix into new automation.

## Development setup

Typical setup is:

```bash
python -m pip install -e '.[dev]'
```

Vendor-document scanner work may additionally require the `maintenance` extra.

## Iteration strategy

1. Reproduce the bug or define the expected behavior with the narrowest deterministic test.
2. Run the target test/module while iterating.
3. Run nearby subsystem tests after the fix.
4. Run Ruff.
5. Run the full test suite before repository-wide completion claims.

Normal final validation:

```bash
ruff check .
pytest -q
```

If local execution is unavailable, use CI evidence and clearly say which checks were observed instead of claiming
local execution.

## Test style

- Keep tests deterministic, isolated, and fast enough for CI.
- Prefer production parser/replay paths over brittle copies of implementation logic.
- Do not require Internet or physical hardware in normal CI.
- Use temporary SQLite databases/files for storage/export tests.
- Use async pytest patterns configured by the project.
- Assert externally meaningful behavior, plus key invariants such as cleanup/read-only safety.
- Add regression tests for each bug class, not only the exact sample that exposed it.

## Hardware and replay

Use replay fixtures for deterministic Modbus transaction sequences. A test using a synthetic fixture proves
software/fixture behavior only; it does not prove physical hardware behavior.

Do not make CI conditional on a real Morningstar controller.

## Catalog changes

Catalog/source-index changes may require:

- catalog tests;
- intelligence tests;
- maintenance/provenance tests;
- a proposal record.

Run the dedicated maintenance validation path rather than only general pytest.

## Storage/API changes

For persistence/history work test both new/fresh databases and compatibility with existing schema assumptions when
relevant. For API work cover validation/errors/limits, not only happy paths.

## CI review

When a PR is open, check CI on the **current head SHA**. If head moved, old green runs are not sufficient.

For a failure:

1. inspect the failed job/step/log;
2. classify code/test/environment/flaky/tooling cause;
3. fix root cause;
4. rerun relevant local test if possible;
5. push and verify a new green run.

Do not disable tests/lint or loosen assertions merely to turn CI green.

## Completion evidence

Report exactly what ran, e.g. "`ruff check .` passed; `pytest -q` passed" or "GitHub CI passed Python 3.12/3.13/
3.14 on head `<sha>`". Do not say "all checks" if only one targeted test ran.
