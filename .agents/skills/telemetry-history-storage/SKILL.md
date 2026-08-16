---
name: telemetry-history-storage
description: Work on SQLite/WAL persistence, raw telemetry retention, controller-scoped history, retained-history providers, unified events, system-history provenance, aggregation, statistics, exports, and additive schema evolution.
---

# Telemetry history and storage

Use for `persistence/`, `history/`, database schema/indexes, telemetry queries, retained-history providers, unified
events, statistics/aggregation, exports, or data-retention semantics.

Read `docs/telemetry-history.md`, system API docs when relevant, and existing storage/history tests before editing.

## Source-of-truth rule

Raw poll/register observations are authoritative evidence. Query/summary/system features derive from them rather
than replacing them with lossy rollups.

Do not prune, rewrite, or irreversibly downsample raw history as an incidental optimization.

## Controller-scoped history

A physical controller may own multiple historical device IDs. Controller-scoped reads must:

- resolve immutable `controller_uid` to all scoped device IDs;
- preserve `source_device_id` on raw observations;
- avoid splitting history when an endpoint/device alias changes;
- use canonical controller identity in API/system aggregation.

## SQLite conventions

- Preserve WAL mode and non-blocking `aiosqlite` access.
- Prefer additive/idempotent initialization (`CREATE TABLE/INDEX IF NOT EXISTS`) until versioned migrations are
  deliberately introduced.
- Keep foreign-key relationships and sample/device/controller ownership explicit.
- Add indexes based on real query shapes rather than every column.
- Avoid loading unbounded histories into Python when SQL filtering/aggregation/streaming can do the work.
- Maintain compatibility with existing databases where feasible.

## Time semantics

Inspect current parser/tests. Keep UTC normalization and the established inclusive-start/exclusive-end convention
consistent across history/API/export. Reject invalid ranges explicitly.

## Resolution and aggregation

Preserve different semantics for:

- numeric values — count/min/max/avg/first/last as applicable;
- text/state values — count/first/last/transitions/state observations, not meaningless numeric averages.

Keep bucket boundaries deterministic and timezone-independent.

For system history, apply metric-specific cross-controller aggregation after preserving per-controller source
observations. Include expected contributors, actual contributors, quality, and freshness where the system model
requires them.

## Statistics and gaps

Include enough provenance to interpret statistics: observation count/duration, first/last, extrema/timestamps.
Treat gaps honestly; an average over samples is not automatically a time-weighted physical average.

## Retained history

Retained history is provider-based. Preserve the provider registry and source-specific behavior. Existing TriStar
LiveView support does not imply that GenStar, ReadyEdge, or future products share its retained-history protocol.
If source material does not document an index/read mechanism, leave that provider unsupported instead of guessing.

## Unified events

Persisted/inbound events, communication errors, state transitions, and retained-history sync outcomes can feed a
system timeline. Preserve:

- controller assignment when known;
- source/source-host;
- observed timestamp;
- severity/event type;
- payload/provenance;
- bounded query behavior.

Do not turn state transitions into destructive rewrites of telemetry history.

## Power versus energy

Instantaneous `W` is power. `Wh`/`kWh` requires a source-backed counter or defensible integration. If deriving
energy from samples:

- define interpolation/integration method;
- define gap handling/max gap;
- use timestamps rather than sample count;
- expose assumptions/coverage;
- test irregular sampling.

The system energy ledger must preserve whether a value is observed, derived, or unknown. Never relabel charger
current as battery net current or manufacture missing load/generator energy.

## Query guardrails and export

Respect branch-defined point/register limits. For large requests use narrower windows, coarser resolution, or
streaming CSV/JSONL. Streaming exports should preserve stable schema, filters, quoting/encoding, and raw versus
aggregated distinction without building the entire response in memory.

## Safe migrations

For schema additions:

1. test an existing-style DB;
2. create new table/index/column safely;
3. avoid rewriting history unless required;
4. test fresh and migrated initialization;
5. document operational impact.

## Validation

Run persistence/history/event tests, controller-scope tests, affected system/API tests, then `testing-and-ci`.
