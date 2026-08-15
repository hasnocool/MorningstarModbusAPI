---
name: morningstar-project
description: Route MorningstarModbusAPI work to the canonical project skills for architecture, Modbus, catalog, verification, lifecycle, history, API, maintenance, tests, docs, releases, and PR integration.
---

# Morningstar project skill router

Start by reading root `AGENTS.md`. Treat the checked-out branch as truth.

The canonical detailed skills are shared with every harness under `.agents/skills/`. Select only what the task
needs:

- unfamiliar repo/task or branch ambiguity -> `.agents/skills/project-orientation/SKILL.md`
- transport/protocol/discovery/polling -> `.agents/skills/read-only-modbus-development/SKILL.md`
- product catalog/intelligence/firmware -> `.agents/skills/catalog-and-intelligence/SKILL.md`
- capture/replay/verification/fixtures -> `.agents/skills/hardware-verification-replay/SKILL.md`
- disconnect/reconnect/backoff -> `.agents/skills/device-lifecycle-reconnect/SKILL.md`
- SQLite/history/aggregation/export -> `.agents/skills/telemetry-history-storage/SKILL.md`
- FastAPI -> `.agents/skills/api-development/SKILL.md`
- vendor documents/scanner/provenance -> `.agents/skills/catalog-maintenance-provenance/SKILL.md`
- implementation validation -> `.agents/skills/testing-and-ci/SKILL.md`
- docs/version/release -> `.agents/skills/documentation-and-release/SKILL.md`
- PR review/publish/merge -> `.agents/skills/pr-review-and-integration/SKILL.md`

For code changes, always include `testing-and-ci`. For GitHub integration, include
`pr-review-and-integration`. Do not load every domain skill merely because it exists.

Project hard stops:

- no Modbus writes/controller mutation under the current architecture;
- no fabricated hardware verification;
- no destructive raw-history rewrite as a side effect of query features;
- no unsanitized physical capture publication;
- no treating open/draft PR behavior as `main`.
