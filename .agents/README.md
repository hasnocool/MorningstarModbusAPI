# Multi-harness agent system

This directory is the portable project knowledge layer for MorningstarModbusAPI coding agents.

The goal is not to duplicate a giant prompt for every harness. `AGENTS.md` contains always-on invariants and
architecture; `.agents/skills/` contains task procedures; each harness receives a thin adapter that routes back
to those canonical files.

## Compatibility map

| Harness | Always-on project context | Skills / specialist surface |
| --- | --- | --- |
| ChatGPT / Codex | root `AGENTS.md` | canonical `.agents/skills/` paths routed from `AGENTS.md` |
| Claude Code | `CLAUDE.md` -> `AGENTS.md` | `.claude/skills/morningstar-project/` + `.claude/agents/` |
| OpenClaude | Claude-compatible `CLAUDE.md` | same Claude skill/agent adapter |
| GitHub Copilot | `.github/copilot-instructions.md` + root `AGENTS.md` where supported | `.agents/skills/`, `.github/instructions/`, `.github/agents/` |
| OpenCode | root `AGENTS.md` | `.agents/skills/` + `.opencode/agents/` |
| Pi | root `AGENTS.md` | `.agents/skills/` + `.pi/APPEND_SYSTEM.md` |
| OMP / oh-my-pi | `.omp/AGENTS.md` + root instructions | `.agents/skills/` + `.omp/RULES.md` |

Harness capabilities evolve. The adapter files deliberately avoid fragile model names or temporary tool IDs;
project behavior remains in the canonical layer.

## Canonical skills

- `project-orientation` — establish branch truth and subsystem ownership.
- `read-only-modbus-development` — transport/protocol/discovery/polling changes without violating read-only safety.
- `catalog-and-intelligence` — product maps, decoders, firmware gates, identity, confidence, verification metadata.
- `hardware-verification-replay` — capture bundles, strict replay, evidence and fixture handling.
- `device-lifecycle-reconnect` — disconnect/reconnect, stale endpoints, retry/backoff, lifecycle state.
- `telemetry-history-storage` — SQLite/WAL, raw retention, time-series queries, stats, aggregation, streaming export.
- `api-development` — FastAPI endpoint work and compatibility/error/streaming behavior.
- `catalog-maintenance-provenance` — official-source scanning, discrepancy classification, provenance gates.
- `testing-and-ci` — deterministic regression coverage, Ruff, pytest, CI matrix.
- `documentation-and-release` — docs reconciliation, version/release workflow, current-vs-release wording.
- `pr-review-and-integration` — PR review, review threads, checks, branch stack, safe integration.

Each skill is a directory with a `SKILL.md` using portable Agent Skills-style YAML frontmatter.

## Loading policy

Agents should not preload every skill into every prompt. Start with the task router in root `AGENTS.md`, then
read the one or two domain skills that own the work. Add `testing-and-ci` for implementation tasks and
`pr-review-and-integration` when publishing or merging.

A skill may point at source/docs/tests. Those files, not the skill prose, are the final authority for the
checked-out branch.

## Keeping this system current

When architecture changes:

1. update the owning project docs/source/tests first;
2. update `AGENTS.md` only if an always-on invariant, package boundary, or routing rule changed;
3. update the relevant skill if its workflow changed;
4. update thin harness adapters only when that harness's file format or discovery convention changed;
5. avoid encoding temporary PR numbers, transient branch SHAs, local device paths, or unreleased feature claims.

When adding a new skill, add it to this index and the root task router. Prefer a new skill over making
`AGENTS.md` indefinitely longer.

## What agents are empowered to do

Within their available tools and user authorization, these instructions are designed for agents to:

- inspect and explain the architecture;
- implement features/fixes/refactors in the correct layer;
- extend documented device support through reviewed catalog changes;
- add APIs/history/statistics/export behavior;
- improve reconnect/runtime reliability;
- create and validate replay fixtures/evidence workflows;
- maintain vendor-source scanning and provenance;
- write tests and documentation;
- review GitHub PRs/CI and prepare integration changes;
- prepare releases when explicitly requested.

They are not authorized by project instructions to add write-capable controller control, publish unsanitized
hardware evidence, republish vendor manuals, fabricate verification status, or merge unrelated work.
