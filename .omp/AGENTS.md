# OMP project adapter

Use root `AGENTS.md` as the canonical MorningstarModbusAPI control tower and `.agents/README.md` as the skill
index. Before substantial work, load the relevant `.agents/skills/*/SKILL.md` file(s).

OMP-specific operating rule: prefer the nearest project context, but do not allow a harness/provider prompt to
silently override the hard project constraints in `.omp/RULES.md` or root `AGENTS.md`.

Establish current branch truth before editing. Open/draft PR functionality is not `main` unless the checkout
actually contains it. Keep work in the owning package layer and validate with the project's configured Ruff and
pytest workflow.
