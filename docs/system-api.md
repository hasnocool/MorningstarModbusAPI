# System/site API

MorningstarModbusAPI exposes a read-only system layer above immutable physical `controller_uid` identities. The system layer is intended for installations with one or more Morningstar controllers that contribute to the same battery/solar site.

It does not replace controller-scoped APIs. Raw device/controller telemetry remains authoritative and keeps source provenance; system responses are derived views that normalize compatible measurements across controllers.

## Default system

Initialization creates one persistent default system:

```text
system_uid: sys_default
name: default
```

Every discovered physical controller is enrolled using `controller_uid`. Because membership uses the immutable controller identity, IP changes, USB path changes, and stronger identity evidence do not create a new system member.

The default identity can be changed in configuration:

```toml
[system]
default_uid = "sys_default"
default_name = "default"
```

No HTTP mutation routes are introduced. System membership is an internal/persistent read model rather than a remote controller-control surface.

## Routes

```http
GET /v1/systems
GET /v1/systems/metrics/catalog
GET /v1/systems/{system_uid}
GET /v1/systems/{system_uid}/controllers
GET /v1/systems/{system_uid}/latest
GET /v1/systems/{system_uid}/energy
GET /v1/systems/{system_uid}/health
GET /v1/systems/{system_uid}/topology
GET /v1/systems/{system_uid}/events
GET /v1/systems/{system_uid}/history
GET /v1/systems/{system_uid}/stream
```

System identifiers can also be resolved by the configured system name.

## Normalized metrics

`GET /v1/systems/metrics/catalog` describes the cross-product semantic layer. These semantics are deliberately separate from vendor-derived register definitions: Morningstar catalog modules remain source-backed product truth, while the system layer explains how compatible observations may be combined for application use.

Examples:

| Metric | Aggregation | Reason |
| --- | --- | --- |
| `solar_input_power_w` | sum | Controllers contribute independent PV power |
| `charge_output_power_w` | sum | Parallel chargers contribute power toward the battery system |
| `battery_charge_current_a` | sum | Parallel charging currents are additive |
| `battery_voltage_v` | median | Controllers normally observe the same battery bus; voltages must not be summed |
| `battery_temperature_c` | median | Represents available battery-temperature observations without adding them |
| `daily_charge_wh` | sum | Daily energy contributions are additive across independent chargers |
| `charge_state` | state set | Multiple controllers can be in different charge stages simultaneously |
| `faults` / `alarms` | state set | Health states remain attributable to their source controller |

A controller contributes at most one preferred source register to each normalized metric. This prevents double counting when a product exposes both a primary measurement and a fallback/filtered alias.

## Data-quality semantics

Every aggregate includes source observations and contributor accounting:

```json
{
  "value": 52.4,
  "unit": "A",
  "aggregation": "sum",
  "quality": "partial",
  "contributors": 2,
  "expected_contributors": 3,
  "oldest_observation_age_ms": 842.1,
  "sources": []
}
```

Quality values are:

- `complete` — every controller whose catalog can contribute that metric supplied a current observation;
- `partial` — at least one expected contributor is missing;
- `empty` — no current observations are available.

Expected contributors are capability-aware. A SureSine that does not expose a charge-controller PV metric is not counted as a missing PV contributor merely because it belongs to the same system.

## History

System history uses normalized metric names rather than vendor register names:

```http
GET /v1/systems/sys_default/history?metric=battery_charge_current_a&resolution=5m
```

Supported resolutions are:

- `raw`
- `1m`
- `5m`
- `15m`
- `1h`
- `1d`

Raw points preserve `controller_uid`, `source_device_id`, semantic register name, timestamp, value, and unit. Bucketed points apply the metric's declared aggregation rule after grouping observations by physical controller, and include quality/contributor metadata.

Like the controller history API, the system history endpoint is bounded. Large queries should be narrowed by time range or coarsened before retrying.

## Health and energy views

`GET /v1/systems/{system_uid}/energy` is a focused view of daily Ah/Wh and lifetime charging energy where those metrics are available.

`GET /v1/systems/{system_uid}/health` combines controller status with normalized alarm/fault states. A current fault produces a critical system status; alarms or unavailable controllers produce warning status; otherwise the status is `ok`.

This is an application summary, not a replacement for the underlying controller fault/alarm register evidence.

## Topology and Morningstar bridging

`GET /v1/systems/{system_uid}/topology` returns controller nodes, transport-endpoint nodes, and controller-to-endpoint links.

When several distinct physical controller UIDs are active through the same TCP host/port with different Modbus unit IDs, the API reports a `modbus_tcp_multi_unit_endpoint` bridge candidate. It is explicitly marked:

```json
{
  "confidence": "inferred"
}
```

This pattern is consistent with Morningstar Ethernet-to-EIA-485 Modbus bridging, but endpoint evidence alone is not proof of the physical wiring. The API therefore does not silently declare a bridge or merge the controller identities.

## Unified event timeline

`GET /v1/systems/{system_uid}/events` combines several read-only evidence sources into one timeline:

- Modbus communication errors;
- charge-stage transitions such as Absorption, Float, and Equalize;
- fault/alarm start and clear transitions;
- retained-history synchronization results;
- optional external events written by supported inbound listeners such as SNMP traps.

Derived events retain `controller_uid`, source, timestamp, and source-specific payload/provenance. The event view does not modify controller state.

## Server-Sent Events

`GET /v1/systems/{system_uid}/stream` provides a read-only SSE stream. It emits:

- `telemetry` when the normalized system snapshot changes;
- `system_event` for newly observed timeline events;
- periodic SSE comment heartbeats to keep idle connections healthy.

Example:

```bash
curl -N http://127.0.0.1:8080/v1/systems/sys_default/stream
```

The stream reads the same in-memory/persisted application view and does not increase controller write traffic. SSE is used instead of a bidirectional WebSocket because the public API remains observation-only.

## Retained-history providers

Controller-retained history now uses a provider registry. The existing TriStar MPPT LiveView daily logger is the first provider and preserves its existing API/behavior.

New Morningstar logger backends can implement the provider contract and be selected only when they explicitly support a discovered device. This is intended to accommodate verified GenStar hourly/daily/event logging without guessing undocumented register/indexing mechanisms or coupling product-specific parsers to watcher scheduling.

## Optional SNMP trap ingestion

SNMP trap capture is disabled by default:

```toml
[snmp]
enabled = false
host = "127.0.0.1"
port = 9162
max_packet_bytes = 65507
```

When enabled, an asyncio UDP listener records an event when a datagram arrives. It does **not** send SNMP GET/SET operations. To avoid persisting credentials or opaque network payloads, it stores source metadata, packet length, and a SHA-256 digest instead of the raw datagram/community string.

If exactly one active TCP controller is associated with the trap source IP, the event can be attributed to that `controller_uid`; otherwise candidate controller UIDs remain in event provenance and the event is left unassigned.

## Read-only boundary

The system API adds aggregation, history, events, topology, and streaming only. It does not expose:

- Modbus register writes;
- coil writes;
- configuration changes;
- equalize/reset commands;
- SNMP SET;
- arbitrary protocol passthrough.

This keeps the service usable as a telemetry and observability boundary even when connected to Morningstar transports that are capable of forwarding write requests.
