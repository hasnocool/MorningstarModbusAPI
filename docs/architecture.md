# Architecture

MorningstarModbusAPI is intentionally a small read-only ingestion boundary between physical Morningstar controllers and applications that consume telemetry.

```text
USB/RS-232/RS-485                 Ethernet
       |                              |
       v                              v
  Modbus RTU                     Modbus TCP
       |                              |
       +---------- discovery ----------+
                      |
                      v
               device registry
                      |
               profile selection
                      |
                      v
              periodic polling
                      |
                      v
              SQLite/WAL history
                      |
                      v
                FastAPI /v1
```

## Concurrency model

- TCP uses native asyncio streams.
- PySerial is blocking by design, so each RTU client isolates serial operations in a dedicated single-worker executor and serializes requests with an `asyncio.Lock`.
- Serial enumeration runs through `asyncio.to_thread`.
- SQLite access uses `aiosqlite` with WAL enabled.
- Device polls run concurrently with `asyncio.TaskGroup`.
- TCP discovery is bounded by a semaphore.

## Safety boundary

The initial service implements Modbus reads only: function 0x03, function 0x04, and device identification 0x2B/0x0E. No coil or register write endpoint is exposed.

## Profiles

The service keeps raw register values even when it can decode a product. The built-in TriStar MPPT profile adds named/scaled values for the core voltage, current, temperature, charge-state, and power registers while preserving the complete 0x0000-0x004F holding-register block.
