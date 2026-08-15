# src/morningstar_modbus/maintenance/report.py
"""Render machine-readable and human-readable catalog maintenance reports."""

from __future__ import annotations

import json
from pathlib import Path

from morningstar_modbus.maintenance.models import CatalogComparison, ProposedChange, SourceArtifact


def _render_changes(lines: list[str], changes: tuple[ProposedChange, ...]) -> None:
    lines.extend(
        [
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


def write_report(
    output_dir: Path,
    artifacts: tuple[SourceArtifact, ...],
    comparison: CatalogComparison,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"

    payload = {
        "actionable_count": comparison.actionable_count,
        "coverage_candidate_count": comparison.coverage_candidate_count,
        "ignored_observations": dict(comparison.ignored_counts),
        "sources": [artifact.to_dict() for artifact in artifacts],
        # Keep proposed_changes as the backward-compatible location for actual conflicts.
        "proposed_changes": [change.to_dict() for change in comparison.actionable],
        "coverage_candidates": [change.to_dict() for change in comparison.coverage_candidates],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Morningstar Catalog Maintenance Report",
        "",
        "This report is advisory. The scanner never edits catalog family modules automatically.",
        "",
        f"Actionable discrepancies: **{comparison.actionable_count}**",
        f"Coverage candidates: **{comparison.coverage_candidate_count}**",
        "",
        "Coverage candidates are not errors. They are vendor table rows that are not yet represented",
        "as a named field or active read block in the intentionally selective runtime catalog.",
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

    lines.extend(["", "## Actionable discrepancies", ""])
    if comparison.actionable:
        _render_changes(lines, comparison.actionable)
    else:
        lines.append("No runtime catalog conflicts were detected.")

    lines.extend(["", "## Coverage candidates", ""])
    if comparison.coverage_candidates:
        _render_changes(lines, comparison.coverage_candidates)
    else:
        lines.append("No additional runtime coverage candidates were detected.")

    if comparison.ignored_counts:
        lines.extend(
            [
                "",
                "## Ignored observations",
                "",
                "These observations came from vendor sections that do not represent a runtime catalog",
                "conflict, or from addresses already covered by a named field.",
                "",
                "| Reason | Count |",
                "| --- | ---: |",
            ]
        )
        for reason, count in comparison.ignored_counts:
            lines.append(f"| `{reason}` | {count} |")

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
