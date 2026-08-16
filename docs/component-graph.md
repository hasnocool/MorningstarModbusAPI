# System component graph, power flow, and energy ledger

MorningstarModbusAPI exposes a read-only electrical/component view above the immutable physical-controller inventory. The graph is evidence-aware: it distinguishes configured membership, catalog-derived capabilities, Morningstar-reported connected products, source-backed whole-system metering, and logical aggregation nodes instead of presenting inferred wiring as physical fact.

## Routes

```http
GET /v1/systems/{system_uid}/component-graph
GET /v1/systems/{system_uid}/components
GET /v1/systems/{system_uid}/relationships
GET /v1/systems/{system_uid}/power-flow
GET /v1/systems/{system_uid}/energy-ledger
```

`GET /v1/systems/{system_uid}/topology` also embeds the component graph alongside transport-endpoint topology and conservative bridge candidates.

## Component identity

Physical Morningstar devices continue to use immutable `controller_uid`. A ReadyEdge Connected Product is not automatically created as a second controller object.

When ReadyEdge reports a Connected Product serial that matches an existing physical controller, the graph links the gateway to that controller. If a reported product has not been independently discovered, the graph may create a deterministic `connected_product` component whose confidence remains `reported` until stronger identity evidence exists.

## ReadyEdge Connected Product inventory

ReadyEdge source-backed descriptors can expose per-slot product type, serial number, physical bus, and Modbus address. Expansion/reserved words remain explicitly reserved rather than receiving speculative names.

The component graph uses compact configured-product descriptors instead of indiscriminately polling every product-specific live-data window, keeping normal polling bounded while preserving stable topology evidence.

## Logical battery bus

Every system graph contains a logical `battery_bus` aggregation component. Charge-controller profiles with source-backed charging telemetry may have `charges` relationships to this node.

The logical bus is an application aggregation point, not proof of physical wiring. Source-backed shunt/BMS/system-current evidence can strengthen the electrical model without changing physical controller identity.

## Power-flow view

```http
GET /v1/systems/{system_uid}/power-flow
```

Power flow combines normalized current measurements and conservative derived values. Source authority matters:

- controller-local PV/input power and charge-output power can contribute additively where semantics allow;
- controller-local charger current is additive across independent chargers;
- source-backed Morningstar `SYSTEM_*` currents are already whole-system observations and are **not** summed across reporters;
- conflicting whole-system reporters remain explicit conflicts rather than being silently averaged.

### Controller-side power

Where both controller input and output power exist, the service can calculate controller-side residual and conversion efficiency. These are labeled `derived` and retain formula/input provenance.

### Source-backed GenStar whole-system power

With GenStar V03 system currents and required voltages, the service may derive:

- system charge power = `system_charge_current_a * battery_voltage_v`;
- battery net power = `battery_net_current_a * battery_voltage_v`;
- DC load power = `system_load_current_a * load_voltage_v`;
- system current residual = `system_charge_current_a - battery_net_current_a - system_load_current_a`;
- whole-system DC residual from corresponding power terms.

This closes an important earlier gap: battery net current is no longer inferred from charger current when authoritative system battery current is available. When it is not available, the field remains unknown rather than being guessed.

See [`system-metering.md`](system-metering.md).

## Energy ledger

```http
GET /v1/systems/{system_uid}/energy-ledger
```

The ledger publishes normalized energy/counter fields with explicit observed/derived/unknown status and source provenance.

It can now prefer a resolved source-backed whole-system daily charge-energy counter where supported. It can also expose aggregated external-source shunt charge energy without labeling that source as a generator.

Native Ah counters remain Ah. The API does **not** multiply a daily Ah counter by one instantaneous voltage and claim daily Wh.

Therefore fields remain unknown when evidence is insufficient, including as applicable:

- battery discharge Wh;
- load consumption Wh;
- generator-generated Wh;
- conversion-loss Wh;
- complete unaccounted-energy Wh.

Unknown is an intentional data-quality state, not a missing implementation placeholder to be filled with speculation.

## Controller energy analytics vs system energy ledger

Controller v0.6 energy analytics:

```http
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

compare one controller's retained daily `charge_wh` against local integration of persisted `output_power` observations.

The system energy ledger has a different scope: it models site/system energy and prefers source-backed whole-system counters when available. A controller-local integral is not promoted into an authoritative system counter, and a whole-system counter is not replaced by a sum of narrower-scope estimates.

See [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).

## TriStar input-power reconciliation

The system-level solar input power semantic prefers the reconciled operational `input_power` when a profile provides both it and a less reliable raw `input_power_reported` estimate. Raw reported telemetry remains available on controller APIs for diagnostics and evidence.

## Evidence hierarchy

The graph/power/ledger layer follows these rules:

- vendor-documented measurements outrank unsupported inference;
- transport topology does not prove electrical topology;
- logical components do not assert undocumented physical wiring;
- whole-system observations are not summed as if they were controller-local contributions;
- materially conflicting reporters remain conflicts;
- retained counters and high-frequency integrations may be compared, but neither silently replaces the other;
- units are preserved: Ah does not become Wh without defensible energy evidence.

## Read-only boundary

These routes do not expose configuration mutation or device control. They do not add Modbus writes, coil writes, equalization/reset commands, ReadyBlock/shunt configuration, generator controls, SNMP SET, or arbitrary protocol passthrough.

See [`system-api.md`](system-api.md) and [`system-metering.md`](system-metering.md).
