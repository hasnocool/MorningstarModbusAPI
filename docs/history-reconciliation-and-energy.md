# History reconciliation, coverage, and energy accounting

MorningstarModbusAPI v0.6 keeps raw live polling history and controller-retained daily history as distinct provenance classes, then joins those sources **at read time** so applications can answer continuity and energy-quality questions without fabricating missing high-frequency samples.

## Evidence classes

| Evidence | Scope | Meaning |
| --- | --- | --- |
| `live_poll` | timestamped local observation | a Modbus observation was persisted by the API |
| `controller_internal_logger` | controller daily summary | the controller retained a daily record |
| local energy integration | derived controller-day estimate | persisted `output_power` samples integrated across accepted time gaps |
| system metering | system/site evidence | normalized or vendor-reported whole-system measurements/counters |

These sources are intentionally not interchangeable.

## Coverage model

```http
GET /v1/controllers/{controller_uid}/history/coverage
```

Optional `from` and `to` parameters use `YYYY-MM-DD` with inclusive-start / exclusive-end semantics.

Coverage is deliberately day based:

- `realtime.coverage_percent` — percentage of days containing at least one persisted `poll_samples` row;
- `daily_evidence.coverage_percent` — percentage of days covered by persisted live samples or a complete retained daily record;
- `recovered_days` — complete retained evidence exists but persisted live samples do not;
- `missing_days` — neither source provides complete day evidence.

This is **evidence coverage**, not a claim that every expected five-second/minute sample exists.

The response also exposes the most recent retained-history synchronization result so applications can distinguish "no retained record exists" from "retained-history synchronization has not succeeded recently."

## Gap reconciliation

```http
GET /v1/controllers/{controller_uid}/history/gaps
```

A gap is a calendar day with zero persisted `poll_samples` rows. Consecutive days with the same reconciliation state are grouped into one interval.

| State | Meaning |
| --- | --- |
| `recovered` | no persisted live sample exists, but a complete controller daily record is available |
| `partial` | no persisted live sample exists and only incomplete retained daily evidence is available |
| `missing` | neither persisted live samples nor retained daily evidence are available |

Example interpretation:

```json
{
  "from": "2026-08-11",
  "to": "2026-08-13",
  "duration_days": 2,
  "status": "recovered",
  "recoverability": "controller_daily",
  "controller_record_count": 2
}
```

This means two days have daily controller evidence despite no persisted local samples. It does **not** mean intra-day samples were reconstructed.

## Daily energy accounting

```http
GET /v1/controllers/{controller_uid}/energy/daily
```

The response keeps independent measurements separate:

- `controller_reported_wh` — controller-retained daily charging energy;
- `integrated_output_wh` — local trapezoidal integration of persisted `output_power` observations.

### Gap-bounded integration

Adjacent power samples are integrated only when their separation is less than or equal to `max_gap_seconds`.

Default:

```text
max_gap_seconds=300
```

Accepted API range:

```text
1..3600 seconds
```

If two observations are farther apart than the threshold, that interval contributes **zero assumed energy** to the local integral and is counted as skipped time. This avoids pretending the previous power value continued through an outage.

### Discrepancy metrics

When both sources exist:

```text
difference_wh = integrated_output_wh - controller_reported_wh
difference_percent = difference_wh / controller_reported_wh * 100
```

A discrepancy can indicate incomplete persistence, long skipped intervals, sampling/integration bias, source resolution differences, or another data-quality issue. It is diagnostic evidence, not automatically proof that either source is wrong.

### Quality fields

Daily responses expose fields such as:

- persisted sample count;
- `output_power` sample count;
- integrated seconds;
- skipped between-sample seconds;
- maximum accepted gap;
- whether a controller daily record exists;
- whether that record is complete;
- provenance source classes.

These fields should accompany energy values in dashboards so users can distinguish a well-supported estimate from a sparse one.

## Energy summary

```http
GET /v1/controllers/{controller_uid}/energy/summary
```

The summary aggregates controller-reported Wh and locally integrated output Wh over the requested day range while retaining separate source/day counts. It does not substitute one source for the other.

## Relationship to retained-history backfill

Backfill is the acquisition layer; reconciliation is the interpretation layer:

```text
successful reconnect
      |
      v
retained-history provider
      |
      v
controller_daily_history
      |
      +---------------------------+
                                  v
persisted poll history ------> reconciliation analytics
                                  |-- coverage
                                  |-- gaps
                                  |-- controller daily energy
                                  `-- local integration/discrepancy
```

See [`controller-history-backfill.md`](controller-history-backfill.md).

## Relationship to system/site energy accounting

Controller energy analytics are controller-scoped. System/site power flow and energy ledger are separate higher-level views:

```http
GET /v1/systems/{system_uid}/power-flow
GET /v1/systems/{system_uid}/energy-ledger
```

Where source-backed whole-system GenStar counters exist, the system layer can treat them as authoritative whole-system observations. It does not silently replace those counters with controller-local integrations or sums that have different scope.

See [`system-api.md`](system-api.md) and [`system-metering.md`](system-metering.md).

## Safety and provenance boundary

These endpoints are read only. They do not write controller registers, reset counters, trigger equalization, configure shunts/ReadyBlocks, or mutate raw historical observations.

The analytics layer never inserts recovered daily records into `poll_samples`. Raw storage ownership remains preserved under immutable `controller_uid` scope, and retained daily history remains identifiable as its own evidence source.
