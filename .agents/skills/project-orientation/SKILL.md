---
name: project-orientation
description: Establish reliable branch truth, current v0.5+ package architecture, subsystem ownership, tests, documentation, release state, and nearby GitHub work before modifying MorningstarModbusAPI.
---

# Project orientation

Use this skill at the start of unfamiliar, broad, ambiguous, or cross-cutting work.

## Goal

Build a small evidence-backed map of the **current checkout**, then route the task to the owning project layer.
Do not solve the task from remembered repository state, an old release, or another open branch.

## Procedure

1. Inspect repository state when available:
   - current branch and HEAD;
   - dirty/untracked files;
   - recent commits;
   - configured remotes if publishing matters.
2. Read root `AGENTS.md`.
3. Read `README.md`, `docs/README.md`, `docs/package-layout.md`, and `pyproject.toml`.
4. Inspect only the source packages and tests likely to own the requested behavior.
5. If a PR/issue/branch is mentioned, inspect exact base/head/diff/status rather than assuming it matches checkout.
6. Identify whether the requested functionality is:
   - already implemented;
   - partially implemented;
   - present only on another/open branch;
   - absent;
   - documented but not implemented;
   - implemented but under-documented.
7. Summarize owning packages, public surfaces, identity/provenance implications, and validation before large edits.

## Current repository map

Verify this against the checkout, but v0.5+ canonical ownership is:

- Modbus transports -> `src/morningstar_modbus/transports/`;
- protocol framing/codec/errors -> `src/morningstar_modbus/protocol/`;
- discovery -> `src/morningstar_modbus/discovery/`;
- immutable physical controller identity/inventory/lifecycle -> `src/morningstar_modbus/controllers/`;
- shared immutable models -> `src/morningstar_modbus/domain/`;
- product/register truth -> `src/morningstar_modbus/catalog/`;
- runtime identity/firmware/confidence -> `src/morningstar_modbus/intelligence/`;
- capture/replay/verification -> `src/morningstar_modbus/capture/`;
- long-running orchestration -> `src/morningstar_modbus/runtime/`;
- SQLite/WAL and persisted events -> `src/morningstar_modbus/persistence/`;
- history/query/retained-history providers -> `src/morningstar_modbus/history/`;
- system/site metrics, topology, components, power -> `src/morningstar_modbus/systems/`;
- HTTP presentation -> `src/morningstar_modbus/api/`;
- optional inbound traps -> `src/morningstar_modbus/snmp/`;
- vendor source scanning/provenance -> `src/morningstar_modbus/maintenance/`;
- CLI orchestration -> `src/morningstar_modbus/cli/`.

The removed pre-release flat modules are not ownership boundaries. Do not reintroduce them for convenience.

## Cross-layer checkpoints

When work crosses layers, explicitly trace:

- stable physical `controller_uid` versus endpoint/device/controller aliases;
- `source_device_id` provenance across controller-scoped history;
- system membership versus physical identity;
- system metric quality and expected contributors;
- transport topology versus component/electrical relationships;
- ReadyEdge-reported product identity reconciliation;
- observed versus derived versus unknown power/energy values;
- vendor/software/fixture/physical verification level.

For system work inspect `systems/semantics.py`, `systems/data.py`, component/power services, and
`api/routers/systems.py`. For retained history inspect provider registration rather than assuming all products use
TriStar LiveView behavior.

## Branch and release reasoning

Keep separate:

- checked-out branch behavior;
- latest merged `main` behavior;
- latest published tag/release behavior.

An open/draft PR is evidence of proposed work only. If a task depends on another open PR, prefer an explicit
stacked branch/PR when appropriate rather than duplicating its diff.

## Questions this skill should answer

Before implementation you should know:

- What exact behavior is requested?
- Which domain package owns it?
- What current tests constrain it?
- Which API/CLI/config/docs surfaces might change?
- Does it touch read-only safety, controller identity, evidence, persistence, migrations, concurrency, privacy,
  system quality, topology confidence, or power accounting?
- Is there an existing branch/PR doing overlapping work?
- What validation will prove completion?

## Handoff

Load the domain skill that owns the work. For implementation, always add
`.agents/skills/testing-and-ci/SKILL.md`. For system/site/topology/component/power work add
`.agents/skills/system-topology-and-power/SKILL.md`. For PR integration add
`.agents/skills/pr-review-and-integration/SKILL.md`.
