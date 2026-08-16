# System component graph, power flow, and energy ledger

MorningstarModbusAPI exposes a read-only electrical/component view above the existing immutable physical-controller inventory. The graph is evidence-aware: it distinguishes configured membership, catalog-derived capabilities, Morningstar-reported connected products, and logical aggregation nodes instead of presenting inferred wiring as physical fact.

## Routes

```http
GET /v1/systems/{system_uid}/component-graph
GET /v1/systems/{system_uid}/components
GET /v1/systems/{system_uid}/relationships
GET /v1/systems/{system_uid}/power-flow
GET /v1/systems/{system_uid}/energy-ledger
```

`GET /v1/systems/{system_uid}/topology` also embeds the component graph alongside the existing transport-endpoint topology and conservative Modbus/TCP bridge candidates.

## Component identity

Physical Morningstar devices continue to use their immutable `controller_uid`. A ReadyEdge Connected Product is therefore not automatically created as a second controller object.

When ReadyEdge reports a Connected Product serial number that matches an existing physical controller, the graph links the ReadyEdge gateway to that existing `controller_uid` with a `monitors` relationship. This preserves one physical identity while adding ReadyEdge's source-backed slot, bus, and Modbus-address evidence.

If a ReadyEdge slot reports a product that has not been independently discovered by the service, the graph creates a deterministic `connected_product` component. Its confidence remains `reported`; it is not promoted to a physical controller until independent controller identity evidence exists.

## ReadyEdge Connected Product inventory

ReadyEdge MODBUS Specification V01 documents 16 configurable Connected Product slots. The source-backed catalog now reads their descriptor fields in two optional contiguous blocks and exposes, per slot:

- product type;
- eight-byte serial number;
- packed physical bus and Modbus address.

The bus/address word is decoded by the component layer: the physical-port identifier is the high byte and the Modbus device address is the low byte. The remaining documented expansion words stay explicitly reserved rather than being assigned speculative semantic names.

The initial component graph deliberately uses the compact configured-product descriptors rather than polling every product-specific live-data window. This keeps the normal ReadyEdge polling cost bounded while establishing stable component identity and topology evidence.

## Logical battery bus

Every system graph contains one `battery_bus` logical component. Charge-controller profiles with source-backed charging telemetry may have a `charges` relationship to this node.

The node is an aggregation point for normalized system semantics; it is not a claim that every controller is physically wired to one particular conductor, battery, or shunt. Future source-backed shunt/BMS observations can strengthen this model without changing controller identity.

## Power-flow view

`GET /v1/systems/{system_uid}/power-flow` reconciles current normalized measurements. It currently exposes source-backed controller-side values such as:

- solar/PV input power;
- charging output power;
- charging current;
- battery voltage;
- battery SOC when available.

It also calculates controller-side input/output residual and conversion efficiency when both power measurements exist. These calculations are labeled `derived` and include their formula.

The service does **not** infer battery net current from charger current, because simultaneous battery loads can make that assumption false. Likewise, generator power, inverter/load power, whole-system residual, and battery net power remain explicitly `unknown` until a source-backed measurement such as ReadyShunt/BMS/load telemetry is available.

## Energy ledger

`GET /v1/systems/{system_uid}/energy-ledger` gives normalized energy-flow fields with explicit observed/derived/unknown status. The first implementation can populate battery charging energy and associated charge counters from supported controller totals. If only daily kWh is available, Wh may be derived with the formula shown in the response.

Fields that cannot yet be measured are present but remain `unknown`, including:

- solar generated Wh when no source-backed energy counter exists;
- generator generated Wh;
- battery discharge Wh;
- load consumption Wh;
- conversion losses Wh;
- unaccounted energy Wh.

This is intentional. The ledger is designed to become more complete as source-backed ReadyShunt, ReadyBMS, inverter/load, or other verified measurements are added; it does not manufacture a complete balance from incomplete telemetry.

## TriStar input-power reconciliation

The system-level `solar_input_power_w` metric prefers the profile's reconciled operational `input_power` when both it and the raw `input_power_reported` estimate are present. This preserves the earlier TriStar MPPT quality correction at the system/power-flow layer instead of reintroducing an unreliable raw estimate through aggregation.

Raw reported telemetry remains available on the controller API for evidence and diagnostics.

## Read-only boundary

These routes do not expose configuration mutation or device control. They do not add Modbus writes, coil writes, equalization/reset commands, generator controls, SNMP SET, or arbitrary protocol passthrough.
