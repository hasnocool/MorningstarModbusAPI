"""Storage v2: bounded hot SQLite plus compact rollups and Zstd/Parquet archives."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

_STORAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS storage_register_dictionary (
    register_key INTEGER PRIMARY KEY,
    register_name TEXT NOT NULL,
    address INTEGER NOT NULL,
    function TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    UNIQUE(register_name, address, function, unit)
);
CREATE TABLE IF NOT EXISTS storage_rollups (
    device_id TEXT NOT NULL,
    register_key INTEGER NOT NULL REFERENCES storage_register_dictionary(register_key),
    bucket_seconds INTEGER NOT NULL,
    bucket_start_ms INTEGER NOT NULL,
    kind INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    min_value REAL,
    max_value REAL,
    avg_value REAL,
    first_numeric REAL,
    last_numeric REAL,
    first_text TEXT,
    last_text TEXT,
    transitions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(device_id, register_key, bucket_seconds, bucket_start_ms)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_storage_rollups_device_time
    ON storage_rollups(device_id, bucket_seconds, bucket_start_ms DESC);
CREATE TABLE IF NOT EXISTS storage_state_runs (
    device_id TEXT NOT NULL,
    register_key INTEGER NOT NULL REFERENCES storage_register_dictionary(register_key),
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER NOT NULL,
    value TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY(device_id, register_key, started_at_ms)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_storage_state_runs_device_time
    ON storage_state_runs(device_id, started_at_ms DESC);
CREATE TABLE IF NOT EXISTS storage_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    path TEXT NOT NULL UNIQUE,
    row_count INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    codec TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_storage_archives_range
    ON storage_archives(start_ms, end_ms);
CREATE TABLE IF NOT EXISTS storage_maintenance_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at_ms INTEGER NOT NULL,
    finished_at_ms INTEGER,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
"""


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _cutoff_ms(days: int) -> int:
    return int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)


def _iso_to_ms(value: str) -> int:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class StorageReport:
    database_bytes: int
    wal_bytes: int
    shm_bytes: int
    archive_bytes: int
    page_bytes: int
    free_page_bytes: int
    reclaimable_percent: float
    poll_samples: int
    register_values: int
    rollups: int
    state_runs: int
    archives: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class StorageV2Manager:
    """Manage compression, rollups, archival, pruning, and SQLite housekeeping."""

    def __init__(self, database_path: str, archive_dir: str) -> None:
        self.database_path = str(Path(database_path).expanduser())
        self.archive_dir = Path(archive_dir).expanduser()

    async def initialize(self) -> None:
        await asyncio.to_thread(self.archive_dir.mkdir, parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            await db.executescript(_STORAGE_SCHEMA)
            await self._ensure_epoch_column(db, "poll_samples")
            await self._ensure_epoch_column(db, "poll_errors")
            if await self._table_exists(db, "poll_performance_samples"):
                await self._ensure_epoch_column(db, "poll_performance_samples")
            await db.commit()
        await self.refresh_register_dictionary()

    async def _ensure_epoch_column(self, db: aiosqlite.Connection, table: str) -> None:
        columns = await self._columns(db, table)
        if "observed_at_ms" not in columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN observed_at_ms INTEGER")
        await db.execute(
            f"""
            UPDATE {table}
            SET observed_at_ms = CAST((julianday(observed_at) - 2440587.5) * 86400000 AS INTEGER)
            WHERE observed_at_ms IS NULL
            """
        )
        await db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_epoch ON {table}(observed_at_ms DESC)"
        )
        trigger = f"storage_{table}_epoch_insert"
        await db.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {trigger}
            AFTER INSERT ON {table}
            WHEN NEW.observed_at_ms IS NULL
            BEGIN
                UPDATE {table}
                SET observed_at_ms = CAST((julianday(NEW.observed_at) - 2440587.5) * 86400000 AS INTEGER)
                WHERE rowid = NEW.rowid;
            END
            """
        )

    @staticmethod
    async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        return {str(row[1]) for row in await cursor.fetchall()}

    @staticmethod
    async def _table_exists(db: aiosqlite.Connection, table: str) -> bool:
        cursor = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return await cursor.fetchone() is not None

    async def refresh_register_dictionary(self) -> int:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO storage_register_dictionary(
                    register_name, address, function, unit
                )
                SELECT DISTINCT register_name, address, function, COALESCE(unit, '')
                FROM register_values
                """
            )
            await db.commit()
            return max(0, int(cursor.rowcount or 0))

    async def build_rollups(self, *, cutoff_ms: int, bucket_seconds: int) -> int:
        if bucket_seconds < 1:
            raise ValueError("bucket_seconds must be positive")
        await self.refresh_register_dictionary()
        bucket_ms = bucket_seconds * 1000
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                "DELETE FROM storage_rollups WHERE bucket_seconds=? AND bucket_start_ms<?",
                (bucket_seconds, cutoff_ms),
            )
            numeric = await db.execute(
                """
                INSERT INTO storage_rollups(
                    device_id, register_key, bucket_seconds, bucket_start_ms, kind,
                    sample_count, min_value, max_value, avg_value, first_numeric, last_numeric,
                    first_text, last_text, transitions
                )
                WITH base AS (
                    SELECT s.device_id, d.register_key, s.id AS sample_id, s.observed_at_ms,
                           (s.observed_at_ms / ?) * ? AS bucket_start_ms, v.numeric_value
                    FROM register_values v
                    JOIN poll_samples s ON s.id=v.sample_id
                    JOIN storage_register_dictionary d
                      ON d.register_name=v.register_name AND d.address=v.address
                     AND d.function=v.function AND d.unit=COALESCE(v.unit, '')
                    WHERE s.observed_at_ms<? AND v.numeric_value IS NOT NULL
                ), ranked AS (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY device_id, register_key, bucket_start_ms
                               ORDER BY observed_at_ms, sample_id
                           ) AS first_rank,
                           ROW_NUMBER() OVER (
                               PARTITION BY device_id, register_key, bucket_start_ms
                               ORDER BY observed_at_ms DESC, sample_id DESC
                           ) AS last_rank
                    FROM base
                )
                SELECT device_id, register_key, ?, bucket_start_ms, 0, COUNT(*),
                       MIN(numeric_value), MAX(numeric_value), AVG(numeric_value),
                       MAX(CASE WHEN first_rank=1 THEN numeric_value END),
                       MAX(CASE WHEN last_rank=1 THEN numeric_value END),
                       NULL, NULL, 0
                FROM ranked
                GROUP BY device_id, register_key, bucket_start_ms
                """,
                (bucket_ms, bucket_ms, cutoff_ms, bucket_seconds),
            )
            text = await db.execute(
                """
                INSERT INTO storage_rollups(
                    device_id, register_key, bucket_seconds, bucket_start_ms, kind,
                    sample_count, min_value, max_value, avg_value, first_numeric, last_numeric,
                    first_text, last_text, transitions
                )
                WITH base AS (
                    SELECT s.device_id, d.register_key, s.id AS sample_id, s.observed_at_ms,
                           (s.observed_at_ms / ?) * ? AS bucket_start_ms, v.text_value,
                           LAG(v.text_value) OVER (
                               PARTITION BY s.device_id, d.register_key
                               ORDER BY s.observed_at_ms, s.id
                           ) AS previous_text
                    FROM register_values v
                    JOIN poll_samples s ON s.id=v.sample_id
                    JOIN storage_register_dictionary d
                      ON d.register_name=v.register_name AND d.address=v.address
                     AND d.function=v.function AND d.unit=COALESCE(v.unit, '')
                    WHERE s.observed_at_ms<? AND v.text_value IS NOT NULL
                ), ranked AS (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY device_id, register_key, bucket_start_ms
                               ORDER BY observed_at_ms, sample_id
                           ) AS first_rank,
                           ROW_NUMBER() OVER (
                               PARTITION BY device_id, register_key, bucket_start_ms
                               ORDER BY observed_at_ms DESC, sample_id DESC
                           ) AS last_rank
                    FROM base
                )
                SELECT device_id, register_key, ?, bucket_start_ms, 1, COUNT(*),
                       NULL, NULL, NULL, NULL, NULL,
                       MAX(CASE WHEN first_rank=1 THEN text_value END),
                       MAX(CASE WHEN last_rank=1 THEN text_value END),
                       SUM(CASE WHEN previous_text IS NOT NULL AND previous_text != text_value THEN 1 ELSE 0 END)
                FROM ranked
                GROUP BY device_id, register_key, bucket_start_ms
                """,
                (bucket_ms, bucket_ms, cutoff_ms, bucket_seconds),
            )
            await db.commit()
            return max(0, int(numeric.rowcount or 0)) + max(0, int(text.rowcount or 0))

    async def build_state_runs(self, *, cutoff_ms: int) -> int:
        await self.refresh_register_dictionary()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("DELETE FROM storage_state_runs WHERE started_at_ms<?", (cutoff_ms,))
            cursor = await db.execute(
                """
                INSERT INTO storage_state_runs(
                    device_id, register_key, started_at_ms, ended_at_ms, value, sample_count
                )
                WITH states AS (
                    SELECT s.device_id, d.register_key, s.observed_at_ms, v.text_value,
                           CASE WHEN LAG(v.text_value) OVER (
                               PARTITION BY s.device_id, d.register_key
                               ORDER BY s.observed_at_ms, s.id
                           ) IS v.text_value THEN 0 ELSE 1 END AS changed
                    FROM register_values v
                    JOIN poll_samples s ON s.id=v.sample_id
                    JOIN storage_register_dictionary d
                      ON d.register_name=v.register_name AND d.address=v.address
                     AND d.function=v.function AND d.unit=COALESCE(v.unit, '')
                    WHERE s.observed_at_ms<? AND v.text_value IS NOT NULL
                ), grouped AS (
                    SELECT *, SUM(changed) OVER (
                        PARTITION BY device_id, register_key ORDER BY observed_at_ms
                    ) AS run_id
                    FROM states
                )
                SELECT device_id, register_key, MIN(observed_at_ms), MAX(observed_at_ms),
                       MAX(text_value), COUNT(*)
                FROM grouped
                GROUP BY device_id, register_key, run_id
                """,
                (cutoff_ms,),
            )
            await db.commit()
            return max(0, int(cursor.rowcount or 0))

    async def archive_before(self, *, cutoff_ms: int, batch_rows: int = 10_000, level: int = 19) -> int:
        try:
            import pyarrow as pa  # type: ignore[import-not-found]
            import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Parquet archival requires the storage extra: pip install 'morningstar-modbus-api[storage]'"
            ) from exc

        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                SELECT MIN(observed_at_ms), MAX(observed_at_ms)
                FROM poll_samples
                WHERE observed_at_ms<?
                """,
                (cutoff_ms,),
            )
            bounds = await cursor.fetchone()
        if not bounds or bounds[0] is None:
            return 0
        first_ms = int(bounds[0])
        last_ms = int(bounds[1])
        first_day = datetime.fromtimestamp(first_ms / 1000, UTC).date()
        last_day = datetime.fromtimestamp(last_ms / 1000, UTC).date()
        archived = 0
        day = first_day
        while day <= last_day:
            start_dt = datetime(day.year, day.month, day.day, tzinfo=UTC)
            end_dt = start_dt + timedelta(days=1)
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = min(int(end_dt.timestamp() * 1000), cutoff_ms)
            if end_ms > start_ms:
                archived += await self._archive_range(
                    pa,
                    pq,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    batch_rows=batch_rows,
                    level=level,
                )
            day += timedelta(days=1)
        return archived

    async def _archive_range(
        self,
        pa: Any,
        pq: Any,
        *,
        start_ms: int,
        end_ms: int,
        batch_rows: int,
        level: int,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as db:
            existing = await db.execute(
                "SELECT verified FROM storage_archives WHERE start_ms=? AND end_ms=?",
                (start_ms, end_ms),
            )
            row = await existing.fetchone()
            if row and int(row[0]) == 1:
                return 0

        stamp = datetime.fromtimestamp(start_ms / 1000, UTC)
        folder = self.archive_dir / f"{stamp.year:04d}" / f"{stamp.month:02d}"
        await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
        target = folder / f"telemetry-{stamp:%Y-%m-%d}.parquet"
        temp = target.with_suffix(".parquet.tmp")
        if temp.exists():
            await asyncio.to_thread(temp.unlink)

        sql = """
            SELECT s.device_id, s.id AS sample_id, s.observed_at_ms, s.latency_ms, s.profile,
                   v.register_name, v.address, v.function, v.raw_json,
                   v.numeric_value, v.text_value, v.unit
            FROM poll_samples s
            JOIN register_values v ON v.sample_id=s.id
            WHERE s.observed_at_ms>=? AND s.observed_at_ms<?
            ORDER BY s.observed_at_ms, s.id, v.address, v.register_name
        """
        writer = None
        row_count = 0
        try:
            async with aiosqlite.connect(self.database_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(sql, (start_ms, end_ms))
                while True:
                    rows = await cursor.fetchmany(max(100, batch_rows))
                    if not rows:
                        break
                    payload = {name: [row[name] for row in rows] for name in rows[0].keys()}
                    table = pa.table(payload)
                    if writer is None:
                        writer = pq.ParquetWriter(
                            temp,
                            table.schema,
                            compression="zstd",
                            compression_level=level,
                            use_dictionary=True,
                            write_statistics=True,
                        )
                    await asyncio.to_thread(writer.write_table, table)
                    row_count += len(rows)
            if writer is not None:
                await asyncio.to_thread(writer.close)
                writer = None
            if row_count == 0:
                if temp.exists():
                    await asyncio.to_thread(temp.unlink)
                return 0
            digest = await asyncio.to_thread(_sha256, temp)
            size = await asyncio.to_thread(_file_size, temp)
            await asyncio.to_thread(os.replace, temp, target)
            verified = int(await asyncio.to_thread(_sha256, target) == digest)
            async with aiosqlite.connect(self.database_path) as db:
                await db.execute(
                    """
                    INSERT INTO storage_archives(
                        start_ms, end_ms, path, row_count, bytes, sha256, codec, verified, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, 'parquet+zstd', ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        row_count=excluded.row_count, bytes=excluded.bytes, sha256=excluded.sha256,
                        verified=excluded.verified, created_at_ms=excluded.created_at_ms
                    """,
                    (start_ms, end_ms, str(target), row_count, size, digest, verified, _now_ms()),
                )
                await db.commit()
            if not verified:
                raise RuntimeError(f"archive verification failed: {target}")
            return row_count
        finally:
            if writer is not None:
                await asyncio.to_thread(writer.close)
            if temp.exists():
                await asyncio.to_thread(temp.unlink)

    async def prune_verified_archives(self, *, cutoff_ms: int) -> int:
        """Delete raw rows only for time ranges with a verified lossless archive."""
        deleted = 0
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            cursor = await db.execute(
                """
                SELECT start_ms, end_ms FROM storage_archives
                WHERE verified=1 AND end_ms<=?
                ORDER BY start_ms
                """,
                (cutoff_ms,),
            )
            ranges = await cursor.fetchall()
            for start_ms, end_ms in ranges:
                await db.execute("BEGIN IMMEDIATE")
                if await self._table_exists(db, "poll_performance_samples"):
                    await db.execute(
                        "DELETE FROM poll_performance_samples WHERE observed_at_ms>=? AND observed_at_ms<?",
                        (start_ms, end_ms),
                    )
                result = await db.execute(
                    "DELETE FROM poll_samples WHERE observed_at_ms>=? AND observed_at_ms<?",
                    (start_ms, end_ms),
                )
                deleted += max(0, int(result.rowcount or 0))
                await db.commit()
        return deleted

    async def checkpoint(self, *, truncate: bool = True) -> None:
        mode = "TRUNCATE" if truncate else "PASSIVE"
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(f"PRAGMA wal_checkpoint({mode})")

    async def incremental_vacuum(self, *, pages: int = 2048) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(f"PRAGMA incremental_vacuum({max(1, pages)})")
            await db.execute("PRAGMA optimize")
            await db.commit()

    async def storage_report(self) -> StorageReport:
        db_path = Path(self.database_path)
        database_bytes, wal_bytes, shm_bytes = await asyncio.gather(
            asyncio.to_thread(_file_size, db_path),
            asyncio.to_thread(_file_size, Path(f"{self.database_path}-wal")),
            asyncio.to_thread(_file_size, Path(f"{self.database_path}-shm")),
        )
        async with aiosqlite.connect(self.database_path) as db:
            page_size = int((await (await db.execute("PRAGMA page_size")).fetchone())[0])
            page_count = int((await (await db.execute("PRAGMA page_count")).fetchone())[0])
            free_pages = int((await (await db.execute("PRAGMA freelist_count")).fetchone())[0])
            counts: dict[str, int] = {}
            for table in (
                "poll_samples",
                "register_values",
                "storage_rollups",
                "storage_state_runs",
                "storage_archives",
            ):
                if await self._table_exists(db, table):
                    value = await (await db.execute(f"SELECT COUNT(*) FROM {table}")).fetchone()
                    counts[table] = int(value[0])
                else:
                    counts[table] = 0
            archive = await (await db.execute(
                "SELECT COALESCE(SUM(bytes), 0) FROM storage_archives WHERE verified=1"
            )).fetchone()
            archive_bytes = int(archive[0])
        page_bytes = page_size * page_count
        free_page_bytes = page_size * free_pages
        reclaimable = (free_page_bytes / page_bytes * 100.0) if page_bytes else 0.0
        return StorageReport(
            database_bytes=database_bytes,
            wal_bytes=wal_bytes,
            shm_bytes=shm_bytes,
            archive_bytes=archive_bytes,
            page_bytes=page_bytes,
            free_page_bytes=free_page_bytes,
            reclaimable_percent=round(reclaimable, 3),
            poll_samples=counts["poll_samples"],
            register_values=counts["register_values"],
            rollups=counts["storage_rollups"],
            state_runs=counts["storage_state_runs"],
            archives=counts["storage_archives"],
        )

    async def maintain(
        self,
        *,
        hot_days: int = 7,
        warm_days: int = 30,
        cool_days: int = 180,
        warm_bucket_seconds: int = 10,
        cool_bucket_seconds: int = 60,
        cold_bucket_seconds: int = 300,
        archive_batch_rows: int = 10_000,
        parquet_compression_level: int = 19,
        prune_archived_raw: bool = True,
        vacuum_pages: int = 2048,
    ) -> dict[str, object]:
        if not 1 <= hot_days <= warm_days <= cool_days:
            raise ValueError("retention tiers must satisfy hot_days <= warm_days <= cool_days")
        started = _now_ms()
        await self.initialize()
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "INSERT INTO storage_maintenance_runs(started_at_ms, action) VALUES (?, 'maintain')",
                (started,),
            )
            run_id = int(cursor.lastrowid or 0)
            await db.commit()
        hot_cutoff = _cutoff_ms(hot_days)
        warm_cutoff = _cutoff_ms(warm_days)
        cool_cutoff = _cutoff_ms(cool_days)
        details: dict[str, object] = {
            "dictionary_added": await self.refresh_register_dictionary(),
            "warm_rollups": await self.build_rollups(
                cutoff_ms=hot_cutoff, bucket_seconds=warm_bucket_seconds
            ),
            "cool_rollups": await self.build_rollups(
                cutoff_ms=warm_cutoff, bucket_seconds=cool_bucket_seconds
            ),
            "cold_rollups": await self.build_rollups(
                cutoff_ms=cool_cutoff, bucket_seconds=cold_bucket_seconds
            ),
            "state_runs": await self.build_state_runs(cutoff_ms=hot_cutoff),
        }
        details["archived_register_rows"] = await self.archive_before(
            cutoff_ms=hot_cutoff,
            batch_rows=archive_batch_rows,
            level=parquet_compression_level,
        )
        details["pruned_samples"] = (
            await self.prune_verified_archives(cutoff_ms=hot_cutoff) if prune_archived_raw else 0
        )
        await self.checkpoint(truncate=True)
        await self.incremental_vacuum(pages=vacuum_pages)
        details["storage"] = (await self.storage_report()).to_dict()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "UPDATE storage_maintenance_runs SET finished_at_ms=?, details_json=? WHERE id=?",
                (_now_ms(), json.dumps(details, separators=(",", ":")), run_id),
            )
            await db.commit()
        return details
