# Polling performance, automatic cadence, and safe interval benchmarking

MorningstarModbusAPI can measure the real cost of each full catalog/profile poll and use those measurements either for an explicit benchmark or to select the watcher interval automatically. The performance layer is observational only: it does not add Modbus writes or change controller settings.

For new integrations, polling-performance data should normally be read through the immutable physical-controller API. The legacy device-scoped routes remain available when one exact raw `device_id` segment is required.

## Poll interval configuration

`[watch].poll_interval_seconds` accepts either a positive number or the string `"auto"`.

A numeric value is used as the watcher target interval exactly as configured, including sub-second values:

```toml
[watch]
poll_interval_seconds = 0.2
```

Automatic mode uses the configured benchmark stages and thresholds instead of a separate heuristic:

```toml
[watch]
poll_interval_seconds = "auto"

[poll_benchmark]
intervals_seconds = [1.0, 0.5, 0.25]
samples_per_interval = 12
min_success_rate = 0.98
max_p95_interval_ratio = 0.80
max_deadline_miss_rate = 0.05
max_request_failure_rate = 0.02
max_bus_utilization_percent = 70.0
minimum_interval_seconds = 0.25
auto_fallback_interval_seconds = 5.0
```

## How automatic polling selects an interval

Auto mode is deliberately conservative and global to the watcher because `poll_interval_seconds` is currently a global watcher setting.

1. The watcher starts at the slowest configured benchmark stage.
2. It collects `samples_per_interval` complete live profile polls for every currently-present physical controller.
3. Each controller is evaluated with the same success-rate, p95-latency, deadline-miss, request-failure, and RTU-utilization rules used by `benchmark-polling`.
4. The watcher moves to the next faster stage only when every present controller passes the current stage.
5. At the first failed stage, it locks to the last passing interval.
6. If the first stage itself fails, it uses `auto_fallback_interval_seconds`.
7. If every configured stage passes, it locks to the fastest configured stage.

For example, with `[1.0, 0.5, 0.25]`, if 1.0 seconds and 0.5 seconds pass but 0.25 seconds fails, the watcher settles at 0.5 seconds.

Auto calibration resets when the selected physical-controller/endpoint/profile set changes. This prevents a rate learned for one connection or controller set from being silently reused after a meaningful runtime topology change.

The automatic tuner uses every live in-memory poll result, even when the database persistence cadence is slower than the polling cadence.

## Polling cadence is separate from database cadence

Fast polling no longer means equally fast SQLite history growth.

`[database].telemetry_write_interval_seconds` controls the minimum interval between poll-driven persistence cycles for one physical controller:

```toml
[database]
telemetry_write_interval_seconds = 1.0
```

Values below `1.0` are rejected. With a 0.2-second poll interval and the default 1-second persistence interval, the service can perform roughly five live polls per second while persisting at most one of those poll snapshots per second per controller.

A poll-driven persistence cycle includes the telemetry sample/register values and, when applicable, its watcher performance sample, connection-success update, and refreshed device-intelligence state. Intermediate successful polls still update in-memory lifecycle/intelligence and still feed automatic interval evaluation; they simply do not create additional high-frequency history rows.

This is a write-amplification and history-cadence safeguard. SQLite WAL and transactions already protect committed writes from ordinary high-frequency access; the one-second floor is not a claim that SQLite would otherwise inherently corrupt at 0.2 seconds. It instead gives the service a deliberate persistence boundary and reduces unnecessary disk churn.

The one-second limiter applies to regular poll-driven persistence. Event-driven state changes such as discovery/reconciliation, startup/shutdown presence updates, and retained-history backfill remain independent because delaying those events could make operational state misleading.

## Persistence failures versus Modbus failures

A successful controller read is not converted into a controller failure merely because a database write fails. Persistence exceptions are logged separately while the in-memory controller lifecycle remains based on the actual Modbus result.

Actual Modbus failures still drive the configured degraded/offline/reconnect behavior. This avoids unnecessary device reconnect churn during a transient SQLite/storage problem.

## Why measure instead of hard-coding a rate?

A safe polling interval depends on more than baud rate. It also depends on the number and size of register blocks in the active profile, controller response time, USB/serial adapter latency, TCP behavior, firmware behavior, request retries, and the host running the daemon.

The watcher measures the exact profile polls it is already performing. The separate benchmark command can deliberately test progressively faster intervals and stop as soon as configured headroom criteria are not met.

## Poll performance samples

The `poll_performance_samples` table stores persisted watcher-performance observations and, optionally, benchmark samples. In watcher mode, persistence follows `database.telemetry_write_interval_seconds`; it is intentionally not required to store every faster in-memory poll.

Each row includes:

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

A successful persisted watcher performance row may reference its corresponding `poll_samples` telemetry row. A persisted failed poll has no successful telemetry sample.

Performance rows retain their original raw `device_id` ownership. Controller-scoped queries resolve all historical member IDs for the physical controller and combine those records without rewriting them.

## Continuous metrics

Preferred controller-scoped summary:

```http
GET /v1/controllers/{controller_uid}/polling/performance?window=300
```

Raw controller-scoped records:

```http
GET /v1/controllers/{controller_uid}/polling/history?limit=300
```

The summary includes metrics such as:

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

These API metrics describe **persisted** watcher/performance rows. When live polling is faster than the database cadence, the persisted `poll_rate_hz` is therefore a storage-sample rate, not necessarily the instantaneous in-memory Modbus poll rate used by auto calibration.

Use `mode=benchmark` to summarize benchmark records or `mode=all` to combine both sources. The default mode is `watch`.

Legacy device-scoped equivalents remain available:

```http
GET /v1/devices/polling/performance?device_id=DEVICE_ID&window=300
GET /v1/devices/polling/history?device_id=DEVICE_ID&limit=300
```

The controller routes are preferred when a controller has changed IP, USB path, or historical raw device ID.

## RTU bus utilization

For serial RTU, the software estimates wire occupancy from the observed raw request/response frame sizes, configured baud rate, serial framing, and conservative 3.5-character silent gaps around each exchange.

This is an estimate of serial link occupancy, not controller CPU utilization. The value can exceed 100% when the requested polling interval is physically shorter than the estimated wire time needed by one poll.

TCP does not expose this serial-style metric; its `bus_utilization_percent` fields are `null`. TCP performance is instead judged by actual poll latency, request failures, success rate, and deadline misses.

## Target interval scheduling

The watcher treats the selected numeric/automatic interval as a target **start-to-start** interval. It subtracts time spent polling from the sleep period:

```text
poll starts
  -> full profile poll takes 210 ms
  -> selected interval is 1.000 s
  -> sleep about 790 ms
next poll starts about 1.000 s after the previous start
```

If the full poll takes longer than the selected interval, the attempt is recorded as a deadline miss and the next cycle begins without an artificial extra delay.

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

## Benchmark identity and persistence

Benchmark performance rows are saved to the configured SQLite database by default with `mode=benchmark`. Before persistence, the benchmark observation is registered through the same physical-controller registry used by the watcher.

That matters when the endpoint has moved: a benchmark performed on a new DHCP address or USB path is associated with the existing immutable `controller_uid`/canonical telemetry identity rather than independently creating a new endpoint-owned controller history.

Use `--no-persist` when a temporary benchmark should leave no performance records.

The benchmark warm-up/identity traffic is not included in stage measurements. Only complete steady-state profile polls are evaluated. The watcher persistence limiter does not change the explicit benchmark command's sampling behavior; benchmark rows are evidence from the requested benchmark run.

## Benchmark safety behavior

The benchmark and auto mode perform only the same read-only profile reads used by normal monitoring. Neither writes registers nor coils.

The default minimum benchmark interval is 250 ms. Faster custom stages are rejected unless `minimum_interval_seconds` is deliberately lowered. Running the explicit benchmark does **not** rewrite `config.toml`. To have the watcher choose automatically, set `watch.poll_interval_seconds = "auto"`.

## Interpreting the recommendation

A passing interval means it satisfied the configured benchmark thresholds for the sample window; it is not a vendor guarantee. Longer observation windows remain useful for catching intermittent adapter, cable, USB, TCP, or controller issues.

A sensible deployment workflow is:

1. set `poll_interval_seconds = "auto"`, or run `benchmark-polling` and choose a numeric interval;
2. keep `database.telemetry_write_interval_seconds >= 1.0` so high-rate polling does not create high-rate database churn;
3. monitor `/v1/controllers/{controller_uid}/polling/performance` over normal operation;
4. inspect `mode=all` or `mode=benchmark` when comparing benchmark evidence to persisted watcher behavior;
5. choose a slower numeric/benchmark stage if real-world latency, request failures, deadline misses, or RTU utilization drift upward.

For the full API parameter reference, see [`api.md`](api.md).
