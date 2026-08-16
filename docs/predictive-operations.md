# Predictive operations

MorningstarModbusAPI can turn its normalized local history into an offline-first operational outlook without weakening the project's read-only boundary.

The forecasting layer is deliberately conservative: it reports percentile bands, evidence coverage, training-day counts, model names, and provenance instead of presenting a single deterministic prediction as truth. It does not write controller settings, alter charge stages, acknowledge alarms, or require an Internet connection.

## System forecast

```http
GET /v1/systems/{system_uid}/forecast
```

The system forecast combines two evidence classes:

1. a local time-of-day solar-input forecast built from normalized `solar_input_power_w` history;
2. controller charge-cycle outlooks built from source-backed `charge_state` history.

The first model is `local-time-of-day-percentile-v1`. It uses 15-minute normalized system-history buckets from prior locally observed days and produces P10, P50, and P90 expected power values for the current day.

The response includes:

- current normalized solar input power;
- the historical training-day count;
- today's history coverage fraction;
- a full-day curve with observed power plus P10/P50/P90 historical expectations;
- locally integrated solar-input energy observed so far;
- expected P50 energy by the current time;
- progress ratio versus that median trajectory;
- P10/P50/P90 remaining input-energy estimates;
- P10/P50/P90 projected end-of-day input energy;
- per-controller probability of reaching Float based on recent charge-cycle history;
- an all-controller Float probability using the most conservative controller probability;
- expected time by which all controllers historically tend to have reached Float when enough evidence exists.

Energy values derived from 15-minute solar-input power are explicitly labeled local integrations. They are not substituted for controller-reported charging-energy counters.

## Charge forecast

```http
GET /v1/controllers/{controller_uid}/charge-forecast
```

The charge forecast examines recent source-backed `charge_state` observations for completed prior days. It reports:

- current charge state when available;
- historical fraction of sufficiently observed days that reached Float;
- current Float probability;
- median historical first-Float time;
- training-day count and confidence;
- model/provenance metadata.

If the controller is already in Float, the current-day probability is 1.0. Otherwise the forecast remains a historical-frequency estimate. Missing observations are not treated as proof that a stage did not occur; days require a minimum amount of charge-state evidence before they enter the training set.

## Forecast accuracy

```http
GET /v1/systems/{system_uid}/forecast/accuracy
```

The accuracy endpoint performs a bounded historical replay over completed local days. For each evaluation day, the predictor uses only earlier days to form a P10/P50/P90 daily solar-input energy expectation and compares that estimate with what was later observed.

It exposes:

- evaluated-day count;
- median and mean absolute percentage error of the P50 prediction;
- P90 absolute percentage error;
- observed coverage of the P10-P90 interval;
- per-day actual/predicted values and training counts.

This is intentionally a transparent calibration surface. Forecast quality can therefore be measured and improved rather than hidden behind an opaque score.

## Confidence and evidence requirements

The default policy uses up to 28 days of local history and requires at least five sufficiently observed prior days before a forecast is considered ready. Confidence rises with the amount of historical evidence and today's observed-history coverage.

Sites with less evidence receive `insufficient_evidence` instead of fabricated predictions.

## Weather and future model layers

The first predictive-operations model is entirely local:

- no weather provider;
- no cloud inference;
- no external irradiance service;
- no Internet requirement.

Weather, irradiance, sun-position, load, or battery-state features can be added later as additional provenance-bearing evidence. They should not replace the local baseline or make the core forecast unavailable on an isolated LAN/off-grid deployment.

## Safety boundary

Forecasts are read-only estimates. They do not:

- issue Modbus writes;
- change controller configuration;
- initiate equalization or reset operations;
- control generators or loads;
- fabricate missing telemetry;
- convert unsupported Ah values into invented Wh;
- claim certainty where only a historical probability is available.
