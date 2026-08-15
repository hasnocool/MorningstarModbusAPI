---
name: documentation-and-release
description: Reconcile MorningstarModbusAPI documentation with source truth, maintain current-vs-release wording, update version metadata, and prepare/publish releases using the repository's actual release workflow.
---

# Documentation and release

Use for README/docs/config examples, version changes, changelog/release preparation, or GitHub releases.

## Documentation truth hierarchy

When reconciling docs:

1. checked-out source/tests/config;
2. branch-specific public behavior;
3. existing docs;
4. old PR/release descriptions.

If docs and source disagree, do not silently change source to match stale prose unless the task is explicitly to
restore that behavior.

Start at `docs/README.md` to find the owning guide.

## Keep states separate

Always distinguish:

- **current checked-out branch**;
- **merged `main`**;
- **latest published release/tag**;
- **open/draft PR proposals**.

It is valid for docs describing current development to include post-release functionality, but say so. Never call
an open PR a released feature.

## Documentation coverage

Public behavior changes may require updates to:

- root README capability/CLI/API sections;
- `docs/README.md` index/layer diagram;
- owning architecture/catalog/intelligence/history/verification/maintenance guide;
- `config.example.toml` when settings change;
- fixture/evidence policy when verification semantics change.

Keep terminology aligned with actual model/field/endpoint names.

## Vendor documentation

Do not republish full Morningstar manuals/PDFs. Link/index approved official sources and document provenance/cache
workflow. Short implementation notes must remain source-backed and not imply ownership of vendor material.

## Version preparation

Before changing a version, inspect all version sources on the branch. Historically this includes project metadata
and package `__version__`, but verify current files rather than assuming.

Choose semantic version based on user/project intent and actual changes. Do not bump a version just because an
agent file says a release might be due.

## Release workflow

Inspect `.github/workflows/release.yml` every time. The current established pattern uses a branch named:

```text
release/vMAJOR.MINOR.PATCH
```

and validates that branch-derived tag against project version metadata before creating a GitHub release targeting
the default branch.

A safe release process is:

1. verify current `main` and latest published release;
2. ensure intended feature PRs are actually merged;
3. choose/bump version in every authoritative location;
4. run full validation;
5. create/push the exact release branch expected by workflow;
6. inspect workflow result;
7. verify published tag/release target/version/notes.

Do not publish from an unmerged feature branch unless the release design explicitly says so.

## Release notes

Summarize user-visible behavior and important safety/migration implications. Do not inflate scanner observations,
synthetic fixtures, or draft features into verified product claims.

## Validation

Docs-only changes still deserve diff/link/path review. Any code/version change follows `testing-and-ci`. Release
GitHub integration also follows `pr-review-and-integration`.
