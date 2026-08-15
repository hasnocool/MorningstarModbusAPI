---
name: project-orientation
description: Establish reliable branch truth, project architecture, subsystem ownership, tests, documentation, release state, and nearby GitHub work before modifying MorningstarModbusAPI.
---

# Project orientation

Use this skill at the start of unfamiliar, broad, ambiguous, or cross-cutting work.

## Goal

Build a small evidence-backed map of the **current checkout**, then route the task to the owning project layer.
Do not solve the task from remembered repository state.

## Procedure

1. Inspect repository state when available:
   - current branch and HEAD;
   - dirty/untracked files;
   - recent commits;
   - configured remotes if publishing matters.
2. Read root `AGENTS.md`.
3. Read `README.md`, `docs/README.md`, and `pyproject.toml`.
4. Inspect only the source modules and tests likely to own the requested behavior.
5. If a PR/issue/branch is mentioned, inspect its exact base/head/diff/status rather than assuming it matches the
   checkout.
6. Identify whether the requested functionality is:
   - already implemented;
   - partially implemented;
   - present only on another/open branch;
   - absent;
   - documented but not implemented;
   - implemented but under-documented.
7. Summarize the owning packages, relevant tests, public surfaces, and invariants before making large changes.

## Repository map to verify, not blindly assume

Typical ownership is:

- protocol/transport -> `protocol.py`, `transport.py`;
- discovery -> `discovery.py`;
- product/register truth -> `catalog/`;
- identity/firmware/confidence -> `intelligence/`;
- capture/replay/verification -> `capture.py`, `replay.py`, `verification.py`;
- reconnect/runtime lifecycle -> `lifecycle.py`, `watcher.py`;
- persistence/history -> `storage.py`, `history.py`;
- API -> `api.py`;
- vendor source scanning -> `maintenance/`;
- CLI orchestration -> `cli.py`.

Read the current directory if the task suggests this map changed.

## Branch and release reasoning

Keep three states separate:

- checked-out branch behavior;
- latest merged `main` behavior;
- latest published tag/release behavior.

An open/draft PR is evidence of proposed work only. If another PR overlaps the requested task, report the
relationship and choose a branch strategy that does not accidentally overwrite it.

## Questions this skill should answer

Before implementation you should know:

- What exact behavior is requested?
- Which layer owns it?
- What current tests constrain it?
- Which public API/CLI/config/docs surfaces might change?
- Does it touch read-only safety, evidence, persistence, migrations, concurrency, or privacy?
- Is there an existing branch/PR doing the same work?
- What validation will prove completion?

## Handoff

After orientation, load the domain skill that owns the work. For implementation, always add
`.agents/skills/testing-and-ci/SKILL.md`. For PR integration, add
`.agents/skills/pr-review-and-integration/SKILL.md`.
