# tools/catalog_maintenance/__main__.py
"""CLI entry point for source validation and advisory Morningstar catalog scans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.catalog_maintenance.diff import compare_observations
from tools.catalog_maintenance.extract import extract_pdf_pages
from tools.catalog_maintenance.parser import parse_register_observations
from tools.catalog_maintenance.provenance import changed_paths, enforce_review_gate
from tools.catalog_maintenance.report import write_report
from tools.catalog_maintenance.snapshot import catalog_snapshot, catalog_source_ids
from tools.catalog_maintenance.sources import download_source, load_sources, select_sources

ROOT = Path(__file__).resolve().parents[2]
SOURCE_INDEX = ROOT / "docs" / "vendor" / "morningstar" / "sources.json"
DEFAULT_CACHE = ROOT / "docs" / "vendor" / "morningstar" / "cache"
DEFAULT_OUTPUT = ROOT / "catalog-maintenance-report"


def _validate(args: argparse.Namespace) -> int:
    sources = load_sources(SOURCE_INDEX)
    selected = select_sources(sources, catalog_source_ids())
    snapshot = catalog_snapshot()

    if args.snapshot:
        destination = Path(args.snapshot)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    errors: list[str] = []
    if args.base_ref:
        errors.extend(enforce_review_gate(changed_paths(args.base_ref), ROOT))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        f"validated {len(selected)} catalog source(s) and "
        f"{len(snapshot['profiles'])} profile definition(s)"
    )
    return 0


def _scan(args: argparse.Namespace) -> int:
    sources = load_sources(SOURCE_INDEX)
    selected = select_sources(sources, catalog_source_ids())
    cache_dir = Path(args.cache_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()

    artifacts = []
    observations = []
    for source in selected:
        artifact = download_source(source, cache_dir, use_cache=args.use_cache)
        artifacts.append(artifact)
        if source.format != "pdf":
            continue
        pages = extract_pdf_pages(Path(artifact.path))
        parsed = parse_register_observations(source.source_id, pages)
        observations.extend(parsed)
        print(
            f"{source.source_id}: sha256={artifact.sha256} "
            f"pages={len(pages)} observations={len(parsed)}"
        )

    changes = compare_observations(tuple(observations))
    json_path, markdown_path = write_report(output_dir, tuple(artifacts), changes)
    print(f"actionable observations: {len(changes)}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and scan official Morningstar Modbus catalog sources."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate",
        help="validate source references, catalog structure, and optional review provenance",
    )
    validate.add_argument(
        "--base-ref",
        help="git base ref/SHA used to enforce provenance and test requirements",
    )
    validate.add_argument(
        "--snapshot",
        help="write a deterministic JSON snapshot of the checked-in catalog",
    )
    validate.set_defaults(func=_validate)

    scan = subparsers.add_parser(
        "scan",
        help="download official profile sources and generate an advisory catalog diff",
    )
    scan.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    scan.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    scan.add_argument(
        "--use-cache",
        action="store_true",
        help="reuse already-downloaded documents instead of refreshing them",
    )
    scan.set_defaults(func=_scan)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
