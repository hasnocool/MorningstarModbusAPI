---
applyTo: "tests/**/*.py"
---

# Test rules

Use `.agents/skills/testing-and-ci/SKILL.md`.

- Tests must be deterministic and normally independent of Internet/physical hardware.
- Prefer strict replay fixtures for real Modbus request-sequence regressions.
- Synthetic/replay tests do not constitute physical hardware evidence.
- Use temporary files/databases for persistence/export tests.
- Cover error/boundary/cleanup behavior, not only happy paths.
- Never weaken/delete a valid assertion merely to make CI green.
- Keep tests compatible with the Python/pytest configuration in `pyproject.toml`.
