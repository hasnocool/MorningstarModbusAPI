import json
from pathlib import Path

import pytest

from morningstar_modbus.maintenance.diff import compare_observations
from morningstar_modbus.maintenance.parser import parse_register_observations
from morningstar_modbus.maintenance.provenance import enforce_review_gate
from morningstar_modbus.maintenance.snapshot import catalog_source_ids
from morningstar_modbus.maintenance.sources import load_sources, select_sources, validate_source_url

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


def test_parser_extracts_canonical_table_rows_and_tracks_address_spaces() -> None:
    observations = parse_register_observations(
        "example",
        (
            "RAM\n"
            "0x0018 25 battery_voltage Battery Voltage V Float16\n"
            "Coils\n"
            "0x0018 25 CLEAR_ALARMS Clear alarms; true==do action\n"
            "EEPROM\n"
            "0xE000 57345 EV_reg Regulation Voltage V Float16\n"
            "Logged Data\n"
            "0x8000 logger_0 first log block\n",
        ),
    )
    by_label = {item.label: item for item in observations}
    assert by_label["battery_voltage"].scope == "runtime"
    assert by_label["CLEAR_ALARMS"].scope == "control"
    assert by_label["EV_reg"].scope == "configuration"
    assert by_label["logger_0"].scope == "log"


def test_parser_ignores_narrative_hex_mentions_and_float_examples() -> None:
    observations = parse_register_observations(
        "example",
        (
            "RAM\n"
            "Note: if va_ref_fixed (0x005A) is non-zero, it overrides the setting.\n"
            "f16 = (sign == 1) ? 0xfc00 : 0x7c00;\n"
            "0x1000 0000 instead of a fault\n"
            "0x005A 91 va_ref_fixed Array V fixed voltage\n",
        ),
    )
    assert [(item.address, item.label) for item in observations] == [(0x005A, "va_ref_fixed")]


def test_diff_treats_vendor_aliases_multiword_spans_and_raw_blocks_as_covered() -> None:
    observations = parse_register_observations(
        "genstar-mppt-modbus-v03",
        (
            "0x0000 SOFTWARE_VERSION Software version\n"
            "0x0001 SERIAL_NUMBER0 Serial number bytes 0-1\n"
            "0x0002 SERIAL_NUMBER2 Serial number bytes 2-3\n"
            "0x0021 VBTERM_F256 Battery voltage V float16\n"
            "0x002B P12_F256 12V power supply V float16\n",
        ),
    )
    comparison = compare_observations(observations)

    assert comparison.actionable == ()
    # 0x002B is already inside GenStar's raw 0x001F-0x0038 read block; it is a naming
    # opportunity rather than a missing address or runtime discrepancy.
    assert any(
        change.profile == "genstar_mppt"
        and change.address == 0x002B
        and change.change_type == "unnamed_field_in_read_block"
        for change in comparison.coverage_candidates
    )
    assert not any(
        change.address in {0x0000, 0x0001, 0x0002, 0x0021}
        for change in comparison.coverage_candidates
    )


def test_diff_ignores_control_configuration_log_and_alternate_encodings() -> None:
    observations = parse_register_observations(
        "genstar-mppt-modbus-v03",
        (
            "Coils\n"
            "0x0000 EQTRIG Manual equalize trigger\n"
            "EEPROM\n"
            "0x1068 Emodbus_id This device's Modbus address\n"
            "RAM\n"
            "0x0041 ILOAD_F256_0 Load current A float32\n"
            "0x0042 ILOAD_F256_1 Load current A float32\n"
            "Logged Data\n"
            "0x8000 logger_0 first log block\n",
        ),
    )
    comparison = compare_observations(observations)

    assert comparison.actionable == ()
    assert comparison.coverage_candidates == ()
    ignored = dict(comparison.ignored_counts)
    assert ignored["control"] == 1
    assert ignored["configuration"] == 1
    assert ignored["alternate_encoding"] == 2
    assert ignored["log"] == 1


def test_diff_reports_runtime_address_outside_read_blocks_as_coverage_candidate() -> None:
    observations = parse_register_observations(
        "tristar-mppt-modbus-v11",
        ("0x00AA 171 new_vendor_field Experimental runtime field\n",),
    )
    comparison = compare_observations(observations)

    assert comparison.actionable == ()
    assert any(
        change.profile == "tristar_mppt"
        and change.address == 0x00AA
        and change.change_type == "runtime_address_outside_read_blocks"
        for change in comparison.coverage_candidates
    )


def test_reserved_vendor_row_overlapping_declared_register_is_actionable() -> None:
    observations = parse_register_observations(
        "tristar-mppt-modbus-v11",
        ("0x0018 25 RESERVED -\n",),
    )
    comparison = compare_observations(observations)

    assert any(
        change.profile == "tristar_mppt"
        and change.address == 0x0018
        and change.change_type == "declared_register_overlaps_reserved_vendor_row"
        for change in comparison.actionable
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
