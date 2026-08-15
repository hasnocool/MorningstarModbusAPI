---
name: pr-review-and-integration
description: Review, prepare, update, and safely integrate MorningstarModbusAPI GitHub pull requests using exact base/head state, diffs, CI, review threads, scope, safety invariants, and merge protection.
---

# PR review and integration

Use when opening/updating/reviewing/merging PRs or diagnosing their checks/reviews.

## Resolve exact PR state

Before conclusions or writes, inspect:

- repository and PR number;
- state/draft status;
- base branch/SHA;
- head branch/SHA;
- mergeability;
- changed filenames and diff/patch;
- commits if branch stacking/history matters;
- current `main` if the base may have moved;
- CI/checks associated with the exact head;
- review submissions and unresolved inline threads.

Do not use a green check from an older head after new commits landed.

## Review priorities

Review the diff against root `AGENTS.md` and the relevant domain skill. Prioritize:

1. accidental Modbus write/control paths;
2. data loss/destructive migrations;
3. wrong product/register/function/firmware semantics;
4. evidence overclaim (especially synthetic -> physical hardware);
5. async/blocking/cleanup/reconnect regressions;
6. API backward compatibility and unbounded responses;
7. vendor-source/provenance violations;
8. missing regression tests;
9. stale/misleading docs/config;
10. unrelated generated/debug/secrets/capture files.

A large diff is not automatically bad; verify it is coherent and owned by the requested feature.

## Open PR workflow

Before opening a PR:

- ensure branch starts from the intended base;
- inspect final diff/stat;
- run validation;
- write a body describing behavior, architecture, tests, safety/data/evidence implications, and any known follow-up;
- do not claim unrun tests.

Use draft status for intentionally unfinished/stacked/experimental work.

## Addressing review feedback

Classify each thread:

- real correctness/safety issue -> fix + test;
- maintainability improvement -> implement if in scope;
- misunderstanding -> reply with concrete source/test evidence;
- stale thread after code changed -> verify new code, reply, resolve when justified.

Do not resolve an actionable thread without addressing it.

## Merge criteria

Only merge when the user/request authorizes integration and:

- PR is not unintentionally draft;
- exact head is reviewed;
- required/relevant CI is green;
- no unresolved actionable review threads remain;
- base/head still match expectations;
- final diff preserves project hard rules.

Use expected-head SHA when the merge API supports it so a last-second branch update cannot be merged unseen.

## Stacked/overlapping work

If another open PR changes the same subsystem:

- identify overlap explicitly;
- avoid pushing unrelated changes into that branch;
- choose independent base, stacked base, or rebase deliberately;
- do not document the other PR's behavior as merged unless it is actually in the branch.

## After merge

Verify the PR reports merged and inspect the resulting `main` head when the task depends on integration. If a
release or follow-up depends on the merge, use the actual merge SHA/state rather than assuming success.
