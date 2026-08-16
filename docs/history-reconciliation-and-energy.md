# History reconciliation, coverage, and energy accounting

MorningstarModbusAPI keeps raw live polling history and controller-retained daily history as distinct provenance classes. The history analytics API joins those sources at read time so applications can answer continuity and energy questions without fabricating missing high-frequency samples.

## Coverage model

Use:

```http
GET /v1/controllers/{controller_uid}/history/coverage
```

Optional `from` and `to` parameters use `YYYY-MM-DD` with inclusive-start / exclusive-end semantics.

Coverage is deliberately day based. `realtime.coverage_percent` is the percentage of days containing at least one persisted `poll_samples` row. `daily_evidence.coverage_percent` is the percentage of days for which either persisted live samples exist or a complete controller-retained daily record exists.

This avoids claiming sample-level completeness when the API does not have enough information to prove how many high-frequency observations should have existed.

The response also reports:

- persisted sample count;
- completed controller-retained days;
- days recovered only from controller-retained history;
- days for which neither live nor complete retained evidence exists;
- the most recent retained-history synchronization result.

## Gap reconciliation

Use:

```http
GET /v1/controllers/{controller_uid}/history/gaps
```

A gap is a calendar day with zero persisted `poll_samples` rows. Consecutive days with the same reconciliation state are grouped into one interval.

States are:

- `recovered` — no persisted live sample exists, but a complete controller daily record is available;
- `partial` — no persisted live sample exists and only an incomplete controller daily record is available;
- `missing` — neither persisted live samples nor controller-retained daily evidence are available.

A recovered gap remains a daily summary. It is never expanded into synthetic one-second, five-second, or minute-level telemetry.

## Daily energy accounting

Use:

```http
GET /v1/controllers/{controller_uid}/energy/daily
```

The response keeps two independent energy measurements when available:

- `controller_reported_wh` from the controller's retained daily logger;
- `integrated_output_wh` calculated from persisted `output_power` samples.

The local integral uses trapezoidal integration. Adjacent persisted power samples are integrated only when their time separation is less than or equal to `max_gap_seconds` (default 300 seconds, configurable from 1 to 3600 seconds). Larger intervals are skipped instead of assuming that the last observed power continued through an outage.

For days where both sources exist the API reports `difference_wh` and `difference_percent`. This is useful for finding incomplete telemetry, persistence gaps, integration bias, or other discrepancies between the API's local observation history and the controller's own daily counter.

Each daily row includes provenance and quality fields such as persisted sample count, output-power sample count, integrated seconds, skipped between-sample seconds, controller-daily completeness, and source classes.

## Energy summary

Use:

```http
GET /v1/controllers/{controller_uid}/energy/summary
```

The summary aggregates controller-reported Wh and locally integrated output Wh over the requested range while retaining separate day counts for each source. It does not substitute one source for the other.

## Safety and provenance boundary

These endpoints are read only. They do not write controller registers, reset counters, trigger equalization, or mutate raw historical observations.

The analytics layer never inserts recovered daily records into `poll_samples`. Raw device ownership remains preserved under the immutable `controller_uid` scope, and controller-retained history remains identifiable as its own provenance source.
