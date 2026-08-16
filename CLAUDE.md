# Claude Code and OpenClaude project instructions

@AGENTS.md
@.agents/README.md

`AGENTS.md` is the canonical project control tower. Do not maintain an independent copy of project facts here.
For substantial work, invoke or consult the `morningstar-project` skill; it dispatches to canonical
`.agents/skills/*/SKILL.md` procedures. Use the canonical `system-topology-and-power` skill for system/site,
ReadyEdge component, topology, power-flow, or energy-ledger work.

Available specialist agents under `.claude/agents/` cover:

- end-to-end project maintenance;
- catalog/intelligence/vendor-source work;
- capture/replay/verification/lifecycle work;
- system/site topology, ReadyEdge component reconciliation, power flow, and energy accounting;
- independent read-only code review.

For system work, preserve immutable `controller_uid`, distinguish transport topology from component/electrical
relationships, and keep unavailable battery/load/generator quantities explicitly unknown. Never force an energy
balance closed with invented values.

Delegate when specialization helps, but the parent remains responsible for branch truth, integration, tests,
and final completion claims. The read-only Modbus/SNMP boundary in `AGENTS.md` is a hard constraint.
