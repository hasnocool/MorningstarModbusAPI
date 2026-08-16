# tests/test_storage_v2.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from morningstar_modbus.persistence.storage_v2 import StorageV2Manager


async def _legacy_db(path: str) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE devices(id TEXT PRIMARY KEY);
            CREATE TABLE poll_samples(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                observed_at TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                profile TEXT NOT NULL
            );
            CREATE TABLE register_values(
                sample_id INTEGER NOT NULL REFERENCES poll_samples(id) ON DELETE CASCADE,
                register_name TEXT NOT NULL,
                address INTEGER NOT NULL,
                function TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                numeric_value REAL,
                text_value TEXT,
                unit TEXT,
                PRIMARY KEY(sample_id, register_name)
            );
            CREATE TABLE poll_errors(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                observed_at TEXT NOT NULL,
                error TEXT NOT NULL
            );
            INSERT INTO devices(id) VALUES ('dev-1');
            """
        )
        start = datetime.now(UTC) - timedelta(days=10)
        for index in range(6):
            observed = (start + timedelta(seconds=index)).isoformat()
            cursor = await db.execute(
                """
                INSERT INTO poll_samples(device_id, observed_at, latency_ms, profile)
                VALUES (?, ?, 5.0, 'test')
                """,
                ("dev-1", observed),
            )
            sample_id = int(cursor.lastrowid or 0)
            await db.execute(
                """
                INSERT INTO register_values(
                    sample_id, register_name, address, function, raw_json, numeric_value, unit
                ) VALUES (?, 'battery_voltage', 24, 'holding', '[1]', ?, 'V')
                """,
                (sample_id, 12.0 + index / 10),
            )
            await db.execute(
                """
                INSERT INTO register_values(
                    sample_id, register_name, address, function, raw_json, text_value, unit
                ) VALUES (?, 'charge_state', 50, 'holding', '[5]', ?, '')
                """,
                (sample_id, "MPPT" if index < 4 else "ABSORPTION"),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_storage_v2_migrates_existing_database_and_builds_compact_layers(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    archive = tmp_path / "archive"
    await _legacy_db(str(database))
    manager = StorageV2Manager(str(database), str(archive))

    await manager.initialize()
    report = await manager.storage_report()
    cutoff_ms = int(datetime.now(UTC).timestamp() * 1000)
    rollups = await manager.build_rollups(cutoff_ms=cutoff_ms, bucket_seconds=60)
    state_runs = await manager.build_state_runs(cutoff_ms=cutoff_ms)

    assert report.poll_samples == 6
    assert report.register_values == 12
    assert rollups >= 2
    assert state_runs == 2

    async with aiosqlite.connect(database) as db:
        columns = {
            row[1]
            for row in await (await db.execute("PRAGMA table_info(poll_samples)")).fetchall()
        }
        dictionary = int(
            (
                await (
                    await db.execute("SELECT COUNT(*) FROM storage_register_dictionary")
                ).fetchone()
            )[0]
        )
    assert "observed_at_ms" in columns
    assert dictionary == 2


@pytest.mark.asyncio
async def test_pruning_requires_verified_archive(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    await _legacy_db(str(database))
    manager = StorageV2Manager(str(database), str(tmp_path / "archive"))
    await manager.initialize()
    cutoff_ms = int(datetime.now(UTC).timestamp() * 1000)

    assert await manager.prune_verified_archives(cutoff_ms=cutoff_ms) == 0
    assert (await manager.storage_report()).poll_samples == 6


@pytest.mark.asyncio
async def test_parquet_archive_is_verified_before_pruning(tmp_path) -> None:
    pytest.importorskip("pyarrow")
    database = tmp_path / "legacy.db"
    await _legacy_db(str(database))
    manager = StorageV2Manager(str(database), str(tmp_path / "archive"))
    await manager.initialize()
    cutoff_ms = int(datetime.now(UTC).timestamp() * 1000)

    archived = await manager.archive_before(cutoff_ms=cutoff_ms, batch_rows=2, level=3)
    deleted = await manager.prune_verified_archives(cutoff_ms=cutoff_ms)
    report = await manager.storage_report()

    assert archived == 12
    assert deleted == 6
    assert report.poll_samples == 0
    assert report.register_values == 0
    assert report.archives >= 1
    assert report.archive_bytes > 0
