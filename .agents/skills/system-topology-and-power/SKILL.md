---
name: system-topology-and-power
description: Design and maintain Morningstar system/site aggregation, quality-aware metrics, transport topology, ReadyEdge Connected Product reconciliation, component graphs, power flow, and provenance-aware energy accounting.
---

# System topology and power

Use for `systems/` and system-facing behavior that combines multiple physical controllers or relationships.
Also load `api-development` for routes, `catalog-and-intelligence` for vendor descriptor changes, and
`telemetry-history-storage` for history/event persistence.

## Layer model

Keep these layers distinct:

1. **Physical controller identity** — immutable `controller_uid` owned by `controllers/`.
2. **System membership/normalized metrics** — site aggregation over controllers.
3. **Transport topology** — observed endpoints/unit IDs and conservative bridge candidates.
4. **Component graph** — logical system/battery nodes, physical controllers, ReadyEdge-reported products, and
   evidence-backed relationships.
5. **Power/energy accounting** — observed measurements, defensible derivations, and explicit unknowns.

## System metric rules

- Define cross-product aliases/aggregation centrally in `systems/semantics.py`.
- Use metric-specific sum/median/max/min/state-set behavior.
- Record expected contributors, actual contributors, quality, freshness, and source observations.
- Prefer better validated aliases only when the semantic priority is explicit and tested.
- Never double-count the same physical controller because it appears through multiple endpoints/bridges.

## Topology and ReadyEdge rules

- A shared TCP endpoint with multiple unit IDs supports an inferred bridge candidate, not proof of wiring.
- ReadyEdge Connected Product descriptors are strong relationship/inventory evidence when source-backed.
- Reconcile a reported product to an existing physical controller using strong identity evidence, especially
  serial number. If not independently discovered, create a deterministic reported-only component rather than a
  fake physical controller UID.
- Preserve ReadyEdge host controller, slot, product type, serial, physical bus, Modbus address, and confidence in
  relationship evidence when available.
- Keep transport edges separate from electrical/component edges.

## Power-flow rules

Every quantity should carry provenance/classification such as `observed`, `derived`, or `unknown`.

Safe examples:

- sum source-backed controller solar input power across unique controllers;
- sum source-backed controller charge output power/current;
- derive controller conversion residual/efficiency when temporally compatible input and output are known.

Unsafe examples:

- treating charger current as battery net current;
- inventing aggregate load or generator power to close a balance;
- treating a logical battery bus as a measured shunt;
- deriving discharge energy without a valid discharge/current/energy measurement;
- using a component relationship as proof of current power direction/magnitude.

Unknown data should remain unknown until a source-backed measurement (for example a future shunt/BMS source)
exists.

## Energy ledger

The ledger is an accounting read model, not an optimizer or controller. Preserve the source measurement/counter
behind observed entries and the exact formula/inputs behind derived entries. Do not silently force a zero
residual or call an inferred residual a measurement.

## Tests

Cover multi-controller aggregation, partial quality, duplicate prevention, ReadyEdge serial reconciliation,
reported-only fallback, bridge-confidence semantics, power alias priority, derived efficiency/residual, and
unknown battery/load/generator fields.
