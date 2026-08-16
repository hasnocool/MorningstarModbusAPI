---
name: project-orientation
description: Establish branch truth, package ownership, current capabilities, and the correct subsystem before modifying MorningstarModbusAPI.
---

# Project orientation

Use this skill before non-trivial work or whenever the subsystem is unfamiliar.

## Procedure

1. Inspect branch/HEAD/status/recent commits and any referenced PR base/head.
2. Read `pyproject.toml`, `README.md`, `docs/README.md`, and `docs/package-layout.md`.
3. Inspect source and tests in the owning domain package before trusting prose.
4. Identify whether behavior belongs to `transports`, `protocol`, `discovery`, `controllers`, `catalog`,
   `intelligence`, `runtime`, `persistence`, `history`, `systems`, `api`, `capture`, `snmp`, or `maintenance`.
5. If work crosses controller/system layers, trace immutable `controller_uid` and provenance end to end.
6. If the branch contains system/site work, inspect `systems/semantics.py`, `systems/data.py`, component/power
   services, and `api/routers/systems.py` rather than assuming route/documentation shape.
7. If the task involves ReadyEdge, GenStar, TriStar, retained history, or SNMP, inspect the current catalog and
   source index before assuming capabilities.
8. Select the smallest relevant canonical skills and add `testing-and-ci` for implementation.

## Current architecture checkpoints

- The v0.5+ codebase uses domain packages; removed flat-module imports are not architectural truth.
- Physical identity is `controller_uid`; device IDs/endpoints may change.
- Systems aggregate controllers but do not own/replace physical identity.
- Transport topology, component/electrical relationships, and power accounting are separate evidence layers.
- Power/energy read models must preserve observed/derived/unknown state.
- Branch-only functionality is not automatically `main` or released behavior.

## Output

Before editing, be able to name the owning package(s), public contract affected, evidence/source constraints,
identity/provenance implications, and tests that should prove the change.
