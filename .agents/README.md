# Multi-harness agent system

This directory is the portable project knowledge layer for MorningstarModbusAPI coding agents.

`AGENTS.md` contains always-on invariants and current architecture. `.agents/skills/` contains task procedures.
Harness-specific files should stay thin and route back to those canonical sources instead of maintaining their
own divergent copy of project behavior.

## Compatibility map

| Harness | Always-on project context | Skills / specialist surface |
| --- | --- | --- |
| ChatGPT / Codex | root `AGENTS.md` | canonical `.agents/skills/` |
| Claude Code / OpenClaude | `CLAUDE.md` -> `AGENTS.md` | `.claude/skills/morningstar-project/` + `.claude/agents/` |
| GitHub Copilot | `.github/copilot-instructions.md` + root `AGENTS.md` where supported | `.github/instructions/` + `.github/agents/` + canonical skills |
| OpenCode | root `AGENTS.md` | `.opencode/agents/` + canonical skills |
| Pi | root `AGENTS.md` | `.pi/APPEND_SYSTEM.md` + canonical skills |
| OMP / oh-my-pi | `.omp/AGENTS.md` + root instructions | `.omp/RULES.md` + canonical skills |

Harness capabilities evolve faster than the project. Do not pin model versions, temporary tool IDs, PR numbers,
branch SHAs, or provider-specific behavior into the canonical knowledge layer.

## Canonical skills

- `project-orientation` — establish branch truth, package ownership, and current capabilities.
- `read-only-modbus-development` — transports/protocol/discovery/polling without violating read-only safety.
- `catalog-and-intelligence` — product maps, decoders, firmware gates, identity, capabilities, verification.
- `hardware-verification-replay` — capture bundles, strict replay, evidence, hardware validation.
- `device-lifecycle-reconnect` — immutable controller identity, reconnect, endpoint changes, retry/backoff.
- `telemetry-history-storage` — SQLite/WAL, controller scope, retained history, events, query/export behavior.
- `system-topology-and-power` — system/site metrics, quality, topology, ReadyEdge Connected Products, component
  graph, power flow, and provenance-aware energy ledger.
- `api-development` — FastAPI controller/system routes, SSE, validation, error and streaming behavior.
- `catalog-maintenance-provenance` — official-source scanning, discrepancy classification, SHA-bound proposals.
- `testing-and-ci` — deterministic regression coverage, Ruff, pytest, CI/catalog gates.
- `documentation-and-release` — docs reconciliation, package layout, version/release workflows.
- `pr-review-and-integration` — review threads/checks, stacked PRs, safe integration/merge.

Each skill is a directory with a `SKILL.md` using portable Agent Skills-style YAML frontmatter.

## Current architectural vocabulary agents must share

Agents should recognize the current domain packages under `src/morningstar_modbus/`: `api`, `capture`, `catalog`,
`cli`, `config`, `controllers`, `discovery`, `domain`, `history`, `intelligence`, `maintenance`, `persistence`,
`polling`, `protocol`, `runtime`, `snmp`, `systems`, and `transports`.

Important cross-cutting concepts include immutable `controller_uid`, controller-scoped history across historical
device IDs, system/site normalized metrics with quality/provenance, retained-history providers, unified events,
SSE, conservative transport topology, ReadyEdge Connected Product reconciliation, component relationships,
and observed/derived/unknown power and energy accounting.

## Loading policy

Do not preload every skill. Start with the root router, load the owning domain skill(s), add `testing-and-ci` for
implementation, and add `pr-review-and-integration` for publishing/review/merge work.

## Keeping this system current

When architecture changes:

1. update source/tests and normal project docs;
2. update `AGENTS.md` for always-on architecture/invariants;
3. update the owning canonical skill;
4. add or update specialist adapters when the responsibility map changed;
5. update `docs/agent-system.md` and `tests/test_agent_system.py` when the skill/specialist inventory changes;
6. avoid temporary PR/commit state in persistent instructions.

## What agents are empowered to do

Within their available tools and user authorization, agents may inspect/explain architecture, implement
read-only features/fixes/refactors, extend documented product support through reviewed catalog changes, improve
controller/system history and APIs, add topology/component/power read models, improve reconnect reliability,
create verification fixtures, maintain provenance, write tests/docs, review PRs/CI, and prepare releases when
explicitly requested.

They are not authorized by project instructions to add write-capable controller control, fabricate topology or
measurements, publish unsanitized evidence, republish vendor manuals, fabricate verification status, or merge
unrelated work.
