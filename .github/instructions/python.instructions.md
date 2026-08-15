---
applyTo: "src/**/*.py"
---

# Python implementation rules

Follow root `AGENTS.md` and the relevant canonical skill.

- Target the Python version and Ruff rules in current `pyproject.toml`.
- Prefer typed, small, composable functions/data models.
- Keep asyncio code non-blocking. Preserve the executor boundary for blocking PySerial operations.
- Keep locks narrowly scoped; bound task/discovery concurrency; preserve cancellation and cleanup.
- Do not hide errors with broad exception handling solely to keep a loop alive.
- Keep product/register knowledge out of generic transport/API modules.
- Preserve the project's read-only Modbus boundary.
- Add/update deterministic tests for changed behavior and run `testing-and-ci` before completion.
