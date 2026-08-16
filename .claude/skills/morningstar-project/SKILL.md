---
name: morningstar-project
description: Route Claude Code/OpenClaude MorningstarModbusAPI work to the repository's canonical project skills and safety rules.
---

# Morningstar project router

Always read root `AGENTS.md` and `.agents/README.md` first, then load the canonical skill(s) that own the task:

- orientation -> `.agents/skills/project-orientation/SKILL.md`
- transport/protocol/discovery/polling -> `.agents/skills/read-only-modbus-development/SKILL.md`
- catalog/intelligence -> `.agents/skills/catalog-and-intelligence/SKILL.md`
- capture/replay/verification -> `.agents/skills/hardware-verification-replay/SKILL.md`
- controller identity/reconnect -> `.agents/skills/device-lifecycle-reconnect/SKILL.md`
- persistence/history/retained history/events -> `.agents/skills/telemetry-history-storage/SKILL.md`
- systems/site/topology/components/power/energy -> `.agents/skills/system-topology-and-power/SKILL.md`
- FastAPI/SSE/export -> `.agents/skills/api-development/SKILL.md`
- vendor-source/provenance -> `.agents/skills/catalog-maintenance-provenance/SKILL.md`
- tests/CI -> `.agents/skills/testing-and-ci/SKILL.md`
- docs/releases -> `.agents/skills/documentation-and-release/SKILL.md`
- PR review/integration -> `.agents/skills/pr-review-and-integration/SKILL.md`

Implementation tasks also load `testing-and-ci`. Publishing/review/merge work also loads
`pr-review-and-integration`.

Do not infer branch functionality from old conversations. Use canonical v0.5+ package imports and preserve the
read-only, immutable-controller-identity, provenance, raw-history, and observed/derived/unknown data contracts.
