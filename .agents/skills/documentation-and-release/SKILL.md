---
name: documentation-and-release
description: Keep MorningstarModbusAPI documentation, package-layout references, current-vs-release wording, agent knowledge, version metadata, and release workflows synchronized with branch truth.
---

# Documentation and release

## Documentation workflow

1. Inspect branch/source/tests first.
2. Update the owning subsystem doc and `docs/README.md` when public behavior changes.
3. Keep `docs/package-layout.md` aligned with canonical domain packages and imports.
4. Distinguish current branch, `main`, and published-release behavior.
5. For system features, document metric quality/provenance and observed/derived/unknown semantics rather than
   presenting inferred values as measurements.
6. When architecture or skills change, synchronize `AGENTS.md`, `.agents/README.md`, owning skills,
   `docs/agent-system.md`, harness adapters, and `tests/test_agent_system.py`.

## Release workflow

Inspect actual version metadata and `.github/workflows/release.yml`. Do not infer a release version from prose.
Before publishing, verify tests/CI, changelog/release notes, supported package imports, and safety boundaries.
Persistent instructions must not pin temporary PR numbers or commit SHAs.
