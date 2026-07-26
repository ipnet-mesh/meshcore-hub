# D08: Compress Raw Bytes In-DB First; Defer Object Storage

- **Status:** Locked (revised in iteration 2)
- **Iteration:** 2

## Context

Today `raw_packets` stores `raw_hex` (Text) and `decoded` (JSON) on every row — duplicate payload storage that drives W2's "retention capped at 2 days because of cost" pain. The data-model/ingest sketch (data-model.md §1.3, ingest.md §5) proposed moving bytes to a `BlobStore` (MinIO / local-volume / S3) from day one. On review, that adds a runtime dependency (an object store) for every deployment — including the smallest community operator — before measurement shows it is actually needed. The question: object storage from day one, or compress-in-DB first and measure?

## Decision

**Compress-in-DB first; defer object storage.** Keep `raw_hex` (Text) on the `raw_receptions` hypertable and lean on TimescaleDB's columnar compression (10–20× typical reduction on hex strings). Retention stretches from 2 days to 30 at similar disk cost. **Add the seam now** so a later move is config-only, not a migration: a nullable `object_key` column and a `BlobStore` interface with a no-op default implementation.

Object storage (local-volume / MinIO / S3 behind the same `BlobStore` interface) is activated **only if** measurement in Phase 2 or later shows bytes are still the bottleneck after compression. The interface is the hedge; the default is no object store.

## Consequences

**Positive:** No new runtime dependency for the default deployment path — the smallest community operator runs Postgres + NATS + the app, nothing else. TimescaleDB compression alone resolves W2's cost driver (10–20×). The `BlobStore` interface + nullable `object_key` mean a later move is a config flip, not a schema migration.

**Negative:** Postgres storage holds the bytes (larger `raw_receptions` chunks vs an object-store-extended design). Compression is asymmetric — decompress-on-update is costly, but `raw_receptions` is append-mostly so this is acceptable. If we eventually move bytes out, the detail-view path gains a hop (DB → object store fetch).

## Alternatives considered

| Option | Verdict |
|---|---|
| **Compress-in-DB first, defer object storage** (chosen) | Resolves W2 at 10–20× reduction with zero new dependencies; interface preserves reversibility. |
| Object storage from day one | Rejected — adds a runtime dependency for every deployment before measurement shows it is needed; heavy for small operators. |
| Drop `raw_hex` entirely, keep only `decoded_summary` | Rejected — loses the detail-view raw-bytes inspection path operators use for debugging. |
| Compress in application code (gzip before insert) | Rejected — TimescaleDB columnar compression is more effective and transparent to queries. |
