# Automated catalog maintenance

MorningstarModbusAPI keeps vendor-document monitoring separate from the runtime service. The
`morningstar_modbus.maintenance` package validates the official source index, downloads the
approved Morningstar documents referenced by active profiles, extracts conservative register-table
observations from PDFs, compares those observations with the checked-in catalog, and produces an
advisory report for human review.

It **never rewrites a family module automatically**.

## Directory layout

```text
src/morningstar_modbus/
└── maintenance/
    ├── __main__.py        # validate / scan CLI
    ├── diff.py            # observations vs checked-in profiles
    ├── extract.py         # PDF text extraction
    ├── models.py          # source/artifact/observation/comparison records
    ├── parser.py          # table-row extraction + address-space classification
    ├── provenance.py      # CI review gate
    ├── report.py          # JSON + Markdown reports
    ├── snapshot.py        # deterministic catalog snapshot
    └── sources.py         # approved-source loading/downloading

docs/vendor/morningstar/
├── sources.json           # machine-readable official source index
├── README.md              # source policy
├── REFERENCE.md           # concise implementation notes
├── pdfs/README.md         # official PDF filename/URL manifest
└── cache/                 # downloaded artifacts; git-ignored

catalog-proposals/
└── README.md              # reviewed provenance record format

.github/workflows/
└── catalog-maintenance.yml
```

The maintenance package is installed with the project so tests and CI import it consistently, but
it has no runtime service hooks. PDF parsing support is optional and loaded only by maintenance scans.

## Pipeline

1. Load `docs/vendor/morningstar/sources.json`.
2. Resolve the source IDs referenced by active catalog profiles.
3. Require approved HTTPS Morningstar URLs.
4. Download source artifacts into the selected cache directory.
5. Record exact artifact SHA-256 and available HTTP metadata.
6. Extract PDF page text with `pypdf`.
7. Parse **anchored vendor table rows** instead of treating every `0xNNNN` mention as a register.
8. Track major address spaces/sections such as runtime RAM, EEPROM/configuration, coils/control,
   logged data, examples, reserved rows, and alternate float encodings.
9. Compare runtime/reserved source observations with declared named register word spans and read blocks using the current conservative comparator.
10. Emit deterministic `report.json` and `report.md` without modifying application code.
11. A developer reviews actionable conflicts separately from optional coverage candidates and ignored observations.
12. Any accepted catalog/source change still requires tests and a `catalog-proposals/*.json`
    provenance record.

This intentionally favors false negatives over turning noisy PDF extraction into controller behavior.

## Runtime catalog can represent reserved ranges

The runtime catalog has first-class concepts for both semantic fields and manufacturer-reserved words:

- `RegisterSpec` describes a named semantic field;
- `ReservedRegisterRange` describes one or more readable words that Morningstar explicitly marks reserved;
- `RegisterBlock` describes the broader read-only range used for safe polling/raw evidence.

A vendor row marked **reserved** should not be converted into an invented semantic metric just because a broad Modbus read returns a value there. After source review, the correct catalog change may be a `ReservedRegisterRange` declaration.

This distinction is particularly visible in the TriStar MPPT v11 map, where the reviewed runtime catalog explicitly classifies `0x0005-0x0017`, `0x002D`, `0x003F`, `0x004A`, and `0xE0C4-0xE0CB` as reserved while continuing to preserve the raw words when the enclosing blocks are read.

The maintenance **comparator itself is intentionally simpler than the runtime catalog model**. It currently does not use declared `ReservedRegisterRange` objects as a separate matching class when comparing extracted rows. Instead, source rows classified as `reserved` are handled as described below. The generated report is advisory, so a reviewer reconciles those observations with the fuller runtime catalog before making a change.

## Current comparison behavior

Morningstar documents frequently reuse the same numeric address in different Modbus address spaces.
For example, a holding-register address and a coil address can both be `0x0018` without referring to
the same value. Vendor documents also contain EEPROM settings, write-only actions, logger ranges,
Float16 conversion examples, and narrative references to hexadecimal constants.

The runtime catalog also intentionally uses semantic API names. A vendor field such as
`VBTERM_F256` can legitimately map to `battery_terminal_voltage`; different spelling is not a
discrepancy.

The current comparator applies these rules:

- a **reserved source row that overlaps a declared named register** becomes an actionable `declared_register_overlaps_reserved_vendor_row` conflict;
- a **reserved source row with no named-register overlap** is counted as an ignored `reserved` observation;
- a non-runtime source row (EEPROM/configuration, coils/control, logs, examples, alternate encodings, and similar scopes) is ignored for runtime-map discrepancy purposes;
- a runtime source row covered by a named `RegisterSpec` word span is counted as covered, regardless of whether the vendor label spelling matches the public semantic name;
- a runtime source row with no named field but **inside an existing read block** is emitted as the lower-confidence coverage candidate `unnamed_field_in_read_block`;
- a runtime source row outside existing read blocks is emitted as `runtime_address_outside_read_blocks` with a higher allowed confidence ceiling.

So an active read block alone does **not** mean every runtime vendor field inside it has semantic coverage. The block makes the address safe to read; a missing named runtime field can still be reported as a coverage candidate.

`report.json` keeps actionable conflicts in `proposed_changes`, optional opportunities in `coverage_candidates`, and non-actionable/source-space observations in `ignored_observations` / ignored-count data.

## Reserved-range review workflow

Because extracted reserved rows without a named-register conflict are currently ignored by the comparator, adding or correcting a `ReservedRegisterRange` is a deliberate source-review task rather than an automatic scanner proposal.

A safe review flow is:

1. confirm the source row is from the correct runtime/read-only address space and firmware context;
2. confirm no documented semantic field occupies that word span;
3. compare the observation with the existing `RegisterBlock`, `RegisterSpec`, and any current `ReservedRegisterRange` declarations;
4. add or adjust the reserved range in the family catalog only when official source evidence supports it;
5. add catalog/intelligence tests for the declared range/effective-map behavior;
6. add a provenance record bound to the exact source artifact SHA-256.

The scanner remains advisory throughout this process.

## Commands

Validate source coverage and catalog structure:

```bash
python -m morningstar_modbus.maintenance validate
```

Write a deterministic catalog snapshot during validation:

```bash
python -m morningstar_modbus.maintenance validate \
  --snapshot /tmp/morningstar-catalog.json
```

Validate a proposed catalog edit against a base ref:

```bash
python -m morningstar_modbus.maintenance validate --base-ref origin/main
```

Install PDF support and refresh the active official source set:

```bash
python -m pip install -e '.[maintenance]'
python -m morningstar_modbus.maintenance scan
```

Reuse existing cached artifacts instead of refreshing them:

```bash
python -m morningstar_modbus.maintenance scan --use-cache
```

Use alternate cache/report destinations:

```bash
python -m morningstar_modbus.maintenance scan \
  --cache-dir /tmp/morningstar-source-cache \
  --output-dir /tmp/morningstar-catalog-report
```

The repository defaults are:

```text
docs/vendor/morningstar/cache/
catalog-maintenance-report/
```

Both are git-ignored.

## Vendor PDF policy

Morningstar's official PDFs are source material, not project-authored files. The repository keeps the
authoritative URLs/filenames and review provenance but does not republish complete vendor manuals.
Local/CI maintenance scans obtain the documents directly from Morningstar and bind reviewed changes
to the exact downloaded artifact using SHA-256.

See [`vendor/morningstar/pdfs/README.md`](vendor/morningstar/pdfs/README.md) for the official PDF
manifest.

## Review provenance

A catalog/source update needs a JSON record such as:

```json
{
  "source_id": "tristar-mppt-modbus-v11",
  "source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "affected_profiles": ["tristar_mppt"],
  "changes": [
    {
      "range": "0x0005-0x0017",
      "change": "classify vendor-documented runtime words as reserved rather than semantic telemetry"
    }
  ],
  "tests": ["tests/test_catalog.py::test_tristar_reserved_ranges"]
}
```

The source hash binds code review to the exact artifact inspected. The generated maintenance report
alone is not sufficient evidence because PDF extraction is heuristic.

A proposal may cover semantic register decoding, a reserved-range classification, firmware gates, source-index changes, or other vendor-derived catalog truth. The important requirement is that the reviewed change is bound to the exact official artifact and accompanied by tests.

## GitHub Actions

The catalog-maintenance workflow has two modes:

- pull requests: validate source coverage, run the provenance gate when catalog/source files change, and execute catalog tests;
- schedule/manual dispatch: download official documents and upload the advisory JSON/Markdown report
  as an Actions artifact.

Scheduled/manual scans do not push commits, rewrite catalog code, or merge pull requests.
