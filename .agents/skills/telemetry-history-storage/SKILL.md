---
name: telemetry-history-storage
description: Work on SQLite/WAL persistence, raw telemetry retention, history time ranges, aggregation, statistics, summaries, exports, indexing, and safe additive schema evolution.
---

# Telemetry history and storage

Use for `storage.py`, `history.py`, database schema/indexes, telemetry queries, statistics/aggregation, exports, or
data-retention semantics.

Read `docs/telemetry-history.md` and existing storage/history tests before editing.

## Source-of-truth rule

Raw poll/register observations are authoritative evidence. Query/summary features should derive from them rather
than replacing them with lossy rollups.

Do not prune, rewrite, or irreversibly downsample raw history as an incidental optimization.

## SQLite conventions

- Preserve WAL mode and non-blocking `aiosqlite` access.
- Prefer additive/idempotent initialization (`CREATE TABLE/INDEX IF NOT EXISTS`) until the project deliberately
  introduces versioned migrations.
- Keep foreign-key relationships and device/sample ownership explicit.
- Add indexes based on real query shapes rather than indexing every column.
- Avoid loading unbounded histories into Python when SQL filtering/aggregation/streaming can do the work.
- Maintain compatibility with existing databases wherever feasible.

## Time semantics

Inspect current parser/tests, but established API history semantics include normalized UTC timestamps and
half-open ranges: inclusive start, exclusive end. Keep one consistent convention across storage/API/export.

Reject invalid ranges explicitly rather than silently swapping them.

## Resolution and aggregation

Current history supports raw and bucketed resolutions on the development line. Preserve different semantics for:

- numeric values — count/min/max/avg/first/last as applicable;
- text/state values — count/first/last/transition count/state observations, not meaningless numeric averages.

Keep bucket boundaries deterministic and timezone-independent.

## Statistics

When adding stats, include enough provenance to interpret them: observation count/duration, first/last, extrema
and timestamps where applicable. Treat gaps honestly; an average over sampled observations is not automatically a
time-weighted physical average.

## Power versus energy

Instantaneous `W` samples are power. `Wh`/`kWh` requires integration over time. If deriving energy:

- define interpolation/integration method;
- define gap handling/max gap;
- use timestamps, not sample count alone;
- expose assumptions/coverage;
- test irregular sampling.

Never relabel power as energy.

## Query guardrails

Respect branch-defined point/register limits for normal JSON responses. Large requests should be handled by:

- narrower time windows;
- coarser resolution;
- streaming CSV/JSONL export.

Do not simply increase limits until the server can exhaust memory.

## Export

Streaming exports should:

- iterate/stream rather than build the whole file in memory;
- preserve stable field ordering/schema;
- support filters consistently with JSON history;
- correctly quote/encode CSV and line-delimit JSONL;
- distinguish raw from aggregated rows.

## Safe migrations

For schema additions:

1. test opening an existing-style DB;
2. create new table/index/column path safely;
3. avoid rewriting historical rows unless required;
4. test fresh and migrated initialization;
5. document operational impact.

## Validation

Run storage/history tests, API tests for affected query surfaces, then `testing-and-ci`.
