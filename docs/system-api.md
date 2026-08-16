# System/site API

MorningstarModbusAPI exposes a read-only system layer above immutable physical `controller_uid` identities. The system layer is intended for installations with one or more Morningstar controllers contributing to the same battery/solar site.

It does not replace controller-scoped APIs. Raw device/controller telemetry remains authoritative and keeps source provenance; system responses are normalized or derived views with explicit quality.

## Default system

Initialization creates one persistent default system:

```text
system_uid: sys_default
name: default
```

Every discovered physical controller is enrolled by immutable `controller_uid`, so IP/USB changes or identity-evidence promotion do not create a new system member.

```toml
[system]
default_uid = "sys_default"
default_name = "default"
```

No HTTP mutation routes are introduced.

## Routes

```http
GET /v1/systems
GET /v1/systems/metrics/catalog
GET /v1/systems/{system_uid}
GET /v1/systems/{system_uid}/controllers
GET /v1/systems/{system_uid}/component-graph
GET /v1/systems/{system_uid}/components
GET /v1/systems/{system_uid}/relationships
GET /v1/systems/{system_uid}/latest
GET /v1/systems/{system_uid}/power-flow
GET /v1/systems/{system_uid}/energy-ledger
GET /v1/systems/{system_uid}/energy
GET /v1/systems/{system_uid}/health
GET /v1/systems/{system_uid}/topology
GET /v1/systems/{system_uid}/events
GET /v1/systems/{system_uid}/history
GET /v1/systems/{system_uid}/stream
```

System identifiers can also be resolved by configured name.

## Normalized metrics

`GET /v1/systems/metrics/catalog` describes cross-product semantics separately from vendor-derived register definitions.

Examples:

| Metric | Aggregation/authority | Meaning |
| --- | --- | --- |
| `solar_input_power_w` | sum | independent controller PV contributions |
| `charge_output_power_w` | sum | controller charging output contributions |
| `battery_charge_current_a` | sum | controller-local charger currents |
| `battery_voltage_v` | median | representative shared-bus voltage |
| `battery_temperature_c` | median | representative available temperature |
| `daily_charge_wh` | sum | additive controller-local daily energy |
| `system_charge_current_a` | non-additive whole-system observation | already-aggregated system charging current |
| `battery_net_current_a` | non-additive whole-system observation | signed whole-system battery current |
| `system_load_current_a` | non-additive whole-system observation | whole-system load current |
| `load_voltage_v` | representative whole-system observation | voltage used for load-power derivation |
| `charge_state` | state set | controllers may be in different stages |
| `faults` / `alarms` | state set | health remains attributable to sources |

A controller contributes at most one preferred source register to each normalized semantic. Already-aggregated `SYSTEM_*` measurements are never summed across multiple reporters.

## Quality and conflict semantics

Aggregate responses expose source observations and contributor accounting. Typical quality values include `complete`, `partial`, and `empty`.

Whole-system measurements use stricter conflict-aware resolution. A single reporter can be accepted directly; close reporters may form a consensus; materially disagreeing reporters remain explicit `unknown` / `conflict` rather than being silently averaged or summed.

This distinction matters because controller-local charger current is additive while a vendor field named **system current** is already intended to represent the whole system.

## Component graph

The component graph models application-level electrical components and typed relationships above controller identities:

```http
GET /v1/systems/{system_uid}/component-graph
GET /v1/systems/{system_uid}/components
GET /v1/systems/{system_uid}/relationships
```

It supports a richer electrical/site model than transport topology alone. Transport topology does not prove electrical topology, so inferred relationships remain explicitly inferred.

See [`component-graph.md`](component-graph.md).

## Power flow

```http
GET /v1/systems/{system_uid}/power-flow
```

Power flow prefers authoritative source-backed measurements when available and derives additional values only when required inputs are defensible.

With source-backed GenStar whole-system currents, the API may derive:

- system charge power = `system_charge_current_a * battery_voltage_v`;
- battery net power = `battery_net_current_a * battery_voltage_v`;
- DC load power = `system_load_current_a * load_voltage_v`;
- current residual = charge current - battery net current - load current;
- whole-system DC power residual from corresponding derived powers.

Derived fields retain formula/input provenance. Charger output current is not treated as battery net current.

## Energy ledger

```http
GET /v1/systems/{system_uid}/energy-ledger
```

The ledger keeps source-backed energy/counters separate from unsupported estimates. It can prefer resolved whole-system daily charging energy when available and can expose aggregated external-source shunt charging energy.

Important rules:

- external-source shunt energy is **not** automatically labeled generator energy;
- native Ah counters remain Ah and are not converted into fake Wh using one instantaneous voltage;
- battery discharge Wh, load consumption Wh, conversion loss, and complete unaccounted-energy Wh remain unknown when evidence is insufficient;
- controller-local retained/integrated energy and system-wide authoritative counters are different evidence classes.

See [`system-metering.md`](system-metering.md) and [`component-graph.md`](component-graph.md).

## Authoritative GenStar system metering

Morningstar GenStar MPPT V03 provides source-backed whole-system measurements used by the normalized system layer, including:

- `SYSTEM_ICHARGE` -> `system_charge_current_a`;
- `SYSTEM_IBATT` -> `battery_net_current_a`;
- `SYSTEM_ILOAD` -> `system_load_current_a`;
- system battery/load Ah daily/resettable/total counters;
- controller-local battery/load Ah counters;
- optional aggregated-shunt charge/battery/load counters.

The system layer treats these as vendor-documented observations/counters with their documented units and signedness. It does not reinterpret Ah as Wh or assume an external-source shunt represents a generator.

See [`system-metering.md`](system-metering.md).

## History

System history uses normalized metric names rather than vendor register names:

```http
GET /v1/systems/sys_default/history?metric=battery_charge_current_a&resolution=5m
```

Supported resolutions include `raw`, `1m`, `5m`, `15m`, `1h`, and `1d`.

Raw points preserve `controller_uid`, `source_device_id`, semantic register name, timestamp, value, and unit. Bucketed points apply the semantic's declared aggregation rule and include contributor/quality metadata.

Large queries are bounded and should be narrowed or coarsened when needed.

## Energy and health summary views

```http
GET /v1/systems/{system_uid}/energy
GET /v1/systems/{system_uid}/health
```

`energy` provides the established normalized charging-energy/Ah view. `energy-ledger` is the richer component/electrical accounting surface and should be used when source authority, unknown quantities, and residuals matter.

`health` combines controller presence/status with normalized fault/alarm state while preserving underlying source evidence.

## Topology

```http
GET /v1/systems/{system_uid}/topology
```

Topology returns controller/transport relationships and includes component-graph information. Shared TCP host/port with different Modbus unit IDs can produce an inferred `modbus_tcp_multi_unit_endpoint` bridge candidate, but endpoint evidence alone is not proof of physical wiring.

## Unified event timeline

```http
GET /v1/systems/{system_uid}/events
```

The timeline can combine Modbus communication errors, charge-stage transitions, fault/alarm transitions, retained-history synchronization results, and supported external inbound events such as SNMP traps. Events retain source/provenance and do not modify controller state.

## Server-Sent Events

```http
GET /v1/systems/{system_uid}/stream
```

The read-only SSE stream emits `telemetry` when the normalized snapshot changes, `system_event` for newly observed timeline events, and heartbeat comments for idle connection health.

```bash
curl -N http://127.0.0.1:8080/v1/systems/sys_default/stream
```

## Retained-history and controller analytics relationship

System/site views are built above controller scopes. Controller-retained recovery and v0.6 controller reconciliation remain controller-scoped:

```http
GET /v1/controllers/{controller_uid}/history/coverage
GET /v1/controllers/{controller_uid}/history/gaps
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

System APIs do not erase the distinction between controller-local retained evidence, locally integrated controller energy, and source-backed whole-system counters.

## Optional SNMP trap ingestion

SNMP trap capture is disabled by default and is inbound-only. The listener does not perform SNMP GET/SET. It stores bounded source metadata/digest evidence rather than persisting opaque credentials/payloads.

## Read-only boundary

The system API adds aggregation, graph/topology, power flow, energy accounting, history, events, and streaming only. It does not expose Modbus register writes, coil writes, configuration changes, equalize/reset commands, ReadyBlock/shunt configuration, generator control, SNMP SET, or arbitrary write-capable protocol passthrough.
