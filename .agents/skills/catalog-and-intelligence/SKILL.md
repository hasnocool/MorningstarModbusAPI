---
name: catalog-and-intelligence
description: Extend or correct Morningstar product profiles, register maps, decoding/scaling, firmware gates, verification metadata, device identity, capabilities, ReadyEdge descriptors, and plausibility evidence.
---

# Catalog and intelligence

Use when work touches `catalog/`, `intelligence/`, product detection, register definitions, firmware compatibility,
capabilities, profile validation, or source-backed Connected Product metadata.

## Keep two concepts separate

**Catalog** = declarative product/vendor truth and compatibility rules.

**Device intelligence** = what runtime believes about a specific connected device/endpoint based on identification,
metadata, firmware, observed capabilities, validation, and evidence.

Do not put runtime confidence into family definitions or vendor register tables into resolver heuristics when a
catalog declaration is the correct abstraction.

## Catalog workflow

Before editing a family:

1. Read `docs/device-catalog.md` and the approved source index.
2. Inspect `catalog/types.py`, `catalog/profile.py`, registry/scaling/compatibility helpers, and the target family.
3. Identify the target source ID in `docs/vendor/morningstar/sources.json`.
4. If vendor-derived, also load `catalog-maintenance-provenance`.
5. Inspect existing catalog/intelligence tests before creating a new convention.

For registers:

- preserve exact numeric address and Modbus function;
- model multi-word fields with `words` rather than fake single-word fields;
- use shared decoders/scaling;
- give stable semantic names while preserving vendor/source provenance;
- set units/categories/enums/bitfields only when source-backed;
- distinguish optional blocks, cached stable metadata, and reserved spans;
- use firmware gates rather than product-version conditionals in runtime/API;
- keep catalog revision and firmware verification ranges evidence-based.

## Semantic names versus vendor labels

A public semantic name need not textually equal a compact vendor symbol. Do not treat spelling differences alone
as register conflicts. Comparison tooling must reason about addresses, spans, functions, and declared semantics.

## Intelligence resolution

Inspect the current staged resolver. Evidence can include:

- Modbus Device Identification;
- catalog aliases/model text;
- conservative family fingerprints;
- targeted metadata reads;
- firmware/hardware revision;
- serial/model evidence;
- capabilities;
- post-poll plausibility validation.

Rules:

- confidence reflects actual evidence, not desired profile selection;
- do not force a profile because a device is "probably" one model;
- newer firmware beyond verified ranges remains explicit/conservative;
- missing optional metadata can reduce confidence without invalidating valid raw telemetry;
- implausible decoded values can invalidate a selected semantic interpretation while raw observations remain.

## Physical identity versus product identity

Catalog/intelligence may provide serial/model evidence used by `controllers/`, but immutable physical identity is
owned by controller scope as `controller_uid`. Do not make endpoint IDs or a product-family guess substitute for
that identity.

## ReadyEdge Connected Product inventory

Current source-backed ReadyEdge coverage can model 16 Connected Product descriptor slots including product type,
serial, physical bus, and Modbus address. Treat those fields as inventory/relationship evidence:

- use the documented enum/type and descriptor layout;
- preserve eight-byte serial and packed bus/address decoding as documented;
- preserve documented reserved expansion words as reserved;
- expose capability metadata only when source-backed;
- reconcile a ReadyEdge report to an independently discovered physical controller only with strong identity
  evidence such as matching serial;
- a product-type match alone is not physical identity and does not prove electrical wiring.

## GenStar and SNMP cautions

Source-backed GenStar coverage may include logger summaries and energy/Ah counters. Do not invent a retained
event-log index/replay mechanism absent from public documentation. Distinguish products supporting SNMP polling
from products documented to emit asynchronous traps.

## Verification registry

Catalog verification evidence is independent of vendor family definitions. Keep document/software/fixture/
physical-hardware statuses separate. Only promote physical-hardware evidence after reviewed physical capture.

## Adding a family

A coherent family addition normally includes:

- family module/profile;
- registry exposure/aliases/detection priority;
- safe read blocks and named register specs;
- shared decoder additions only if required;
- conservative discovery/intelligence support if needed;
- source/provenance record for vendor-derived map data;
- focused catalog/intelligence tests;
- docs coverage/status update.

Do not add product-specific branches to API/transports to make a family work.

## Validation

Run focused catalog/intelligence tests, downstream system/component tests when relevant, then `testing-and-ci`.
For vendor-derived truth ensure the catalog provenance workflow also passes.
