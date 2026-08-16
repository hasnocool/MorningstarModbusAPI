# src/morningstar_modbus/cli/storage.py
"""Storage-v2 maintenance command."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from morningstar_modbus.config.settings import load_config
from morningstar_modbus.persistence.storage_v2 import StorageV2Manager


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Morningstar compressed time-series storage maintenance")
    parser.add_argument("--config", default=None, help="TOML config file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("initialize", help="initialize additive Storage v2 schema")
    sub.add_parser("status", help="report SQLite/WAL/archive/reclaimable sizes")
    maintain = sub.add_parser("maintain", help="roll up, archive, prune, checkpoint, and vacuum")
    maintain.add_argument("--no-prune", action="store_true", help="archive but keep raw SQLite rows")
    return parser


async def _run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_config(args.config)
    storage = config.storage
    manager = StorageV2Manager(config.database.path, storage.archive_dir)
    if args.command == "initialize":
        await manager.initialize()
        result: object = {"initialized": True}
    elif args.command == "status":
        await manager.initialize()
        result = (await manager.storage_report()).to_dict()
    else:
        result = await manager.maintain(
            hot_days=storage.hot_days,
            warm_days=storage.warm_days,
            cool_days=storage.cool_days,
            warm_bucket_seconds=storage.warm_bucket_seconds,
            cool_bucket_seconds=storage.cool_bucket_seconds,
            cold_bucket_seconds=storage.cold_bucket_seconds,
            archive_batch_rows=storage.archive_batch_rows,
            parquet_compression_level=storage.parquet_compression_level,
            prune_archived_raw=storage.prune_archived_raw and not args.no_prune,
            vacuum_pages=storage.incremental_vacuum_pages,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
