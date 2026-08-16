# Authoritative system metering and energy accounting

MorningstarModbusAPI can use source-backed GenStar whole-system current and counter measurements to make the system power-flow and energy-ledger views more complete without inventing missing electrical quantities.

This layer remains strictly read-only. It does not configure shunts, change ReadyBlock roles, control generators, write Modbus registers, or infer a complete balance from incomplete telemetry.

## GenStar whole-system current measurements

Morningstar GenStar MPPT MODBUS Specification V03 documents three instantaneous system currents:

- `SYSTEM_ICHARGE` at `0x0063` — system charging current;
- `SYSTEM_IBATT` at `0x0064` — system battery current;
- `SYSTEM_ILOAD` at `0x0065` — system load current.

The normalized system layer exposes them as:

- `system_charge_current_a`;
- `battery_net_current_a`;
- `system_load_current_a`.

These are deliberately separate from additive controller-local charger current. A Morningstar value named *system current* is treated as an observation of an already-aggregated electrical quantity and is never summed across controllers.

When more than one controller reports the same whole-system semantic, the power service accepts a single reporter directly or a close consensus. Materially disagreeing reporters produce `status=unknown`, `quality=conflict`, and preserve their source observations instead of silently averaging potentially different electrical systems.

## Derived instantaneous power

When the required source-backed values are present, `/v1/systems/{system_uid}/power-flow` may derive:

- system charge power = `system_charge_current_a * battery_voltage_v`;
- battery net power = `battery_net_current_a * battery_voltage_v`;
- DC load power = `system_load_current_a * load_voltage_v`;
- system current residual = `system_charge_current_a - battery_net_current_a - system_load_current_a`;
- whole-system DC residual from the corresponding derived powers.

Derived values retain their formula and input metric names. No direction label is invented beyond the signed measurement supplied by Morningstar.

Controller input/output residual and conversion efficiency remain separate controller-side calculations. They must not be confused with the whole-system DC balance.

## Completed GenStar V03 counters

The GenStar profile includes documented system and internal battery/load counters:

- `0x02DC-0x02E7` — system battery and load Ah daily/resettable/total;
- `0x02F4-0x02FF` — controller-local battery and load Ah daily/resettable/total.

Signed battery resettable/total counters use signed 32-bit `*0.1` decoding because the vendor map specifies signed integer semantics.

## Aggregated shunt counters

V03 also documents the read-only Aggregated Shunt Counters block at `0x227C-0x2293`. The API models this block as optional because useful values depend on compatible shunt/ReadyBlock configuration and firmware support.

The block includes source-backed daily/resettable/total counters for:

- aggregated external-source shunt charge Ah;
- aggregated external-source shunt charge kWh;
- aggregated shunt battery net Ah;
- aggregated shunt load Ah.

These retained counters belong in the energy/counter model, not in a synthetic high-frequency telemetry loop.

## Energy-ledger behavior

The energy ledger prefers a resolved Morningstar whole-system daily charge kWh counter when available, converting kWh to Wh with an explicit formula. It can also expose aggregated external-source shunt charge kWh as `external_source_charge_wh`.

External-source shunt energy is **not** labeled as generator energy. The measured source may be a generator, another charger, a fuel cell, or another DC source.

Native Ah counters remain Ah. The API does not multiply a daily Ah total by one instantaneous voltage and call the result daily Wh. Therefore these remain explicitly unknown unless separate energy evidence exists:

- battery discharge Wh;
- load consumption Wh;
- generator-generated Wh;
- conversion-loss Wh;
- complete unaccounted-energy Wh.

The source-backed Ah counters remain available for diagnostics and future time-resolved reconciliation.

## Relationship to v0.6 controller energy analytics

System metering and controller energy analytics answer different questions and must not be conflated.

Controller analytics:

```http
GET /v1/controllers/{controller_uid}/energy/daily
GET /v1/controllers/{controller_uid}/energy/summary
```

compare controller-retained daily `charge_wh` with a local integration of that controller's persisted `output_power` observations. They are useful for continuity and telemetry-quality checks.

System metering:

```http
GET /v1/systems/{system_uid}/power-flow
GET /v1/systems/{system_uid}/energy-ledger
```

uses normalized system semantics and source-backed whole-system counters where available. A system-wide GenStar counter is not replaced by the sum of controller-local estimates, and a controller-local integral is not promoted to a vendor-reported whole-system value.

When both evidence classes exist, applications should compare them while retaining their scope and provenance.

## Measurement authority and future expansion

Future ReadyBMS, ReadyShunt role metadata, and ReadyEdge live-product telemetry should feed the same normalized semantics instead of bypassing them.

Important rules remain:

- BMS/shunt authority must be based on documented product behavior, not arbitrary numeric priority scores;
- transport topology is not electrical topology;
- a logical battery bus does not prove physical wiring;
- charger output current is not battery net current;
- conflicting independent observations should be surfaced, not hidden;
- retained native counters and high-frequency integrations should be compared rather than one silently replacing the other.

## Provenance

The GenStar declarations are tied to the reviewed `genstar-mppt-modbus-v03` source and its catalog-maintenance SHA-256 proposal record. No vendor PDF is committed to the repository.

See [`system-api.md`](system-api.md), [`component-graph.md`](component-graph.md), and [`history-reconciliation-and-energy.md`](history-reconciliation-and-energy.md).
