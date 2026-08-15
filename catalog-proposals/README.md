# Catalog proposal provenance

This directory stores small, reviewed provenance records for changes to Morningstar family catalog definitions or the authoritative source index.

Complete Morningstar vendor PDFs are not committed here. Obtain the source artifact from the official URL in `docs/vendor/morningstar/sources.json` (normally through the maintenance scanner), then bind the reviewed change to that exact artifact with its SHA-256 digest.

Every proposal JSON file must contain:

- `source_id`: ID from `docs/vendor/morningstar/sources.json`.
- `source_sha256`: SHA-256 of the exact vendor document used for review.
- `affected_profiles`: non-empty list of catalog profile names.
- `changes`: non-empty list describing the reviewed code changes.
- `tests`: non-empty list naming the tests added or changed.

Example:

```json
{
  "source_id": "tristar-mppt-modbus-v11",
  "source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "affected_profiles": ["tristar_mppt"],
  "changes": [
    {
      "address": "0x0018",
      "change": "verified decoder and unit against vendor specification"
    }
  ],
  "tests": ["tests/test_catalog.py::test_tristar_updated_register"]
}
```

CI requires at least one valid proposal JSON and a `tests/` change whenever a family module or the authoritative source index changes. Generated maintenance reports are advisory artifacts and should not be committed as source truth.

See `docs/catalog-maintenance.md` for the full validation/scanning workflow.
