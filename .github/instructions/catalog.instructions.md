---
applyTo: "src/morningstar_modbus/catalog/**/*.py,src/morningstar_modbus/intelligence/**/*.py,src/morningstar_modbus/maintenance/**/*.py,catalog-proposals/**/*.json,docs/vendor/morningstar/**"
---

# Catalog, intelligence, and vendor-evidence rules

Use `.agents/skills/catalog-and-intelligence/SKILL.md` and, for vendor-derived work,
`.agents/skills/catalog-maintenance-provenance/SKILL.md`.

- Preserve exact address/function/multi-word/firmware semantics.
- Semantic API names may differ from vendor labels.
- Catalog truth, runtime intelligence confidence, and verification evidence are separate concerns.
- Never promote synthetic fixture evidence to physical-hardware verification.
- Do not translate maintenance scanner output directly into family modules.
- Vendor-derived changes require official-source evidence, SHA-bound proposal provenance, and tests.
- Do not commit/re-publish complete vendor PDFs.
- Do not add write/control register behavior to the runtime.
