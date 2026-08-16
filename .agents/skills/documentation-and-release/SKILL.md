---
name: documentation-and-release
description: Reconcile MorningstarModbusAPI docs and agent knowledge with source truth, maintain current-vs-release wording and package layout, update version metadata, and prepare releases using the actual workflow.
---

# Documentation and release

Use for README/docs/config examples, agent knowledge, version changes, changelog/release preparation, or releases.

## Documentation truth hierarchy

1. checked-out source/tests/config;
2. branch-specific public behavior;
3. existing docs;
4. old PR/release descriptions.

If docs and source disagree, do not silently change source to match stale prose unless restoring that behavior is
explicitly requested. Start at `docs/README.md` and `docs/package-layout.md`.

## Keep states separate

Always distinguish:

- current checked-out branch;
- merged `main`;
- latest published release/tag;
- open/draft PR proposals.

Development docs may describe branch behavior, but say so. Never call open PR functionality released.

## Documentation coverage

Public behavior changes may require:

- root README capability/CLI/API sections;
- `docs/README.md` index;
- `docs/package-layout.md` canonical package/import map;
- owning architecture/catalog/history/system/component/verification/maintenance guide;
- `config.example.toml` when settings change;
- fixture/evidence policy when verification semantics change.

Use current v0.5+ package names. Do not restore removed flat-module names into architectural diagrams.

For system/component/power documentation:

- distinguish transport topology from evidence-backed component relationships;
- document metric quality/contributors/provenance;
- say when ReadyEdge data is reported-only versus reconciled physical identity;
- label power/energy quantities observed, derived, or unknown;
- never present missing battery net/load/generator values as zeros or measured facts.

## Agent knowledge synchronization

When architecture/responsibilities change, reconcile:

- root `AGENTS.md`;
- `.agents/README.md`;
- owning canonical skills;
- Claude/OpenCode/Copilot/Pi/OMP adapters when their routing/responsibilities changed;
- `docs/agent-system.md`;
- `tests/test_agent_system.py`.

Persistent agent files should not pin temporary PR numbers, branch SHAs, local paths, or model/provider versions.

## Vendor documentation

Do not republish Morningstar manuals/PDFs. Link/index approved official sources and document provenance/cache
workflow. Short implementation notes remain source-backed.

## Version preparation

Inspect all authoritative version sources before changing versions. Choose semantic version based on actual
changes/project intent, not because an agent file suggests a release.

## Release workflow

Inspect `.github/workflows/release.yml` each time. The established release branch pattern may be
`release/vMAJOR.MINOR.PATCH`; verify actual workflow before acting.

Safe process:

1. verify current `main` and latest published release;
2. ensure intended feature PRs are actually merged;
3. choose/bump version in authoritative locations;
4. run full validation;
5. create/push exact release branch expected by workflow;
6. inspect workflow result;
7. verify published tag/release target/version/notes.

Do not release from an unmerged feature branch unless explicitly designed that way.

## Release notes and validation

Summarize user-visible behavior and important safety/migration implications. Do not inflate scanner observations,
synthetic fixtures, inferred topology, or derived values into physical verification. Docs-only changes still need
path/link/diff review. Code/version changes follow `testing-and-ci`; GitHub release integration also follows
`pr-review-and-integration`.
