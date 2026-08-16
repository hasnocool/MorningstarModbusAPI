---
name: catalog-and-intelligence
description: Maintain source-backed Morningstar product maps, decoders, firmware gates, identity evidence, capabilities, reserved ranges, and runtime confidence without fabricating device truth.
---

# Catalog and intelligence

Use for `catalog/` and `intelligence/` changes. Also load `catalog-maintenance-provenance` for vendor-derived map
edits.

## Rules

- Catalog family modules are declarative vendor-derived truth; runtime intelligence is connected-device evidence.
- Preserve holding/input function, complete word spans, decoders, units, enum/bitfields, firmware gates, and
  reserved ranges.
- Use shared scaling/decoder helpers.
- Unknown firmware remains conservative.
- Do not convert plausibility into fabricated identity or discard raw evidence.
- Keep product aliases/fingerprints conservative.

## Current product patterns

- GenStar may expose logger summaries and charge-energy/Ah counters, but public source material does not justify
  inventing a retained event-log record-reader protocol.
- ReadyEdge can expose 16 Connected Product descriptors. Treat product type, serial, bus, and Modbus address as
  inventory/relationship evidence. Reconcile strong identifiers such as serial with discovered physical
  controllers before adding a reported-only component.
- Distinguish SNMP polling support from asynchronous trap support by source documentation.

## Workflow

1. Identify the approved Morningstar source and exact field/range.
2. Update catalog blocks/registers/reserved ranges/capabilities in the family module.
3. Update decoders centrally when needed.
4. Add tests for address, word width, decoding, capabilities, reserved gaps, and firmware gates.
5. Add the required SHA-bound catalog proposal when the provenance gate applies.
6. Check downstream intelligence, system semantics, component reconciliation, and API exposure for unintended
   assumptions.
