# tools/catalog_maintenance/sources.py
"""Secure loading and downloading of official Morningstar catalog sources."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from tools.catalog_maintenance.models import SourceArtifact, SourceDocument

USER_AGENT = (
    "MorningstarModbusAPI-catalog-maintenance/1.0 "
    "(+https://github.com/hasnocool/MorningstarModbusAPI)"
)
_ALLOWED_HOSTS = {"morningstarcorp.com", "www.morningstarcorp.com"}


def validate_source_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"source must use HTTPS: {url}")
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError(f"source host is not approved: {parsed.hostname or '<missing>'}")


def load_sources(path: Path) -> tuple[SourceDocument, ...]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    sources: list[SourceDocument] = []
    seen: set[str] = set()
    for item in payload.get("sources", []):
        if item.get("download", True) is False or not item.get("filename"):
            continue
        source_id = str(item["id"])
        if source_id in seen:
            raise ValueError(f"duplicate source id: {source_id}")
        seen.add(source_id)
        url = str(item["url"])
        validate_source_url(url)
        sources.append(
            SourceDocument(
                source_id=source_id,
                title=str(item["title"]),
                url=url,
                filename=str(item["filename"]),
                format=str(item.get("format", "pdf")).casefold(),
                version=str(item.get("version", "")),
                document_id=str(item.get("document_id", "")),
                document_date=str(item.get("document_date", "")),
            )
        )
    return tuple(sources)


def select_sources(
    sources: tuple[SourceDocument, ...],
    source_ids: set[str],
) -> tuple[SourceDocument, ...]:
    by_id = {source.source_id: source for source in sources}
    missing = sorted(source_ids - by_id.keys())
    if missing:
        raise ValueError(f"catalog references unknown source id(s): {', '.join(missing)}")
    return tuple(by_id[source_id] for source_id in sorted(source_ids))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_source(
    source: SourceDocument,
    cache_dir: Path,
    *,
    use_cache: bool = False,
) -> SourceArtifact:
    validate_source_url(source.url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / source.filename
    if destination.exists() and use_cache:
        return SourceArtifact(
            source=source,
            path=str(destination),
            sha256=sha256_file(destination),
            size_bytes=destination.stat().st_size,
        )

    request = urllib.request.Request(
        source.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    temporary_path: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if source.format == "pdf":
                content_type = response.headers.get_content_type()
                if content_type not in {"application/pdf", "application/octet-stream"}:
                    raise RuntimeError(
                        f"unexpected content type for {source.source_id}: {content_type}"
                    )
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".part",
                dir=cache_dir,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(destination)
            return SourceArtifact(
                source=source,
                path=str(destination),
                sha256=sha256_file(destination),
                size_bytes=destination.stat().st_size,
                etag=response.headers.get("ETag", ""),
                last_modified=response.headers.get("Last-Modified", ""),
            )
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
