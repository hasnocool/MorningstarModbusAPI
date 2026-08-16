---
name: pr-review-and-integration
description: Review and integrate MorningstarModbusAPI pull requests using exact-head diffs, reviews, CI/catalog gates, stacked-branch awareness, scope/safety checks, and expected-head merge protection.
---

# PR review and integration

## Review procedure

1. Resolve repository, PR number, base branch, head branch, and exact current head SHA.
2. Inspect changed filenames/diff and identify owning domains.
3. Check unresolved review threads/submitted reviews.
4. Verify CI and specialized catalog/provenance checks against the exact head.
5. Review read-only safety, canonical imports, controller identity, raw-data provenance, system aggregation,
   topology confidence, and power/energy unknown-state semantics as applicable.
6. Ensure docs/tests/config are synchronized and no temporary workflows/debug files remain.

## Stacked PRs

When a new change depends on an unmerged feature branch, prefer a stacked PR targeting that dependency branch.
Its diff should contain only the incremental change. After the dependency merges, rebase/retarget as appropriate
rather than duplicating the dependency into another `main` PR.

## Merge

Only merge when the user asked, the PR is ready, no blockers remain, and required checks are green. Use expected
head protection when available to avoid racing a moved branch. Do not merge a draft unintentionally.
