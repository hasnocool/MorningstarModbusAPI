# OMP project adapter

Use root `AGENTS.md` as the canonical MorningstarModbusAPI control tower and `.agents/README.md` as the skill
index. Load relevant `.agents/skills/*/SKILL.md`; use `system-topology-and-power` for system/site, ReadyEdge
components, topology, power flow, and energy ledger tasks.

OMP-specific rule: nearest context may refine workflow, but must not silently override `.omp/RULES.md` or root
hard constraints. Establish branch truth, use canonical v0.5+ package paths, and validate with configured Ruff,
pytest, CI, and provenance gates as applicable.
