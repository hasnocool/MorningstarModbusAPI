# Automated catalog maintenance

MorningstarModbusAPI keeps vendor-document monitoring separate from the runtime service. The `morningstar_modbus.maintenance` package validates the official source index, can download the approved Morningstar documents referenced by active profiles, extracts conservative register observations from PDFs, compares those observations with the checked-in catalog, and produces an advisory diff for human review.

It **never rewrites a family module automatically**.

## Directory layout

```text
src/morningstar_modbus/
└── maintenance/
    ├── __main__.py        # validate / scan CLI
    ├── diff.py            # observations vs checked-in profiles
    ├── extract.py         # PDF text extraction
    ├── models.py          # source/artifact/observation/proposal records
    ├── parser.py          # conservative address/table extraction
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

The maintenance package is installed with the project so tests and CI import it consistently, but it has no runtime service hooks. PDF parsing support is optional and loaded only by maintenance scans.

## Pipeline

1. Load `docs/vendor/morningstar/sources.json`.
2. Resolve the source IDs referenced by active catalog profiles.
3. Require approved HTTPS Morningstar URLs.
4. Download source artifacts into the selected cache directory.
5. Record exact artifact SHA-256 and available HTTP metadata.
6. Extract PDF page text with `pypdf`.
7. Collect conservative `0xNNNN` register observations with source page/text provenance.
8. Compare observations with the current `catalog/families/*.py` declarations.
9. Emit deterministic `report.json` and `report.md` without modifying application code.
10. A developer reviews the source, manually edits the catalog if warranted, changes/adds tests, and records a `catalog-proposals/*.json` provenance entry.
11. CI rejects catalog/source-index edits that omit required provenance or tests.

This intentionally favors false negatives over automatically converting noisy PDF extraction into controller behavior.

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

Morningstar's official PDFs are source material, not project-authored files. The repository keeps the authoritative URLs/filenames and review provenance but does not republish complete vendor manuals. Local/CI maintenance scans obtain the documents directly from Morningstar and bind reviewed changes to the exact downloaded artifact using SHA-256.

See [`vendor/morningstar/pdfs/README.md`](vendor/morningstar/pdfs/README.md) for the official PDF manifest.

## Review provenance

A catalog/source update needs a JSON record such as:

```json
{
  "source_id": "tristar-mppt-modbus-v11",
  "source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "affected_profiles": ["tristar_mppt"],
  "changes": [
    {
      "address": "0x0018",
      "change": "verified decoder and unit against updated vendor table"
    }
  ],
  "tests": ["tests/test_catalog.py::test_tristar_updated_register"]
}
```

The source hash binds code review to the exact artifact inspected. The generated maintenance report alone is not sufficient evidence because PDF extraction is heuristic.

## GitHub Actions

The catalog-maintenance workflow has two modes:

- pull requests: validate source coverage, run the provenance gate, and execute catalog tests;
- schedule/manual dispatch: download official documents and upload the advisory JSON/Markdown report as an Actions artifact.

Scheduled/manual scans do not push commits, rewrite catalog code, or merge pull requests.
