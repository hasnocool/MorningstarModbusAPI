# Claude Code and OpenClaude project instructions

@AGENTS.md
@.agents/README.md

`AGENTS.md` is the canonical project control tower. Do not maintain an independent copy of project facts here.

For substantial work, invoke or consult the `morningstar-project` skill. It dispatches to the canonical
`.agents/skills/*/SKILL.md` procedures so Claude Code/OpenClaude use the same workflows as the other agents.

Available project subagents under `.claude/agents/` specialize in:

- end-to-end project maintenance;
- catalog/intelligence/vendor-source work;
- capture/replay/verification/lifecycle work;
- independent read-only code review.

Delegate when specialization improves focus, but the parent agent remains responsible for branch truth,
integration, tests, and the final claim of completion.

Never infer current functionality from an old conversation or an unmerged PR. Inspect the checked-out branch.
The project's read-only Modbus boundary in `AGENTS.md` is a hard architectural constraint.
