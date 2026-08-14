# tools/catalog_maintenance/report.py
"""Render machine-readable and human-readable catalog maintenance reports."""

from __future__ import annotations

import json
from pathlib import Path

from tools.catalog_maintenance.models import ProposedChange, SourceArtifact


def write_report(
    output_dir: Path,
    artifacts: tuple[SourceArtifact, ...],
    changes: tuple[ProposedChange, ...],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"

    payload = {
        "actionable_count": len(changes),
        "sources": [artifact.to_dict() for artifact in artifacts],
        "proposed_changes": [change.to_dict() for change in changes],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Morningstar Catalog Maintenance Report",
        "",
        "This report is advisory. The scanner never edits catalog family modules automatically.",
        "",
        f"Actionable observations: **{len(changes)}**",
        "",
        "## Source artifacts",
        "",
        "| Source | SHA-256 | Bytes |",
        "| --- | --- | ---: |",
    ]
    for artifact in artifacts:
        lines.append(
            f"| `{artifact.source.source_id}` | `{artifact.sha256}` | {artifact.size_bytes} |"
        )

    lines.extend(
        [
            "",
            "## Proposed differences",
            "",
            "| Profile | Address | Type | Observed label | Declared names | Confidence | Page |",
            "| --- | ---: | --- | --- | --- | ---: | ---: |",
        ]
    )
    for change in changes:
        declared = ", ".join(change.declared_names) or "—"
        label = change.observed_label or "—"
        lines.append(
            f"| `{change.profile}` | `{change.address_hex}` | `{change.change_type}` | "
            f"`{label}` | `{declared}` | {change.confidence:.2f} | {change.page} |"
        )
    lines.extend(
        [
            "",
            "To accept a real catalog change, update the family module manually, add/adjust tests,",
            "and commit a `catalog-proposals/*.json` provenance record containing the source hash.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path
