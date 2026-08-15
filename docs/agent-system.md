# Coding-agent system

MorningstarModbusAPI includes a repository-native instruction and skill system so different coding-agent
harnesses operate from the same architecture, safety boundaries, evidence model, and development workflows.

## Design

The system has three layers:

1. **Control tower** — root `AGENTS.md` contains branch-truth rules, architecture, read-only safety, package
   ownership, engineering conventions, skill routing, validation, and definition of done.
2. **Canonical skills** — `.agents/skills/*/SKILL.md` contains detailed procedures for a particular subsystem or
   task family.
3. **Harness adapters** — Claude/OpenClaude, Copilot, OpenCode, Pi, and OMP files adapt their native discovery
   conventions back to the same control tower and skills.

This avoids maintaining seven diverging copies of project behavior.

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

The adapters intentionally avoid hard-coded model versions and temporary PR state. Harness features can change
faster than the project; the canonical project knowledge should remain stable.

## Skill selection

Root `AGENTS.md` contains the task router. Agents should load only the relevant domain skills, plus
`testing-and-ci` for implementation and `pr-review-and-integration` for GitHub integration.

Examples:

- a USB reconnect bug -> `project-orientation` + `device-lifecycle-reconnect` + `testing-and-ci`;
- a new Morningstar register -> `catalog-and-intelligence` + `catalog-maintenance-provenance` +
  `testing-and-ci`;
- a history endpoint -> `telemetry-history-storage` + `api-development` + `testing-and-ci`;
- physical fixture promotion -> `hardware-verification-replay` + `testing-and-ci`;
- a release -> `documentation-and-release` + `pr-review-and-integration`.

## Specialist agents

Claude, Copilot, and OpenCode receive four task-focused agent profiles:

- **project maintainer** — end-to-end implementation across normal layers;
- **catalog specialist** — register maps, firmware gates, intelligence, maintenance/provenance;
- **verification specialist** — capture/replay, evidence, lifecycle/reconnect;
- **reviewer** — independent read-oriented review of correctness, safety, migrations, tests, and docs.

They are convenience personas, not alternate sources of truth. Each is required to read `AGENTS.md` and the
canonical skill procedures.

Pi and OMP can directly combine the root context and portable skills rather than needing duplicated specialist
files. OMP additionally receives a small hard-rule file to keep the read-only/evidence constraints sticky.

## Updating agent knowledge after a project change

Do not paste release notes into every adapter. Instead:

1. update source/tests and the normal project documentation;
2. decide whether the change affects an always-on invariant — if yes, update `AGENTS.md`;
3. update the owning canonical skill if its procedure or subsystem map changed;
4. update an adapter only when the harness-specific integration itself changed.

Agents are instructed to inspect the checkout before assuming current functionality, so temporary feature
branches and open PRs should not be encoded into persistent instruction files.

## Validation

Agent Markdown/config additions should not alter runtime behavior. Any change to this system should still pass
normal repository validation:

```bash
ruff check .
pytest -q
```

Review the final diff for malformed YAML frontmatter, stale paths, duplicated contradictory policy, and any
accidental runtime/configuration changes.
