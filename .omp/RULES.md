# MorningstarModbusAPI hard rules

1. Keep runtime read-only: no Modbus/SNMP/controller writes, reset/equalize/generator control, or write escape hatch.
2. Checked-out branch/source/tests are truth; never describe remembered/open work as merged/released.
3. Use canonical v0.5+ domain packages; do not reintroduce removed flat-module architecture.
4. Preserve immutable physical `controller_uid`; endpoints/device IDs/system membership do not replace identity.
5. Preserve raw telemetry/source provenance; do not destructively rewrite history for reporting.
6. Keep vendor, software, fixture/replay, and physical-hardware verification levels separate.
7. Review physical captures/raw frames before publication; never commit secrets or unsanitized evidence.
8. Do not republish vendor PDFs; use approved sources and SHA-bound provenance.
9. Keep product/register knowledge in catalog/intelligence and cross-controller semantics in `systems/`, not routes.
10. Treat transport topology as observational and component relationships as evidence-backed with confidence.
11. Reconcile ReadyEdge-reported products to discovered controllers before creating reported-only components.
12. Power/energy values are observed, derived, or unknown. Never infer battery net current from charger current or
    invent load/generator/discharge/residual values to make an energy balance close.
13. Keep async I/O non-blocking and connection cleanup/retry semantics correct.
14. Do not claim tests/CI/provenance passed unless verified against the relevant head.
15. Never hide failures by deleting coverage or weakening assertions without a justified behavior change.
