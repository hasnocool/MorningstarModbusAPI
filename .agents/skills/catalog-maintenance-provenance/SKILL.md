---
name: catalog-maintenance-provenance
description: Maintain official Morningstar source indexing, PDF extraction, discrepancy classification, catalog proposals, exact SHA provenance, and CI review gates without auto-generating unsafe runtime maps or higher-level inferences.
---

# Catalog maintenance and provenance

Use for `maintenance/`, `docs/vendor/morningstar/`, `catalog-proposals/`, source scanning, vendor-derived family
changes, or maintenance CI.

Read `docs/catalog-maintenance.md` and `catalog-proposals/README.md` first.

## Source policy

`docs/vendor/morningstar/sources.json` is authoritative.

- Fetch only approved HTTPS Morningstar sources through maintenance source policy.
- Record exact source artifact SHA-256 and available HTTP metadata.
- Full vendor PDFs are source material and are not committed/republished.
- Local cache/report outputs remain generated/ignored unless policy deliberately changes.

## Scanner philosophy

The scanner is evidence assistance, not code-generation authority. Morningstar documents contain multiple
address spaces and non-runtime hexadecimal material. Keep distinctions such as:

- runtime registers;
- EEPROM/configuration;
- coils/control actions;
- logged-data ranges;
- examples/conversion constants;
- reserved rows;
- alternate encodings.

Parse anchored table rows conservatively. Do not scan every hexadecimal token as telemetry.

## Comparison semantics

When comparing source observations with catalog profiles:

- account for full multi-word `RegisterSpec` spans;
- account for declared raw `RegisterBlock` coverage;
- do not require vendor symbols to equal semantic API names;
- keep holding/input/address-space semantics separate;
- treat actual conflicts as actionable discrepancies;
- treat valid runtime fields outside named coverage as optional coverage candidates;
- count/describe ignored non-runtime observations rather than calling them catalog bugs.

A large scanner count is not proof that thousands of edits are needed.

## Accepting a vendor-derived change

For a genuine map/source change:

1. inspect exact official source artifact/page/table;
2. update owning family/catalog declaration manually;
3. add/update deterministic tests;
4. add required `catalog-proposals/*.json` with exact source ID/SHA-256, affected profiles, reviewed changes, tests;
5. run provenance validation and catalog tests;
6. update catalog/system docs if public behavior changed.

Never accept a scanner observation solely because a confidence score is high.

## Higher-level inference boundary

Source provenance for a register/descriptor does not automatically validate a higher-level claim. For example:

- a ReadyEdge Connected Product descriptor proves what ReadyEdge reported, not necessarily independent physical
  identity or wiring;
- a shared Modbus endpoint does not prove electrical topology;
- a documented power register does not justify inventing battery net/load/generator flow;
- a documented logger does not justify an undocumented history-replay protocol.

Record limitations instead of guessing.

## Source updates

If an official URL/version changes, distinguish:

- same document moved;
- new revision with semantic differences;
- binary/hash change without semantic change;
- unavailable/deprecated source.

Do not silently repoint an old source ID at semantically different evidence.

## Maintenance CLI and CI

Inspect current `maintenance/` entry points for branch truth. Scanner workflows remain advisory and should never
push/merge catalog edits themselves. Catalog/source-index edits are expected to trigger provenance review gates;
do not bypass them by path tricks.

Finish with `testing-and-ci`.
