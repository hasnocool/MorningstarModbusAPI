# MorningstarModbusAPI agent control tower

This file is the canonical always-on project instruction set for coding agents. It is shared across
ChatGPT/Codex, GitHub Copilot, OpenCode, Pi, OMP/oh-my-pi, Claude Code, and OpenClaude adapters.
Task-specific procedures live under `.agents/skills/`; load only the relevant skills for the task.

## 1. Establish branch truth before doing work

Never treat memory, a previous chat, an open pull request, release notes, or this file's examples as proof of
what the current checkout implements.

Before substantial work:

1. Inspect the current branch, HEAD, working tree, recent commits, and open PR base/head when tools permit.
2. Read `README.md`, `docs/README.md`, `docs/package-layout.md`, and source/tests relevant to the task.
3. Read `pyproject.toml` before assuming Python versions, dependencies, scripts, or Ruff configuration.
4. Prefer source and tests on the checked-out branch over prose when they disagree, then repair stale docs.
5. Distinguish `main`, a feature branch, and a published tag. Do not describe branch-only behavior as released.
6. State uncertainty rather than inventing capabilities, register semantics, topology, measurements, or evidence.

## 2. Project contract: read-only Morningstar observability

MorningstarModbusAPI is a read-only Morningstar device discovery, telemetry, persistence, history, system/site,
event, topology, component-model, and HTTP API service. It also supports evidence-driven capture/replay and
official-source catalog maintenance.

The runtime is deliberately **read only**. Allowed protocol operations are the reads already implemented for
holding registers, input registers, and Read Device Identification. Do **not** add Modbus register writes, coil
writes, EEPROM/configuration mutation, reset/equalize triggers, generator control, SNMP SET, or a generic
write-capable passthrough. Vendor documentation containing writable fields is evidence, not permission to expose
control operations.

## 3. Current capability model

Treat these as architectural concepts that must be verified against the checked-out branch before use.

### Physical controllers and discovery

- Serial and Modbus/TCP discovery feed immutable physical-controller identities.
- `controller_uid` is the stable internal identity. Human/vendor-derived controller IDs and endpoint IDs may
  change as stronger evidence appears; aliases preserve continuity.
- One physical controller can accumulate multiple historical device IDs/endpoints without splitting history.
- Reconnect logic must tolerate USB path/identity changes and TCP endpoint changes without creating duplicate
  controllers when identity evidence supports continuity.

### Catalog, intelligence, and product coverage

- `catalog/` is declarative vendor-derived product/register truth.
- `intelligence/` is runtime identity/capability/confidence evidence for a connected device.
- Multi-word decoders, firmware gates, reserved ranges, and function type are first-class catalog semantics.
- GenStar coverage includes source-backed logger summaries and charge-energy/Ah counters; do not invent an
  undocumented retained-event-log replay protocol.
- ReadyEdge coverage can expose its documented Connected Product inventory. The current source-backed design
  models 16 slots with product type, serial, physical bus, and Modbus address descriptors. Connected Products
  reported by ReadyEdge must be reconciled to an already discovered physical controller by strong evidence such
  as serial number before creating a separate reported-only component.

### Persistence, telemetry, history, and events

- SQLite/WAL raw observations remain authoritative and append-oriented.
- Controller-scoped reads aggregate all historical device IDs while preserving `source_device_id` provenance.
- Retained-history ingestion is provider-based; the existing TriStar LiveView behavior is a provider, not a
  reason to hard-code all future products to the same format.
- Unified events may combine persisted external/inbound events, communication errors, state transitions, and
  retained-history synchronization outcomes while preserving source/controller provenance.
- Optional inbound SNMP trap ingestion remains read-only. Do not assume every product emits traps; distinguish
  trap-capable products from products that only support SNMP polling.

### System/site aggregation

- `systems/` sits above physical controllers and must not replace or mutate controller identity.
- A system/site groups controllers and exposes normalized cross-product metrics with explicit aggregation rules.
- Aggregate quality distinguishes complete, partial, and empty observations and records expected contributors,
  actual contributors, source observations, and freshness.
- System history must preserve per-controller/source provenance and use metric-specific aggregation semantics.
- Transport topology and electrical/component topology are related but distinct views.
- Shared TCP endpoint/multi-unit observations may support an **inferred** bridge candidate; they are not proof of
  physical wiring.
- The unified system event timeline and Server-Sent Events stream are read-only presentation surfaces.

### Component graph and power/energy model

- The component graph represents the logical system, physical controllers, electrical aggregation points such as
  the battery bus, ReadyEdge-reported Connected Products, and evidence-backed relationships.
- Physical controller components keep `controller_uid` as identity. Never duplicate a controller just because a
  bridge or ReadyEdge reports it through another path.
- Relationships must retain evidence and confidence. Do not convert a transport observation into a physical
  electrical connection without source-backed evidence.
- Power flow distinguishes **observed**, **derived**, and **unknown** values. Unknown is a valid result.
- It is acceptable to derive a controller conversion residual/efficiency when both input and output power are
  known and temporally compatible. It is not acceptable to invent generator power, aggregate load power,
  battery net power/current, discharge energy, or whole-system balance from incomplete measurements.
- Charger current is **not** battery net current when loads can be active on the same battery bus.
- Prefer a reconciled/validated operational measurement over a known lower-quality raw estimate when system
  semantics explicitly define that priority; preserve source provenance so the choice is auditable.
- The energy ledger is an accounting/read model over available measurements and defensible derivations. It must
  not silently close the energy balance by manufacturing a residual as though it were measured.

## 4. Current package ownership

The v0.5+ runtime uses domain packages. Do not reintroduce the removed pre-release flat-module layout.

```text
src/morningstar_modbus/
├── api/            # FastAPI app + controller/system routers
├── capture/        # capture/replay/verification support
├── catalog/        # declarative product/register truth
├── cli/            # command-line orchestration
├── config/         # typed configuration
├── controllers/    # immutable controller UID, inventory, scope, lifecycle
├── discovery/      # serial/TCP discovery
├── domain/         # shared immutable models
├── history/        # controller history/query + retained-history providers
├── intelligence/   # runtime identity/capability/confidence
├── maintenance/    # vendor-source scanning/provenance tooling
├── persistence/    # SQLite/WAL store + persisted events
├── polling/        # poll cadence/performance/benchmarking
├── protocol/       # read-only Modbus framing/codec/errors
├── runtime/        # long-running watcher/composition
├── snmp/           # optional inbound trap ingestion
├── systems/        # site aggregation, semantics, components, power
└── transports/     # RTU/TCP I/O
```

Typical ownership rules:

- `transports/` + `protocol/`: Modbus I/O/framing only.
- `discovery/`, `controllers/`, `runtime/`: discovery, stable physical identity, lifecycle/reconnect/orchestration.
- `catalog/` + `intelligence/`: product knowledge and runtime evidence.
- `persistence/` + `history/`: raw storage, controller-scoped history, retained-history ingestion/query.
- `systems/`: cross-controller semantics, site views, topology/component relationships, power/energy read models.
- `api/routers/`: HTTP validation/presentation of owning services; not product-specific knowledge.
- `capture/`: evidence bundles/replay/verification.
- `maintenance/`: official-source retrieval, comparison, catalog provenance validation.

A new product family belongs in `catalog/`. A new cross-controller metric belongs in `systems/semantics.py`. A
component relationship or power accounting rule belongs in `systems/`, not in FastAPI route conditionals.

## 5. Skill router

For non-trivial work, read the matching skill before editing. Load more than one when a task crosses boundaries.

| Task | Skill |
| --- | --- |
| Orient to repo/branch or unfamiliar subsystem | `.agents/skills/project-orientation/SKILL.md` |
| Modbus transport, discovery, polling, protocol | `.agents/skills/read-only-modbus-development/SKILL.md` |
| Product maps, scaling, firmware gates, identity | `.agents/skills/catalog-and-intelligence/SKILL.md` |
| Capture, verify, replay, fixture/evidence work | `.agents/skills/hardware-verification-replay/SKILL.md` |
| USB/TCP reconnect, controller identity, retry lifecycle | `.agents/skills/device-lifecycle-reconnect/SKILL.md` |
| SQLite, telemetry/history, retained history, events | `.agents/skills/telemetry-history-storage/SKILL.md` |
| System/site metrics, topology, components, power/energy | `.agents/skills/system-topology-and-power/SKILL.md` |
| FastAPI endpoints, SSE, response/error behavior | `.agents/skills/api-development/SKILL.md` |
| Vendor PDFs, scanner, catalog proposals | `.agents/skills/catalog-maintenance-provenance/SKILL.md` |
| Tests, Ruff, CI, regression strategy | `.agents/skills/testing-and-ci/SKILL.md` |
| Docs, versions, releases | `.agents/skills/documentation-and-release/SKILL.md` |
| PR review, CI/reviews, stacked integration/merge | `.agents/skills/pr-review-and-integration/SKILL.md` |

Every implementation task should also use `testing-and-ci` before it is considered complete.

## 6. Normal implementation workflow

Unless the task is genuinely tiny:

1. Establish branch truth and identify the owning domain package(s).
2. Read relevant skills, source, tests, and public docs.
3. Define the smallest coherent change that preserves read-only, identity, evidence, and raw-data invariants.
4. Implement in the owning layer; avoid parallel implementations of the same logic.
5. Add deterministic regression tests, including provenance/quality/unknown-state cases where relevant.
6. Run targeted tests while iterating.
7. Run `ruff check .` and `pytest -q` before claiming repository-wide success.
8. Reconcile public docs/config/examples when behavior changes.
9. Review the final diff for unsafe writes, stale flat imports, duplicate identities, fabricated measurements,
   debug files, generated artifacts, secrets, unsanitized captures, and accidental evidence claims.
10. For GitHub publishing, verify PR base/head, changed files, review threads, and CI against the exact head.

Do not say checks passed unless they actually ran or were verified on the relevant head.

## 7. Python engineering expectations

This project requires Python 3.12+; inspect `pyproject.toml` and CI for the exact current policy.

- Prefer typed, small, composable functions and explicit immutable/domain models where appropriate.
- Keep async code non-blocking. Blocking serial work belongs behind the established executor boundary.
- Do not perform blocking file/network/device work directly in the event loop when an async/executor path exists.
- Keep locks narrowly scoped; do not hold a lock across unrelated slow work.
- Use bounded concurrency for discovery/scanning and preserve cancellation/cleanup semantics.
- Failed or stale clients must be closed.
- Avoid broad exception swallowing and global mutable runtime state.
- Follow configured Ruff rules and line length.
- Use canonical package imports only; do not recreate removed flat aliases for convenience.

## 8. Controller identity and lifecycle invariants

- `controller_uid` is immutable after assignment.
- Endpoint IDs, device IDs, or vendor-derived aliases are not substitutes for physical identity.
- Identity promotion must retain old aliases/history rather than split a controller.
- System membership and component relationships reference the physical controller; they do not own identity.
- Reconnect must close stale clients, rediscover endpoints, use bounded backoff, and reset failure state on success.
- Do not conflate in-memory lifecycle state with persisted status unless intentionally designing that contract.

## 9. Catalog and intelligence invariants

- `RegisterSpec` may span multiple words; reason about full word ranges.
- `RegisterBlock` defines safely readable regions; reserved ranges remain reserved evidence, not unnamed features.
- Preserve holding-vs-input distinction and firmware gates.
- Use central decoders/scaling helpers instead of ad-hoc conversions in routes/runtime.
- Unknown firmware remains conservative rather than silently verified.
- Product aliases/fingerprints must be conservative; generic read-only behavior is safer than false identity.
- ReadyEdge Connected Product descriptors are inventory/relationship evidence; product-type labels do not by
  themselves prove that a separately discovered physical controller is the same device.
- Vendor-derived catalog edits require official-source provenance and tests.

## 10. Telemetry, retained history, storage, and event rules

- Raw observations are source truth. Do not destructively rewrite or downsample them as a reporting side effect.
- Use existing SQLite WAL/`aiosqlite` patterns and additive/idempotent schema evolution unless a migration system
  is intentionally introduced.
- Preserve `source_device_id`/controller provenance on controller and system history.
- Numeric and text/state series require different aggregation/statistics semantics.
- Large history exports should stream or use bounded aggregation rather than build unbounded JSON.
- Retained-history providers must be source-specific and must not invent undocumented retrieval protocols.
- Unified events must preserve event source, controller assignment, timestamp, severity, and payload provenance.
- Power and energy are different dimensions; watts are not watt-hours without defensible integration/counters.

## 11. System/site, topology, component, and power rules

- Cross-product semantics live in `systems/semantics.py`, not vendor family files or API routes.
- Aggregation strategy is metric-specific: sums, medians, maxima, and state sets are not interchangeable.
- Quality must account for expected contributors and stale/missing observations.
- Transport topology is observational. Mark inference confidence explicitly.
- Component relationships are evidence-backed and should retain source details such as ReadyEdge host/slot,
  serial, physical bus, and Modbus address when available.
- Reconcile bridge-reported products with physical controllers before adding reported-only components.
- Keep logical battery/system nodes distinct from physical controller nodes.
- Power-flow and energy-ledger outputs must label values as observed, derived, or unknown.
- Never infer battery net current from charger output current alone.
- Never infer load or generator power merely to make a balance equation close.
- Derived efficiency/residual calculations require compatible input/output observations and must preserve inputs.

## 12. API rules

The API package and tests are branch truth for endpoint shape. Representative system routes include normalized
latest/history/energy/health, topology, events, SSE streaming, component graph, relationships, power flow, and
energy ledger. Inspect the actual router before changing a contract.

- Keep `/v1` behavior backward compatible unless an intentional migration is documented/tested.
- Validate time ranges, resolution, limits, identifiers, and query parameters at the boundary.
- Preserve IDs containing `/` where the existing API supports them.
- Keep product-specific decoding and system accounting out of route functions.
- SSE endpoints must remain non-blocking, disconnect-aware, and bounded.
- Use explicit HTTP error semantics and regression tests.
- Do not expose write-capable protocol operations through convenience endpoints.

## 13. Evidence, capture, replay, and verification

Keep evidence levels separate:

1. vendor-documented;
2. software-tested;
3. fixture/replay-verified;
4. physical-device-verified.

Never promote a higher evidence level merely because a lower level passed.

- Capture the production read path; do not build a second protocol implementation only for fixtures.
- Replay remains strict about function/address/count/order.
- Structured identifiers are redacted by default; raw frames may still contain identifying data and require
  review before publication.
- Do not commit real-device captures without reviewing identifiers and evidence metadata.
- A topology/power inference that works in a synthetic fixture is not physical wiring verification.

## 14. Vendor-source maintenance and provenance

`docs/vendor/morningstar/sources.json` is the approved source index.

- Automated source retrieval is limited to approved Morningstar HTTPS sources.
- Complete vendor PDFs are source material and are not republished in the repository.
- The scanner is advisory and must not automatically rewrite catalog family modules.
- Distinguish runtime telemetry tables from configuration/control/log/example/reserved material.
- Catalog/source-index changes require a reviewed `catalog-proposals/*.json` record bound to the exact source
  SHA-256 plus tests.
- When source material is incomplete, record the limitation instead of guessing missing fields/protocols.

## 15. Testing and CI

Default validation:

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

Use targeted tests first. Inspect `.github/workflows/ci.yml` and catalog-maintenance workflows rather than
assuming a matrix. Tests should normally run without Internet or physical Morningstar hardware. Add tests for
identity continuity, source provenance, partial/unknown data, aggregation quality, and read-only safety when a
change touches those areas.

## 16. Documentation and release discipline

When public behavior changes, reconcile relevant docs in the same change. Start from `docs/README.md` and the
owning subsystem docs. Distinguish current branch behavior, `main`, and the latest published release. Do not
encode temporary PR numbers or commit SHAs into persistent agent instructions.

Before a release, inspect package version metadata and the actual release workflow. Do not bump/release merely
because prose suggests a version.

## 17. GitHub and PR discipline

- Do not modify an unrelated open PR branch unless explicitly asked.
- Prefer one coherent feature/fix branch per task.
- For stacked work, make the dependency explicit and target the dependency branch until it merges; avoid
  duplicating the dependency's diff into a separate `main` PR.
- Before merge, inspect PR base/head, changed files, unresolved review threads/reviews, and CI on the exact head.
- Use expected-head protection when supported.
- Never hide failing checks by deleting tests, disabling lint, or weakening assertions without a justified
  behavior change.

## 18. Project anti-patterns

Do not:

- add write-capable Modbus/SNMP/controller-control functionality;
- use removed flat module paths as architectural ownership;
- copy product register knowledge into API/runtime conditionals;
- confuse device/endpoint IDs with immutable physical `controller_uid`;
- duplicate a physical controller because it appears through ReadyEdge or a bridge;
- treat a shared TCP endpoint as proof of electrical topology;
- fabricate battery net current, load/generator power, discharge energy, or residual balance;
- claim synthetic evidence is physical verification;
- discard raw telemetry because a decoded value looks implausible;
- poll stale endpoints indefinitely after disconnect;
- block the event loop with device/file/network work;
- create a second authoritative telemetry store for reporting;
- commit vendor manuals, secrets, databases, caches, or unsanitized hardware captures;
- document an open PR as though it were merged/released;
- claim test/CI success without evidence.

## 19. Definition of done

A change is done when it lives in the owning layer, preserves the read-only/identity/evidence/raw-data contracts,
handles unknown/partial data honestly, has deterministic regression coverage, passes relevant validation,
reconciles public docs/configuration, and leaves no unrelated or generated debris in the final diff.

When unsure which workflow applies, start with `.agents/skills/project-orientation/SKILL.md` and route from there.
