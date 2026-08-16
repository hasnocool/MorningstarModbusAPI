---
name: pr-review-and-integration
description: Review, prepare, update, stack, and safely integrate MorningstarModbusAPI pull requests using exact base/head state, diffs, CI/provenance, review threads, architecture/safety invariants, and expected-head protection.
---

# PR review and integration

Use when opening/updating/reviewing/merging PRs or diagnosing checks/reviews.

## Resolve exact PR state

Before conclusions or writes inspect:

- repository/PR number;
- state/draft status;
- base branch/SHA;
- head branch/SHA;
- mergeability;
- changed filenames and diff/patch;
- commits if stacking/history matters;
- current `main` if base may have moved;
- CI/checks associated with exact head;
- submitted reviews and unresolved inline threads.

Do not use green checks from an older head after new commits land.

## Review priorities

Review against root `AGENTS.md` and domain skills. Prioritize:

1. accidental Modbus/SNMP/controller write/control paths;
2. data loss/destructive migrations;
3. wrong product/register/function/firmware semantics;
4. physical controller identity split/duplication or lost history provenance;
5. evidence overclaim, especially synthetic/inferred -> physical;
6. async/blocking/cleanup/reconnect regressions;
7. incorrect system aggregation/quality or controller double-counting;
8. topology inference presented as physical fact;
9. fabricated battery/load/generator/power/energy values;
10. API compatibility/unbounded responses;
11. vendor-source/provenance violations;
12. missing tests/stale docs/config;
13. unrelated generated/debug/secrets/capture files.

A large diff is not automatically bad; verify it is coherent and owned by requested behavior.

## Open PR workflow

Before opening:

- ensure branch starts from intended base;
- inspect final diff/stat;
- run/observe validation;
- write body describing behavior, architecture, tests, safety/data/evidence implications, dependency/follow-up;
- do not claim unrun tests.

Use draft only when intentionally unfinished/experimental. A stacked PR can be ready for review if its dependency
and incremental diff are explicit and its own checks are green.

## Stacked/overlapping work

If a new change depends on an unmerged feature branch:

- make dependency explicit;
- branch from the dependency head;
- target the dependency branch so the PR diff is incremental;
- do not duplicate the dependency's runtime diff into another `main` PR;
- after dependency merges, rebase/retarget as appropriate and reverify CI on the new exact head/base.

If another open PR merely overlaps rather than being a dependency, choose independent versus stacked strategy
deliberately and avoid pushing unrelated changes into its branch.

## Address review feedback

Classify each thread:

- correctness/safety issue -> fix + regression test;
- maintainability improvement -> implement if in scope;
- misunderstanding -> reply with concrete source/test evidence;
- stale after code change -> verify new code, reply/resolve when justified.

Do not resolve an actionable thread without addressing it.

## Merge criteria

Only merge when user authorizes integration and:

- PR is not unintentionally draft;
- exact head is reviewed;
- required/relevant CI and provenance gates are green;
- no unresolved actionable review threads remain;
- base/head still match expectations;
- final diff preserves project hard rules.

Use expected-head SHA protection when available.

## After merge

Verify PR reports merged and inspect resulting base/main state when follow-up depends on integration. Retarget
stacked follow-ups based on actual merged state rather than assumption.
