# Coding-agent system

MorningstarModbusAPI includes a repository-native instruction and skill system so different coding-agent
harnesses operate from the same current architecture, read-only safety boundary, controller-identity model,
evidence model, system/site semantics, and development workflows.

## Design

The system has three layers:

1. **Control tower** — root `AGENTS.md` contains branch-truth rules, current domain-package ownership, read-only
   safety, immutable `controller_uid`, data/evidence invariants, system/component/power semantics, skill routing,
   validation, and definition of done.
2. **Canonical skills** — `.agents/skills/*/SKILL.md` contains detailed procedures for subsystem/task families.
3. **Harness adapters** — Claude/OpenClaude, Copilot, OpenCode, Pi, and OMP files adapt native discovery
   conventions back to the same control tower and skills.

This prevents separate harnesses from learning different versions of the project.

## Supported repository adapters

```text
AGENTS.md                                  ChatGPT/Codex + shared project truth
CLAUDE.md                                  Claude Code + OpenClaude adapter
.claude/skills/morningstar-project/        Claude/OpenClaude skill dispatcher
.claude/agents/                            Claude specialist subagents
.github/copilot-instructions.md            Copilot repository instructions
.github/instructions/                      Copilot path-specific instructions
.github/agents/                            Copilot specialist agents
.opencode/agents/                          OpenCode specialist subagents
.pi/APPEND_SYSTEM.md                       Pi supplemental project context
.omp/AGENTS.md + .omp/RULES.md             OMP context + sticky hard rules
.agents/README.md                          shared compatibility/skill index
.agents/skills/                            canonical portable project skills
```

Adapters avoid hard-coded model versions and temporary PR state. The canonical project layer must stay stable
and source/test-driven.

## Canonical skills

The current router includes:

- `project-orientation`;
- `read-only-modbus-development`;
- `catalog-and-intelligence`;
- `hardware-verification-replay`;
- `device-lifecycle-reconnect`;
- `telemetry-history-storage`;
- `system-topology-and-power`;
- `api-development`;
- `catalog-maintenance-provenance`;
- `testing-and-ci`;
- `documentation-and-release`;
- `pr-review-and-integration`.

The `system-topology-and-power` skill owns the cross-controller layer: normalized site metrics and quality,
transport topology, ReadyEdge Connected Product reconciliation, component graphs, evidence-backed relationships,
power flow, and provenance-aware energy accounting. It explicitly preserves observed/derived/unknown states so
missing battery/load/generator measurements are not fabricated.

Implementation work also loads `testing-and-ci`; GitHub publishing/review/merge work also loads
`pr-review-and-integration`.

## Current project vocabulary the agent layer tracks

The v0.5+ runtime is organized into domain packages including `api/`, `capture/`, `controllers/`, `discovery/`,
`domain/`, `history/`, `persistence/`, `polling/`, `protocol/`, `runtime/`, `snmp/`, `systems/`, and `transports/`,
with `catalog/` and `intelligence/` retaining product/evidence ownership. The removed pre-release flat modules
are not architectural ownership boundaries.

Cross-cutting concepts the agent system must preserve include:

- immutable physical `controller_uid` and alias/history continuity across endpoint changes;
- controller-scoped telemetry across historical device IDs with `source_device_id` provenance;
- retained-history provider abstraction rather than one hard-coded product protocol;
- system/site normalized metrics with complete/partial/empty quality and contributor provenance;
- unified events and read-only SSE;
- conservative transport topology/bridge inference;
- ReadyEdge's source-backed Connected Product inventory and reconciliation to physical controllers;
- logical component/electrical relationships separated from transport observations;
- observed/derived/unknown power-flow and energy-ledger semantics;
- the strict no-write Modbus/SNMP/controller-control boundary.

## Skill selection examples

- USB reconnect/identity bug -> `project-orientation` + `device-lifecycle-reconnect` + `testing-and-ci`;
- new Morningstar register -> `catalog-and-intelligence` + `catalog-maintenance-provenance` + `testing-and-ci`;
- retained-history/event work -> `telemetry-history-storage` + `testing-and-ci`;
- system aggregate/quality change -> `system-topology-and-power` + `testing-and-ci`;
- ReadyEdge component reconciliation -> `system-topology-and-power` + `catalog-and-intelligence` +
  `testing-and-ci`;
- power-flow/energy-ledger endpoint -> `system-topology-and-power` + `api-development` + `testing-and-ci`;
- physical fixture promotion -> `hardware-verification-replay` + `testing-and-ci`;
- release -> `documentation-and-release` + `pr-review-and-integration`.

## Specialist agents

Claude, Copilot, and OpenCode receive five task-focused profiles:

- **project maintainer** — end-to-end implementation across normal domain packages;
- **catalog specialist** — register maps, firmware gates, intelligence, vendor-source provenance;
- **verification specialist** — capture/replay, evidence, controller identity/reconnect, hardware verification;
- **system specialist** — system/site metrics, topology, ReadyEdge reconciliation, component graph, power/energy,
  events, and SSE;
- **reviewer** — independent review of correctness, read-only safety, identity/provenance, migrations, tests/docs,
  and system topology/power semantics.

These are personas, not alternate truth sources. Each routes back to root `AGENTS.md` and canonical skills.

## Updating agent knowledge after project changes

1. Update source/tests and normal project docs first.
2. Update `AGENTS.md` when an always-on architecture/invariant changes.
3. Update the owning canonical skill when procedure/ownership changes.
4. Update specialist/adapters when responsibility or harness integration changes.
5. Update this document and `tests/test_agent_system.py` when skill/specialist inventory changes.
6. Do not pin temporary PR numbers, branch SHAs, local device paths, or transient provider/model details.

## Validation

Agent Markdown should not change runtime behavior, but agent-system changes still run normal repository validation:

```bash
ruff check .
pytest -q
```

Review for malformed YAML frontmatter, stale paths, removed flat-module ownership, duplicated contradictory
policy, fabricated current/release claims, and accidental runtime/configuration changes.
