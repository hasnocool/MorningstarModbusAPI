# tests/test_catalog_maintenance.py
import json
from pathlib import Path

import pytest

from tools.catalog_maintenance.diff import compare_observations
from tools.catalog_maintenance.parser import parse_register_observations
from tools.catalog_maintenance.provenance import enforce_review_gate
from tools.catalog_maintenance.snapshot import catalog_source_ids
from tools.catalog_maintenance.sources import load_sources, select_sources, validate_source_url

ROOT = Path(__file__).resolve().parents[1]
SOURCE_INDEX = ROOT / "docs" / "vendor" / "morningstar" / "sources.json"


def test_every_runtime_profile_source_is_indexed() -> None:
    sources = load_sources(SOURCE_INDEX)
    selected = select_sources(sources, catalog_source_ids())
    assert {source.source_id for source in selected} == catalog_source_ids()


@pytest.mark.parametrize(
    "url",
    [
        "http://www.morningstarcorp.com/file.pdf",
        "https://example.com/file.pdf",
        "file:///tmp/source.pdf",
    ],
)
def test_source_url_validation_rejects_unapproved_locations(url: str) -> None:
    with pytest.raises(ValueError):
        validate_source_url(url)


def test_parser_extracts_addresses_and_conservative_labels() -> None:
    observations = parse_register_observations(
        "example",
        (
            "0x0018 battery_voltage Battery Voltage\n"
            "0x00AA new_vendor_field Experimental Field\n",
        ),
    )
    by_address = {item.address: item for item in observations}
    assert by_address[0x0018].label == "battery_voltage"
    assert by_address[0x0018].confidence == 0.90
    assert by_address[0x00AA].label == "new_vendor_field"


def test_diff_ignores_matching_field_and_flags_unknown_address() -> None:
    observations = parse_register_observations(
        "tristar-mppt-modbus-v11",
        (
            "0x0018 battery_voltage Battery Voltage\n"
            "0x00AA new_vendor_field Experimental Field\n",
        ),
    )
    changes = compare_observations(observations)
    assert not any(change.address == 0x0018 for change in changes)
    assert any(
        change.profile == "tristar_mppt"
        and change.address == 0x00AA
        and change.change_type == "observed_address_not_declared"
        for change in changes
    )


def test_review_gate_requires_provenance_and_tests(tmp_path: Path) -> None:
    paths = ("src/morningstar_modbus/catalog/families/tristar_mppt.py",)
    errors = enforce_review_gate(paths, tmp_path)
    assert any("catalog-proposals" in error for error in errors)
    assert any("tests/" in error for error in errors)


def test_review_gate_accepts_valid_provenance_and_test_change(tmp_path: Path) -> None:
    proposal_path = tmp_path / "catalog-proposals" / "tristar-v12.json"
    proposal_path.parent.mkdir(parents=True)
    proposal_path.write_text(
        json.dumps(
            {
                "source_id": "tristar-mppt-modbus-v11",
                "source_sha256": "a" * 64,
                "affected_profiles": ["tristar_mppt"],
                "changes": [{"address": "0x0018", "change": "verified"}],
                "tests": ["tests/test_catalog.py::test_family_selection_prefers_specific_products"],
            }
        ),
        encoding="utf-8",
    )
    paths = (
        "src/morningstar_modbus/catalog/families/tristar_mppt.py",
        "catalog-proposals/tristar-v12.json",
        "tests/test_catalog.py",
    )
    assert enforce_review_gate(paths, tmp_path) == []
