---
name: catalog-maintenance-provenance
description: Maintain official Morningstar source scanning and SHA-bound catalog provenance so vendor-derived changes are reviewable, reproducible, and never guessed from incomplete documentation.
---

# Catalog maintenance and provenance

`docs/vendor/morningstar/sources.json` is the approved source index. `maintenance/` owns scanner/provenance logic.

## Rules

- Retrieve only approved Morningstar HTTPS sources through the maintenance workflow.
- Do not republish complete vendor PDFs in the repository.
- Treat scanner output as advisory; never auto-rewrite catalog family modules.
- Distinguish runtime telemetry from configuration/control/log/example/reserved/alternate-encoding material.
- Catalog/source-index edits require a reviewed `catalog-proposals/*.json` record when the gate applies.
- Bind the proposal to the exact source SHA-256 and list affected profiles/changes/tests.
- Do not guess undocumented event-log indexing, component relationships, register meanings, or measurement units.

When adding ReadyEdge/GenStar/component-related coverage, verify the vendor document actually supports the field
used by downstream system topology or power logic. Provenance of a descriptor does not automatically validate a
higher-level physical inference.
