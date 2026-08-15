# MorningstarModbusAPI hard rules

1. Keep the runtime read-only. Do not implement Modbus writes, coil actions, EEPROM/configuration mutation,
   resets, equalize/control triggers, or a generic write-capable protocol escape hatch.
2. The checked-out branch/source/tests are truth. Never describe an open or remembered PR as merged behavior.
3. Preserve raw telemetry as source evidence; do not destructively rewrite/prune history for reporting features.
4. Keep vendor documentation, software tests, synthetic/replay fixtures, and physical-device verification as
   separate evidence levels. Never promote evidence without support.
5. Review physical capture identifiers/raw frames before publication. Never commit secrets or unsanitized device
   evidence.
6. Do not republish complete vendor manuals/PDFs. Use the approved source index and SHA-bound provenance.
7. Put product/register knowledge in the catalog/intelligence layers, not transport/API conditionals.
8. Keep async code non-blocking and preserve connection cleanup/retry semantics.
9. Do not claim tests/CI passed unless they actually ran against the relevant head.
10. Never make a failing check disappear by deleting coverage or weakening assertions without a justified
    behavior change.
