# tools/fetch_morningstar_docs.py
"""Fetch official Morningstar reference documents into a local ignored cache."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "docs" / "vendor" / "morningstar" / "sources.json"
DEFAULT_CACHE = ROOT / "docs" / "vendor" / "morningstar" / "cache"
USER_AGENT = "MorningstarModbusAPI-doc-fetch/1.0 (+https://github.com/hasnocool/MorningstarModbusAPI)"


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    title: str
    url: str
    filename: str


def _load_sources(path: Path) -> list[Source]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    sources: list[Source] = []
    for item in payload.get("sources", []):
        if item.get("download", True) is False:
            continue
        filename = item.get("filename")
        if not filename:
            continue
        sources.append(
            Source(
                source_id=str(item["id"]),
                title=str(item["title"]),
                url=str(item["url"]),
                filename=str(filename),
            )
        )
    return sources


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_one(source: Source, destination: Path, *, refresh: bool) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not refresh:
        return {
            "id": source.source_id,
            "status": "cached",
            "path": str(destination),
            "sha256": _sha256(destination),
            "bytes": destination.stat().st_size,
        }

    request = urllib.request.Request(
        source.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    temporary_path: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"application/pdf", "application/octet-stream"}:
                raise RuntimeError(
                    f"unexpected content type for {source.source_id}: {content_type}"
                )
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".part",
                dir=destination.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
        temporary_path.replace(destination)
        return {
            "id": source.source_id,
            "status": "downloaded",
            "path": str(destination),
            "sha256": _sha256(destination),
            "bytes": destination.stat().st_size,
        }
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


async def _fetch_one(
    source: Source,
    cache_dir: Path,
    semaphore: asyncio.Semaphore,
    *,
    refresh: bool,
) -> dict[str, object]:
    async with semaphore:
        destination = cache_dir / source.filename
        return await asyncio.to_thread(_download_one, source, destination, refresh=refresh)


async def _run(args: argparse.Namespace) -> int:
    sources = await asyncio.to_thread(_load_sources, CATALOG_PATH)
    if args.source:
        selected = [source for source in sources if source.source_id in args.source]
        missing = sorted(set(args.source) - {source.source_id for source in selected})
        if missing:
            raise SystemExit(f"unknown source id(s): {', '.join(missing)}")
        sources = selected

    if args.list:
        for source in sources:
            print(f"{source.source_id}: {source.title}")
            print(f"  {source.url}")
        return 0

    cache_dir = Path(args.cache_dir).expanduser()
    await asyncio.to_thread(cache_dir.mkdir, parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.workers)
    tasks = [
        asyncio.create_task(
            _fetch_one(source, cache_dir, semaphore, refresh=args.refresh),
            name=f"fetch-{source.source_id}",
        )
        for source in sources
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    manifest: list[dict[str, object]] = []
    for source, result in zip(sources, results, strict=True):
        if isinstance(result, BaseException):
            failures += 1
            print(f"FAILED {source.source_id}: {type(result).__name__}: {result}")
            continue
        manifest.append(result)
        print(
            f"{result['status'].upper():10} {source.source_id} "
            f"{result['bytes']} bytes sha256={result['sha256']}"
        )

    manifest_path = cache_dir / "manifest.json"
    await asyncio.to_thread(
        manifest_path.write_text,
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch official Morningstar reference PDFs into an ignored local cache."
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE),
        help="destination directory for downloaded documents",
    )
    parser.add_argument(
        "--source",
        action="append",
        help="fetch only this source id; repeat for multiple sources",
    )
    parser.add_argument("--refresh", action="store_true", help="replace already cached documents")
    parser.add_argument("--list", action="store_true", help="list catalog sources without downloading")
    parser.add_argument("--workers", type=int, default=3, choices=range(1, 9))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
