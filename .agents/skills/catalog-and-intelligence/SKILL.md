---
name: catalog-and-intelligence
description: Extend or correct Morningstar product profiles, register maps, decoding/scaling, firmware gates, verification metadata, device identity, confidence, capabilities, and plausibility validation.
---

# Catalog and intelligence

Use when work touches `catalog/`, `intelligence/`, product detection, register definitions, firmware compatibility,
capabilities, or profile validation.

## Keep two concepts separate

**Catalog** = declarative product/vendor truth and compatibility rules.

**Device intelligence** = what the runtime believes about a specific connected endpoint based on identification,
metadata, firmware, observed capabilities, validation, and evidence.

Do not put runtime confidence into family definitions or vendor register tables into resolver heuristics when a
catalog declaration is the correct abstraction.

## Catalog workflow

Before editing a family:

1. Read `docs/device-catalog.md`.
2. Inspect `catalog/types.py`, `profile.py`, `registry.py`, `scaling.py`, `compatibility.py`, and the target family.
3. Identify the target source ID in `docs/vendor/morningstar/sources.json`.
4. If the change is vendor-derived, also load `catalog-maintenance-provenance`.
5. Inspect existing catalog tests before creating new conventions.

For registers:

- preserve exact numeric address and Modbus function;
- model multi-word fields with `words`, not separate fake fields unless the vendor semantics require it;
- use shared decoders/scaling;
- give semantic stable API names while preserving source provenance in docs/proposals;
- set units/categories/enums/bitfields only when supported;
- distinguish optional blocks and cached stable metadata;
- use `since_firmware` / `until_firmware` for documented compatibility rather than conditionals in watcher/API;
- keep `catalog_revision` and firmware verification ranges evidence-based.

## Semantic names versus vendor labels

The public semantic name does not have to textually equal the vendor symbol. For example, a compact vendor
identifier can legitimately map to a descriptive snake_case API field. Do not treat spelling differences alone as
register conflicts.

Maintenance comparison already accounts for this distinction; do not regress it.

## Intelligence resolution

Inspect the current staged resolver. Typical evidence can include:

- Modbus Device Identification;
- catalog aliases/model text;
- conservative family fingerprints;
- targeted metadata reads;
- firmware/hardware revision;
- serial/model evidence;
- negotiated capabilities;
- post-poll plausibility validation.

Rules:

- confidence must reflect actual evidence, not desired product selection;
- do not force a specific profile because a device is "probably" one model;
- newer firmware beyond verified ranges should remain explicitly unverified/conservative;
- missing optional metadata may reduce confidence without invalidating valid raw telemetry;
- implausible decoded values can invalidate the selected profile while raw values remain available.

## Verification registry

Catalog verification evidence is independent of vendor family definitions. Keep document/software/fixture/
physical-hardware statuses separate. Only update physical-hardware evidence after reviewed physical capture.

Do not encode a synthetic fixture as hardware proof.

## Adding a family

A coherent new family normally includes:

- family module/profile;
- registry exposure and aliases/detection priority;
- appropriate read blocks and named register specs;
- scaling/decoder additions only if reusable helpers lack the required type;
- conservative discovery/intelligence support if needed;
- source/provenance record for vendor-derived map data;
- focused catalog/intelligence tests;
- docs coverage/status update.

Do not add product-specific branches to API/transport to make a family work.

## Validation

Run target catalog/intelligence tests first, then `testing-and-ci`. If changing vendor-derived truth, ensure the
catalog provenance workflow also passes.
