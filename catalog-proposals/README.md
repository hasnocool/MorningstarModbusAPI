# Catalog Proposal Provenance

This directory stores small, reviewed provenance records for changes to Morningstar family catalog
definitions or the authoritative source index.

Do not vendor Morningstar PDFs here. The source document stays in the ignored local/CI cache and the
proposal records its SHA-256 digest.

Every proposal JSON file must contain:

- `source_id`: ID from `docs/vendor/morningstar/sources.json`.
- `source_sha256`: SHA-256 of the exact vendor document used for review.
- `affected_profiles`: non-empty list of catalog profile names.
- `changes`: non-empty list describing the reviewed code changes.
- `tests`: non-empty list naming the tests added or changed.

CI requires at least one proposal JSON and a `tests/` change whenever a family module or the source
index changes. Generated maintenance reports are advisory artifacts and should not be committed.
