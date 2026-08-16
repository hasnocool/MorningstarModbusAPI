# Storage v2: compressed time-series retention

Storage v2 bounds the growth of the live SQLite database without changing the existing read-only telemetry API.
Raw observations remain authoritative: archival is lossless and raw SQLite rows are only eligible for deletion
after the corresponding Parquet file is written and verified with SHA-256.

## Architecture

The live database remains SQLite/WAL. Storage v2 adds four complementary layers:

1. **Integer time indexes** — existing ISO-8601 timestamps are retained for API compatibility, while additive
   `observed_at_ms` columns and triggers remove repeated `strftime()` work from storage maintenance.
2. **Register dictionary** — repeated register metadata is normalized into an integer-key dictionary for compact
   rollups and state runs.
3. **Multi-resolution rollups** — numeric series preserve count/min/max/avg/first/last; text series preserve
   first/last and transition counts. State registers additionally receive change-run encoding.
4. **Cold archive** — raw sample/register rows are streamed into daily Parquet partitions using Zstd compression,
   dictionary encoding, statistics, bounded batches, atomic rename, and SHA-256 verification.

The archive layout is deterministic:

```text
morningstar-archive/
  2026/
    08/
      telemetry-2026-08-16.parquet
```

## Default retention policy

| Tier | Age | Representation |
| --- | ---: | --- |
| hot | 0–7 days | raw SQLite at acquisition cadence |
| warm | >7 days | 10-second rollups + lossless Parquet |
| cool | >30 days | 1-minute rollups + lossless Parquet |
| cold | >180 days | 5-minute rollups + lossless Parquet |

Raw archive files remain lossless. Rollups are an analytics/query acceleration layer, not the sole source of truth.

## Installation and commands

Parquet archival is an optional dependency because PyArrow is large:

```bash
python -m pip install -e '.[storage]'
morningstar-storage --config config.toml initialize
morningstar-storage --config config.toml status
morningstar-storage --config config.toml maintain
```

Use `maintain --no-prune` to build/verify archives while intentionally retaining all raw SQLite rows.

`maintain` performs these operations in order:

1. additive/idempotent schema initialization;
2. integer timestamp backfill and indexes;
3. register dictionary refresh;
4. warm/cool/cold rollup rebuilds;
5. text/state run compression;
6. daily Zstd/Parquet archival in bounded batches;
7. optional deletion of only verified archived raw ranges;
8. WAL truncate checkpoint;
9. incremental vacuum and `PRAGMA optimize`;
10. total storage accounting.

The maintenance path is asynchronous. SQLite work uses `aiosqlite`; filesystem hashing, directory creation,
Parquet batch writes, close operations, and atomic file replacement are moved off the event loop.

## Size accounting

`morningstar-storage status` reports the main database, WAL, shared-memory file, verified archive bytes, SQLite
page bytes, freelist/reclaimable bytes, and row counts for raw and compact stores. This avoids the old blind spot
where only `morningstar.db` was measured while `morningstar.db-wal` could contain substantial live data.

## Operational safety

- `prune_archived_raw=true` never authorizes unarchived deletion.
- A Parquet partition must pass SHA-256 verification before its range is marked verified.
- Foreign keys remain enabled during pruning so per-register rows cascade with their parent samples.
- WAL checkpointing happens after archival/pruning, not during capture.
- Incremental vacuum is used for routine maintenance; a full `VACUUM` is intentionally not run automatically.
- Existing ISO timestamps, raw JSON values, and current API query tables remain compatible for the hot window.

## Scheduling

Run maintenance periodically from systemd/cron or another supervisor. The default configuration records a
six-hour desired cadence (`maintenance_interval_seconds = 21600`) so a future runtime scheduler can use the same
policy; the current implementation keeps the potentially CPU-heavy archival job isolated from the live poll loop.
