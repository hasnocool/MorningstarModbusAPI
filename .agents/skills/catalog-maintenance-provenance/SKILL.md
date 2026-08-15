---
name: catalog-maintenance-provenance
description: Maintain official Morningstar source indexing, PDF extraction, discrepancy/coverage classification, catalog proposals, SHA provenance, and CI review gates without auto-generating unsafe runtime maps.
---

# Catalog maintenance and provenance

Use for `maintenance/`, `docs/vendor/morningstar/`, `catalog-proposals/`, source scanning, vendor-derived family
changes, or maintenance CI.

Read `docs/catalog-maintenance.md` and `catalog-proposals/README.md` first.

## Source policy

`docs/vendor/morningstar/sources.json` is the authoritative source index.

- Fetch only approved HTTPS Morningstar sources through the maintenance source policy.
- Record exact source artifact SHA-256 and available HTTP metadata.
- Full vendor PDFs are source material and are not committed/republished in the repository.
- Local cache/report outputs remain generated/ignored unless the project deliberately changes that policy.

## Scanner philosophy

The scanner is evidence assistance, not code generation authority.

Morningstar documents contain multiple numeric address spaces and non-runtime hex material. Keep distinctions such
as:

- runtime registers;
- EEPROM/configuration;
- coils/control actions;
- logged-data ranges;
- examples/conversion constants;
- reserved rows;
- alternate encodings.

Parse anchored table rows conservatively. Do not regress to scanning every `0xNNNN` token and treating it as
telemetry.

## Comparison semantics

When comparing observations with catalog profiles:

- account for full multi-word `RegisterSpec` spans;
- account for declared raw `RegisterBlock` coverage;
- do not require vendor symbols to equal semantic API names;
- keep holding/input/address-space semantics separate;
- treat actual conflicts as actionable discrepancies;
- treat valid runtime fields outside named/active coverage as optional coverage candidates;
- count/describe ignored non-runtime observations instead of reporting them as catalog bugs.

A large scanner count is not proof that thousands of catalog edits are needed.

## Accepting a real vendor-derived change

For a genuine map/source change:

1. inspect the exact official source artifact/page/table;
2. update the owning family/catalog declaration manually;
3. add or update deterministic tests;
4. add a `catalog-proposals/*.json` provenance record containing the exact source ID/SHA-256, affected profiles,
   reviewed changes, and tests;
5. run provenance validation and catalog tests;
6. update catalog docs/coverage if public behavior changed.

Never accept a scanner observation solely because its confidence score is high.

## Source updates

If an official URL/version changes, distinguish:

- same document moved to a new URL;
- new revision with actual register differences;
- changed binary/hash with no semantic change;
- unavailable/deprecated source.

Do not silently point an old `source_id` at semantically different evidence without review.

## Maintenance CLI

Inspect `maintenance/__main__.py` for branch truth. Established workflows include source/catalog validation and
advisory scans with optional cache reuse. The scanner should never push/merge catalog edits itself.

## CI

Catalog/source-index edits are expected to trigger the provenance review gate and tests. Do not bypass the gate
by renaming files or excluding paths.

Finish with `testing-and-ci`.
