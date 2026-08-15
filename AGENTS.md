# MorningstarModbusAPI agent control tower

This file is the canonical always-on project instruction set for coding agents. It is intentionally
shared across ChatGPT/Codex, GitHub Copilot, OpenCode, Pi, OMP, Claude Code, and OpenClaude adapters.
Task-specific operating procedures live under `.agents/skills/` and should be loaded only when relevant.

## 1. Establish branch truth before doing work

Never treat memory, a previous chat, an open pull request, release notes, or this file's examples as proof
of what the current checkout implements.

Before substantial work:

1. Inspect the current branch, HEAD, working tree, and recent commits when tools permit.
2. Read `README.md`, `docs/README.md`, and the source/tests relevant to the task.
3. Read `pyproject.toml` before assuming Python versions, dependencies, scripts, or lint settings.
4. If the task mentions a PR, inspect its base/head and changed files. An open or draft PR is not `main`.
5. Prefer source code and tests on the checked-out branch over documentation when they disagree; then fix
   stale documentation as part of the task when appropriate.
6. State uncertainty instead of inventing functionality.

`main` is development truth. A tagged release is release truth. They can differ.

## 2. Project contract: a read-only Morningstar Modbus boundary

MorningstarModbusAPI discovers Morningstar controllers/inverters/accessories, resolves product identity,
reads and decodes telemetry, persists observations, exposes HTTP APIs, and supports evidence-driven
capture/replay and catalog maintenance.

The runtime is deliberately **read only**.

Allowed protocol operations under the current project contract are the reads already implemented for:

- holding registers (`0x03`);
- input registers (`0x04`);
- Read Device Identification (`0x2B / 0x0E`).

Do **not** add Modbus write-register, write-coil, reset, equalize-trigger, EEPROM mutation, configuration,
or remote-control paths. Vendor documentation containing writable addresses is evidence for understanding a
device, not permission to expose those operations. Do not weaken this boundary indirectly through a generic
"raw command" API.

## 3. Architecture and ownership boundaries

Use the package boundaries instead of putting product-specific behavior everywhere.

```text
physical Morningstar device
        |
        v
transport / protocol
        |
        v
discovery -----------------------> capture observer
        |                                |
        v                                v
catalog profile selection          capture bundle
        |                                |
        v                                v
firmware-aware intelligence <------ strict replay
        |
        v
watcher + in-memory lifecycle
        |
        v
SQLite/WAL raw observations
        |
        +------> current/latest views
        |
        +------> history/query/aggregation/export
        |
        v
FastAPI /v1

vendor source index -> maintenance scanner -> advisory report -> reviewed catalog/provenance change
```

Primary ownership:

- `transport.py`, `protocol.py`: Modbus RTU/TCP reads and protocol framing/parsing.
- `discovery.py`: serial/TCP discovery and candidate identification.
- `catalog/`: declarative vendor-derived product/register truth plus independent verification registry.
- `intelligence/`: runtime identity, firmware compatibility, confidence, capabilities, validation.
- `capture.py`, `replay.py`, `verification.py`: evidence capture, strict replay, verification reports.
- `lifecycle.py`, `watcher.py`: continuous polling, reconnect, retry/backoff, endpoint changes.
- `storage.py`, `history.py`: append-oriented persistence, history queries, statistics/aggregation/export.
- `api.py`: HTTP presentation and validation, not product knowledge.
- `maintenance/`: offline official-source scanning, comparison, reporting, provenance support.
- `cli.py`: command-line orchestration over the same production layers.

A new product family belongs in the catalog. A new transport behavior belongs in transport/protocol. Do not
solve a catalog problem with device-name conditionals in API or transport code.

## 4. Skill router

For non-trivial work, read the matching skill before editing. Skills are canonical under `.agents/skills/`.
Load more than one when a task crosses boundaries.

| Task | Skill |
| --- | --- |
| Orient to repo/branch or unfamiliar subsystem | `.agents/skills/project-orientation/SKILL.md` |
| Modbus transport, discovery, polling, protocol | `.agents/skills/read-only-modbus-development/SKILL.md` |
| Product maps, scaling, firmware gates, identity | `.agents/skills/catalog-and-intelligence/SKILL.md` |
| Capture, verify, replay, fixture/evidence work | `.agents/skills/hardware-verification-replay/SKILL.md` |
| USB/TCP reconnect, retry, endpoint lifecycle | `.agents/skills/device-lifecycle-reconnect/SKILL.md` |
| SQLite, telemetry history, aggregation/export | `.agents/skills/telemetry-history-storage/SKILL.md` |
| FastAPI endpoints and response behavior | `.agents/skills/api-development/SKILL.md` |
| Vendor PDFs, scanner, catalog proposals | `.agents/skills/catalog-maintenance-provenance/SKILL.md` |
| Tests, Ruff, CI, regression strategy | `.agents/skills/testing-and-ci/SKILL.md` |
| Docs, versions, releases | `.agents/skills/documentation-and-release/SKILL.md` |
| PR review, CI/reviews, integration/merge | `.agents/skills/pr-review-and-integration/SKILL.md` |

Every implementation task should also use `testing-and-ci` before it is considered complete.

## 5. Normal implementation workflow

Unless the task is genuinely tiny:

1. Orient to branch truth and identify the owning subsystem.
2. Read the relevant skill(s), source, tests, and docs.
3. Define the smallest coherent change that preserves project invariants.
4. Implement in the owning layer; avoid parallel implementations of the same logic.
5. Add or update deterministic tests for behavior and regression cases.
6. Run the narrowest useful tests while iterating.
7. Run `ruff check .` and `pytest -q` before claiming repository-wide success.
8. Reconcile docs/config/examples when public behavior changes.
9. Review the final diff for scope creep, unsafe writes, stale names, debug files, generated artifacts, secrets,
   and accidental evidence claims.
10. When publishing through GitHub, use a focused branch/PR and verify CI/review state against the exact head.

Do not say checks passed unless they were actually run or verified in CI.

## 6. Python engineering expectations

This is Python 3.12+; verify `pyproject.toml` for the exact current policy.

- Prefer typed, small, composable functions and explicit data models.
- Keep async code non-blocking. Native TCP uses asyncio; blocking serial operations belong behind the
  existing dedicated executor boundary.
- Do not call blocking file/network/device operations directly from the event loop when an asynchronous or
  executor-backed path exists.
- Keep locks narrowly scoped and never hold a lock across unrelated slow work.
- Prefer bounded concurrency for scanning/discovery; do not create unbounded task storms.
- Preserve cancellation and cleanup semantics. Failed or stale clients must be closed.
- Use structured exceptions and useful context; do not catch broad exceptions merely to hide failures.
- Avoid global mutable runtime state when ownership can live in watcher/storage/service objects.
- Follow Ruff rules (`E`, `F`, `I`, `UP`, `B`, `ASYNC`) and the configured line length.
- Keep public behavior backward compatible unless the change intentionally includes a documented migration.

## 7. Catalog and intelligence invariants

The catalog is declarative vendor/product truth. Runtime intelligence is evidence about a connected device.
Do not blur the two.

- `RegisterSpec` may span multiple words; reason about the full word range, not only the starting address.
- `RegisterBlock` defines what is safely read; named registers define semantic decoding within those reads.
- Preserve holding-vs-input function distinction and firmware `since_firmware` / `until_firmware` gates.
- Use central scaling/decoder helpers instead of ad-hoc conversions in API/watcher code.
- Unknown/new firmware should remain conservative (`newer-firmware-unverified` or equivalent current model),
  not silently promoted to verified.
- Plausibility validation is profile-confidence evidence, not an excuse to discard raw telemetry.
- Product aliases/fingerprints must be conservative. Prefer generic read-only behavior over a false identity.
- Vendor-derived catalog edits require official-source provenance and tests; see the maintenance skill.
- Catalog verification evidence is independent of the vendor-derived family module.

## 8. Evidence, capture, and replay

Evidence levels are deliberately separate:

1. vendor-documented;
2. software-tested;
3. fixture-verified;
4. physical-device-verified.

Never promote one level merely because a lower level passed. A synthetic/spec-derived fixture is not physical
hardware evidence.

Capture/replay rules:

- Capture the same production read path; do not build a second protocol implementation just for fixtures.
- `transactions.jsonl` is transport evidence; decoded/raw register values belong in `registers.json`.
- Replay is strict about function/address/count/order and should fail loudly on mismatch.
- Structured identifiers are redacted by default. Raw frames can still contain identifying data and require
  review before publication.
- Do not commit captures from real hardware without reviewing identifiers and evidence metadata.

## 9. Device lifecycle and reconnect behavior

The detailed lifecycle is owned by watcher/lifecycle and is currently an in-memory operational model unless
the checked-out branch explicitly changes that.

Expected behavior includes:

- discovery refreshes presence and endpoint identity;
- endpoint changes close stale clients before reconnect;
- absent devices are not polled through stale endpoints;
- failures move through degraded/offline according to configured thresholds;
- retries use bounded exponential backoff;
- successful recovery resets failure/backoff state;
- persistence/API may expose a simpler storage status than the in-memory lifecycle.

Do not conflate lifecycle state with persisted device status unless the task intentionally designs that
migration and its API/storage contract.

## 10. Telemetry, storage, and history rules

Raw observations are the source of truth.

- Use SQLite WAL and existing `aiosqlite` access patterns.
- Prefer additive, idempotent schema evolution (`CREATE ... IF NOT EXISTS`, additive indexes/tables) unless a
  migration system is deliberately introduced.
- Do not rewrite, prune, or irreversibly downsample raw history as a side effect of adding summaries.
- Time ranges use the semantics implemented by `history.py`/tests; inspect them before changing API behavior.
- Numeric and text/state series require different aggregation/statistics semantics.
- Large history exports should stream rather than building unbounded responses in memory.
- Respect current query limits and use exports/coarser resolution for large datasets.
- Power and energy are different quantities; do not label instantaneous watts as watt-hours without integrating
  over time using defensible sampling semantics.

## 11. API rules

`api.py` and its tests are the branch truth for endpoint shape. README tables can lag during active development.

- Keep `/v1` behavior backward compatible where possible.
- Validate time ranges, resolution, limits, and device/register identifiers at the boundary.
- Preserve device IDs containing `/` where the current path/query design supports them.
- Do not expose product-specific conditional logic from FastAPI routes.
- Do not expose Modbus writes or generic write-capable protocol passthrough.
- Stream large exports.
- Use explicit HTTP error semantics and test them.
- If exposing in-memory runtime-only state, design ownership/thread-safety/lifetime instead of pretending it is
  already persisted.

## 12. Vendor-source maintenance and provenance

`docs/vendor/morningstar/sources.json` is the authoritative approved source index.

- Automated source retrieval is limited to approved HTTPS Morningstar sources.
- Complete vendor PDFs are source material and are not republished in this repository.
- The maintenance scanner is advisory and never automatically rewrites catalog family modules.
- Its parser distinguishes runtime tables from configuration/control/log/example/reserved/alternate-encoding
  material; do not regress to "every hexadecimal token is a register".
- Distinguish actionable conflicts from optional coverage candidates.
- A reviewed vendor-derived catalog/source-index change needs an appropriate `catalog-proposals/*.json` record
  bound to the exact source SHA-256 plus tests.

## 13. Testing and CI

Default local validation:

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

Use targeted tests first when iterating. Full CI currently validates the supported Python matrix defined in
`.github/workflows/ci.yml`; inspect that workflow rather than hard-coding an assumed matrix into automation.

Tests should be deterministic and normally must not require Internet access or physical Morningstar hardware.
Use replay fixtures for protocol-level behavior and mocks/fakes only when replay is not the right abstraction.

A real-hardware capture can provide evidence, but unit/CI tests must remain runnable without that device.

## 14. Documentation and release discipline

When public behavior changes, reconcile the relevant docs in the same change. Start from `docs/README.md`.

Distinguish:

- current branch behavior;
- latest published release behavior;
- work proposed by an open/draft PR.

Do not describe an unmerged branch as released functionality.

Before a release, inspect the package version locations and `.github/workflows/release.yml`. The release workflow
uses `release/vMAJOR.MINOR.PATCH` branch naming and validates the branch version against project metadata.
Never bump/release merely because documentation suggests a version.

## 15. GitHub and PR discipline

- Do not modify an unrelated open PR branch unless the user asked to continue that PR.
- Prefer one coherent feature/fix branch per task.
- Before merge, inspect changed files, PR base/head, unresolved review threads, and CI on the exact current head.
- Do not merge a draft unless the user intentionally wants it promoted/merged.
- Use expected-head protection when the integration tool supports it.
- Never hide failing checks by deleting tests, disabling lint, or weakening assertions without a justified behavior
  change.

## 16. Project anti-patterns

Do not:

- add write-capable Modbus functionality under the current contract;
- copy register maps into API/watcher conditionals;
- treat every vendor hex address as runtime telemetry;
- claim synthetic evidence is physical-device verification;
- discard raw telemetry because decoding looks implausible;
- poll stale endpoints indefinitely after disconnect;
- block the asyncio event loop with serial/file/network work;
- create a second telemetry store for a query/reporting feature when the existing history is authoritative;
- build large JSON history responses when streaming/aggregation is appropriate;
- commit vendor manuals, secrets, local databases, caches, or unsanitized hardware captures;
- document an open PR as though it were on `main`;
- claim test/CI success without evidence.

## 17. Definition of done

A change is done when the implementation lives in the correct layer, preserves the read-only/evidence/data
contracts, has regression coverage, passes the relevant validation, has accurate public docs/configuration,
and the final diff contains no unrelated or generated debris.

When unsure which workflow applies, start with `.agents/skills/project-orientation/SKILL.md` and route from there.
