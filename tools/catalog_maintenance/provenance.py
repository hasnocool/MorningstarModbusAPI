# tools/catalog_maintenance/provenance.py
"""CI review gate for catalog edits derived from vendor documentation."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

CATALOG_PREFIX = "src/morningstar_modbus/catalog/families/"
SOURCE_INDEX = "docs/vendor/morningstar/sources.json"
PROPOSAL_PREFIX = "catalog-proposals/"
TEST_PREFIX = "tests/"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_KEYS = {
    "source_id",
    "source_sha256",
    "affected_profiles",
    "changes",
    "tests",
}


def changed_paths(base_ref: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def validate_proposal_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: invalid proposal JSON: {exc}"]

    missing = sorted(_REQUIRED_KEYS - payload.keys())
    if missing:
        errors.append(f"{path}: missing required key(s): {', '.join(missing)}")
    if not str(payload.get("source_id", "")).strip():
        errors.append(f"{path}: source_id must be non-empty")
    if not _SHA256_RE.fullmatch(str(payload.get("source_sha256", ""))):
        errors.append(f"{path}: source_sha256 must be a 64-character SHA-256 digest")

    affected = payload.get("affected_profiles")
    if not isinstance(affected, list) or not affected:
        errors.append(f"{path}: affected_profiles must be a non-empty list")

    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        errors.append(f"{path}: changes must be a non-empty list")

    tests = payload.get("tests")
    if not isinstance(tests, list) or not tests:
        errors.append(f"{path}: tests must be a non-empty list")
    return errors


def enforce_review_gate(paths: tuple[str, ...], root: Path) -> list[str]:
    catalog_changed = any(
        path.startswith(CATALOG_PREFIX) or path == SOURCE_INDEX for path in paths
    )
    if not catalog_changed:
        return []

    proposal_paths = tuple(
        path
        for path in paths
        if path.startswith(PROPOSAL_PREFIX) and path.endswith(".json")
    )
    test_paths = tuple(path for path in paths if path.startswith(TEST_PREFIX))

    errors: list[str] = []
    if not proposal_paths:
        errors.append(
            "catalog/source changes require a reviewed catalog-proposals/*.json provenance record"
        )
    if not test_paths:
        errors.append("catalog/source changes require an accompanying tests/ change")

    for path in proposal_paths:
        errors.extend(validate_proposal_file(root / path))
    return errors
