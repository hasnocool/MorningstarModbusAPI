---
name: telemetry-history-storage
description: Work on SQLite/WAL telemetry persistence, controller-scoped history, retained-history providers, unified events, system history provenance, aggregation, and exports without losing raw evidence.
---

# Telemetry, history, storage, and events

Primary ownership: `persistence/` and `history/`, with `systems/` consuming those read models.

## Invariants

- Raw poll observations remain authoritative and append-oriented.
- Controller-scoped history spans all historical device IDs and preserves `source_device_id`.
- Use existing `aiosqlite`/WAL patterns and additive/idempotent schema changes unless a migration framework is
  intentionally introduced.
- Numeric and state/text data require different statistics/aggregation.
- Large exports should stream or aggregate within bounded limits.
- Power (W) and energy (Wh/kWh) are different quantities.

## Retained history

Retained history is provider-based. Preserve the provider registry abstraction and source-specific behavior.
Do not assume GenStar, TriStar LiveView, ReadyEdge, or future products share the same on-device history protocol.
If the vendor source does not document replay/index semantics, leave the provider unsupported rather than guess.

## Events

Unified events can include inbound event records, communication errors, charge/fault/alarm transitions, and
history-sync outcomes. Preserve controller/source/timestamp/severity/payload provenance and bound queries.

## System history

When aggregating controllers, retain source observations, contributor counts, expected contributors, freshness,
and metric-specific aggregation semantics. Do not rewrite raw rows to make site-level history easier.
