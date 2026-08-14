# Automated Catalog Maintenance

MorningstarModbusAPI keeps vendor-document monitoring separate from the runtime service. The
`tools.catalog_maintenance` package can refresh the official Modbus documents already referenced by
the product catalog, extract conservative register observations, compare those observations with
the checked-in family definitions, and produce an advisory diff for human review.

It **never rewrites a family module automatically**.

## Directory layout

```text
tools/
└── catalog_maintenance/
    ├── __main__.py        # validate / scan CLI
    ├── diff.py            # observations vs checked-in profiles
    ├── extract.py         # PDF text extraction
    ├── models.py          # source/observation/proposal records
    ├── parser.py          # conservative address/table extraction
    ├── provenance.py      # CI review gate
    ├── report.py          # JSON + Markdown reports
    ├── snapshot.py        # deterministic catalog snapshot
    └── sources.py         # approved-source loading/downloading

catalog-proposals/
└── README.md              # provenance record format

.github/workflows/
└── catalog-maintenance.yml
```

Runtime code remains under `src/morningstar_modbus/`; source ingestion and review automation stay
under `tools/`.

## Pipeline

1. Read `docs/vendor/morningstar/sources.json`.
2. Resolve only source IDs referenced by active catalog profiles.
3. Require HTTPS documents hosted by Morningstar.
4. Download each source and record its SHA-256 plus HTTP metadata.
5. Extract PDF text with `pypdf`.
6. Collect conservative `0xNNNN` register observations with source page/text provenance.
7. Compare observations with the current `catalog/families/*.py` definitions.
8. Emit `report.json` and `report.md` without changing application code.
9. A developer reviews the source, edits the catalog manually, adds tests, and commits a
   `catalog-proposals/*.json` provenance record.
10. CI rejects catalog/source-index edits that do not include both provenance and test changes.

This intentionally favors false negatives over automatically turning noisy PDF extraction into
controller behavior.

## Commands

Validate source coverage and the checked-in catalog:

```bash
python -m tools.catalog_maintenance validate
```

Validate a proposed catalog edit against a base commit or branch:

```bash
python -m tools.catalog_maintenance validate --base-ref origin/main
```

Install PDF support and scan the current official source set:

```bash
python -m pip install -e '.[maintenance]'
python -m tools.catalog_maintenance scan
```

The default PDF cache remains under `docs/vendor/morningstar/cache/` and is ignored by Git. Reports
default to `catalog-maintenance-report/`, which is also ignored.

## Review provenance

A real catalog change needs a JSON record such as:

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

The source hash binds the code review to the exact vendor artifact that was inspected. The
maintenance report itself is not sufficient evidence because PDF extraction is heuristic.

## GitHub Actions

The catalog-maintenance workflow has two modes:

- pull requests: validate source coverage, run the provenance gate, and execute catalog tests;
- schedule/manual dispatch: download the official documents and upload the advisory JSON/Markdown
  report as an Actions artifact.

Scheduled scans do not push commits or open/merge pull requests. They surface evidence for a normal
reviewed code change.
