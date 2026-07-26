# Open Questions

> **Status (iteration 7):** All design questions resolved. The items below are **deferred
> measurements** (decided in principle, final form pending a benchmark) — not open design
> questions. See [decisions/](decisions/) for the 23 locked ADRs.

## Deferred measurements (locked, pending execution)

### D5 — fold `packet_path_hops` benchmark

**Status:** Locked as a research spike; outcome decides the schema shape.

The D5 threshold (D17) is locked — fold if `sweep_ms(F) ≤ 1.5×` + `p95 ≤ 500ms` at 40% commonality — but the fold-vs-separate choice itself runs as a benchmark before the schema freezes.

**When:** Phase 2, half-day budget. Harness + dataset shape in [testing.md → D5 benchmark](testing.md).

### D8 — raw bytes: compress-in-DB vs object storage

**Status:** Locked — compress-in-DB first (TimescaleDB native compression, 10–20×). The `BlobStore` interface (MinIO/local-volume/S3) is introduced only if measurement shows bytes are still the bottleneck post-compression.

**When:** Phase 2, after ≥1 week of live data. Measure via `hypertable_compression_stats('raw_receptions')`.

**Threshold:** activate object storage if compressed `raw_receptions` exceeds ~50% of total DB size AND monthly growth exceeds the operator's storage budget. Most community-mesh deployments (1–4 observers) will not need it. Full criteria + activation process in [ingest.md §5](components/ingest.md#5-raw-capture-compress-in-db-defer-object-storage).

## Resolved in iteration 7 (gap review)

Four gaps identified during the full-plan review were resolved:

| # | Gap | Resolution |
|---|---|---|
| G1 | Webhook delivery undesigned | **D19** — `WebhookWorker` NATS core subscriber on `events.new.<inst>.*`; Tier-2 settings config; filter DSL wired into production |
| G2 | Custom pages file-based, D11 claimed "already DB-backed" | **D20** — `custom_pages` table, CRUD API, admin UI; `CONTENT_HOME` retired |
| G3 | OpenTelemetry tracing mentioned but unscheduled | **Dropped** — structured JSON logs + Prometheus metrics sufficient at this scale |
| G4 | Phase 0 TS client generation ambiguous | **Tooling only** — orval config + CI gate in Phase 0; first real generation in Phase 4 |
| G5 | Multi-tenancy feasibility | **D21** — shared platform, tenant-scoped observers via NATS routing, per-tenant OIDC, hostname resolution. Phase 7 extension. |
| G6 | Backend language (Python vs Node/TS) | **D22** — Node/TypeScript (Fastify). Primary decoder + first-party NATS client + one-language stack. |

Additional fixes applied: 12 stale contradictions from pre-iteration-4/6 language corrected across all files; `telemetry.event_hash` UNIQUE constraint removed (hypertable incompatibility); `settings`, `local_users`, `custom_pages`, `_metrics_cache` tables added to the authoritative DDL.

## Resolved in iteration 6 (design interview)

All six iteration-5 review questions resolved:

| # | Question | Resolution |
|---|---|---|
| Q1 | Token lifetime | **5m access / 7d sliding** — confirmed as proposed |
| Q2 | Cache invalidation graph edges | **As proposed** — no edges added or removed |
| Q3 | orval validation spike | **Committed upfront** (D09 updated) — spike skipped; `openapi-fetch` remains the documented fallback |
| Q4 | SSE patch strategy | **Hybrid** — optimistic patch for unfiltered views, invalidate for filtered; 30s poll fallback |
| Q5 | OIDC users role-editable | **Yes — DB-additive override** (`effective = IdP ∪ DB`); Users page shows both, DB is additive only |
| Q6a | NATS vs Redis for fan-out | **Both** — NATS for pub/sub, Redis for KV cache (optional) |
| Q6b | Token signing algorithm | **HS256 default**, RS256 as config option |
| Q6c | Feature-flag propagation | **Next-boundary** per flag (next packet / next tick / next request), as documented in api.md → Settings API (cross-service propagation) |

## Resolved in iteration 8 (full-plan design review)

A second full-plan review surfaced 13 issues — 4 schema-level blockers, 5 design risks, 4 softer notes —
all now corrected in place and catalogued in [review-findings.md](review-findings.md). The blockers were
resolved **before** the Phase 0 DDL freeze:

| # | Issue | Resolution |
|---|---|---|
| F1 | Global unique constraints broke multi-tenancy (`nodes.public_key`, `event_hash`, `channels`, `settings` PK) | Instance-scoped composite uniques from Phase 0 — makes D21's "schema does not change" true |
| F2 | Two of five CAGGs can't be built (source tables aren't hypertables) | Only `raw_receptions`-sourced CAGGs remain; message/advert/node-count become worker-maintained rollup tables |
| F3 | RLS silently bypassable (owner bypass, autocommit reads, unscoped CAGGs + cache) | `FORCE RLS` + non-owner role, per-request transaction, `instance_id` in cache key, explicit CAGG predicate |
| F5 | D5 benchmark scheduled after the schema it decides | Moved to Phase 0; Phase 1 = decode shadow, Phase 2 = full parallel-stack |
| F4/F6/F7/F8 | Diff harness hash mismatch; compressed-hypertable FKs; unstable advisory-lock key; per-instance stream vs wildcard consumer | wire_hash join key; loose (FK-less) hypertable node refs; two-arg `pg_advisory_xact_lock(job, hashtext(instance_id))`; single `INGEST` stream |
| F10/F11 | Spam sweep double-eval; telemetry dedup race; missing observer upsert; rowid lookup | Single-eval sweep; documented best-effort telemetry dedup; observer node upsert; `raw_reception_received_at` for chunk exclusion |
| F9/F12/F13 | Python-shaped pseudocode; wizard SSR; scope/risk realism | TS-translation notes; wizard as SPA route; explicit strategy/risk note |

## No remaining open design questions

The design covers Phases 0–7 concretely. All 23 decisions are locked; iteration 8 corrected implementation
details without reopening any decision (iteration 9 added the testing-policy decision, D23). The remaining work is implementation, guided by the
[phasing plan](phasing.md), [implementation checklist](implementation-checklist.md),
[testing/exit criteria](testing.md), and [review-findings.md](review-findings.md).
