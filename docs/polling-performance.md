# Polling performance and safe interval benchmarking

MorningstarModbusAPI can measure the real cost of each full catalog/profile poll and persist those measurements alongside controller telemetry. The performance layer is observational only: it does not add Modbus writes or change controller settings.

## Why measure instead of hard-coding a rate?

A safe polling interval depends on more than baud rate. It also depends on the number and size of register blocks in the active profile, controller response time, USB/serial adapter latency, TCP connection setup, firmware behavior, request retries, and the host running the daemon.

The daemon therefore records performance for the exact profile polls it is already performing. A separate benchmark command can deliberately test progressively faster intervals and stop as soon as the configured headroom criteria are not met.

## Persisted performance samples

The `poll_performance_samples` table stores one row for each watcher poll attempt and, optionally, each benchmark sample:

- observation timestamp;
- source mode (`watch` or `benchmark`);
- transport;
- configured/target interval;
- full-profile poll latency;
- Modbus request count;
- successful and failed Modbus request counts;
- request and response bytes;
- estimated RTU wire time;
- estimated RTU bus utilization;
- deadline-miss flag;
- poll success/failure and error text.

A successful watcher sample may reference its corresponding `poll_samples` telemetry row. Failed polls still receive a performance row even though there is no successful telemetry sample.

## Continuous metrics

`GET /v1/devices/polling/performance?device_id=...&window=300` summarizes the most recent watcher performance samples. It includes:

```text
poll_rate_hz
poll_latency_p50_ms
poll_latency_p95_ms
poll_latency_p99_ms
deadline_misses
deadline_miss_rate
modbus_requests_per_second
modbus_bytes_per_second
request_failure_rate
success_rate
bus_utilization_percent
bus_utilization_max_percent
```

Use `mode=benchmark` to summarize benchmark records or `mode=all` to combine both sources.

Raw records are available through:

```http
GET /v1/devices/polling/history?device_id=DEVICE_ID&limit=300
```

## RTU bus utilization

For serial RTU, the software estimates wire occupancy from the observed raw request/response frame sizes, configured baud rate, serial framing, and conservative 3.5-character silent gaps around each exchange.

This is an estimate of serial link occupancy, not controller CPU utilization. The value can exceed 100% when the requested polling interval is physically shorter than the estimated wire time needed by one poll.

TCP does not expose this serial-style metric; its `bus_utilization_percent` fields are `null`. TCP performance is instead judged by actual poll latency, request failures, success rate, and deadline misses.

## Target interval scheduling

The watcher treats `poll_interval_seconds` as a target **start-to-start** interval. It subtracts the time spent polling from the sleep period:

```text
poll starts
  -> full profile poll takes 210 ms
  -> configured interval is 1.000 s
  -> sleep about 790 ms
next poll starts about 1.000 s after the previous start
```

If the full poll takes longer than the configured interval, the attempt is recorded as a deadline miss and the next cycle begins without an artificial extra delay.

## Controlled benchmark

Run a benchmark against one attached device:

```bash
morningstar-modbus --config config.toml benchmark-polling \
  --device /dev/ttyUSB0 \
  --transport serial
```

For TCP:

```bash
morningstar-modbus --config config.toml benchmark-polling \
  --device 192.168.1.50 \
  --transport tcp
```

The default benchmark stages are configured as:

```toml
[poll_benchmark]
intervals_seconds = [1.0, 0.5, 0.25]
samples_per_interval = 12
min_success_rate = 0.98
max_p95_interval_ratio = 0.80
max_deadline_miss_rate = 0.05
max_request_failure_rate = 0.02
max_bus_utilization_percent = 70.0
minimum_interval_seconds = 0.25
```

Stages are tested from slowest to fastest. A stage passes only if all configured conditions pass. Testing stops immediately after the first failed stage, and the fastest previous passing stage becomes the recommendation.

For example:

```text
Polling benchmark
profile: tristar_mppt
transport: serial
1.000s PASS success=100.0% p95=214.0ms bus_max=24.5%
0.500s PASS success=100.0% p95=219.0ms bus_max=49.0%
0.250s STOP success=100.0% p95=224.0ms bus_max=98.0%
  - p95 poll latency leaves insufficient interval headroom
  - estimated RTU bus utilization above threshold
recommended interval: 0.500s
```

The exact values come from the attached device and adapter rather than from the example.

## Benchmark safety behavior

The benchmark performs only the same read-only profile reads used by normal monitoring. It does not write registers or coils.

The default minimum benchmark interval is 250 ms. Faster custom stages are rejected unless the configured `minimum_interval_seconds` is deliberately lowered. The ordinary watcher remains at its conservative configured interval; running the benchmark does **not** automatically rewrite `config.toml` or change the daemon's interval.

This separation is intentional. The benchmark produces evidence and a recommendation; the operator decides whether to apply it.

## Persistence

Benchmark performance rows are saved to the configured SQLite database by default with `mode=benchmark`, allowing later comparison with real watcher behavior. Use `--no-persist` when a temporary benchmark should leave no performance records.

The benchmark warm-up/identity traffic is not included in stage measurements. Only complete steady-state profile polls are evaluated.

## Interpreting the recommendation

A passing interval means it satisfied the configured benchmark thresholds for the sample window; it is not a vendor guarantee. Longer observation windows remain useful for catching intermittent adapter, cable, USB, TCP, or controller issues.

A sensible deployment workflow is:

1. run the benchmark on the actual device/transport;
2. choose the recommended interval or a slower one;
3. set `[watch].poll_interval_seconds`;
4. monitor `/v1/devices/polling/performance` over normal operation;
5. increase the interval again if p95/p99 latency, request errors, deadline misses, or RTU utilization drift upward.
