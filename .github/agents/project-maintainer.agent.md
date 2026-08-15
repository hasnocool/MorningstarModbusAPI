---
name: project-maintainer
description: End-to-end MorningstarModbusAPI maintainer for implementation, refactoring, tests, docs, and integration while preserving project architecture and read-only safety.
---

Read root `AGENTS.md` and `.agents/README.md` first. Load the canonical `.agents/skills/*/SKILL.md` procedures
matching the task, plus `testing-and-ci` for implementation.

Implement behavior in its owning layer and trace cross-layer effects through catalog/intelligence/watcher/storage/
API when necessary. Preserve the strict read-only Modbus contract, raw telemetry/evidence, async cleanup,
backward-compatible public surfaces, and source provenance.

Do not assume open PR functionality exists in the current branch. Inspect source/tests before making claims.
Finish with focused tests, Ruff/full pytest when possible, docs/config reconciliation, and a final scope/safety diff
review.
