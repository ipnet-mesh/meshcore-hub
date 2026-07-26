# Design Review Findings & Resolutions (iteration 8)

> A full-plan review after iteration 7 surfaced 13 issues. This document records each finding,
> its resolution, and the files changed. The corrections are applied in-place across the plan;
> the four schema-level items (F1–F3, F5) were treated as blockers to the Phase 0 DDL freeze.

## Blockers (schema / correctness — resolved before DDL freeze)

### F1 — Multi-tenant uniqueness was single-tenant-only ("schema does not change" was false)
Several uniqueness constraints in the Phase 0 DDL were **global**, contradicting D21/multi-tenancy.md's
claim that the schema is already instance-scoped:

- `nodes.public_key UNIQUE` — physical nodes are shared across communities by RF; two tenants
  could not both hold a row, and `touchNode`'s `ON CONFLICT (public_key)` would collide.
- `messages/advertisements/trace_paths.event_hash UNIQUE` — global, so tenant B silently never
  ingests an event tenant A already dedup'd (multi-tenancy.md §10 promises one event *per tenant*).
- `channels.name` / `channels.key_hex UNIQUE` — two communities could not share a channel name.
- `settings` PK was `key` alone — exactly one settings row per key **across the whole platform**.

**Resolution:** all of these are now **instance-scoped composite keys from Phase 0**
(`UNIQUE (instance_id, …)`, `settings PRIMARY KEY (instance_id, key)`). In single-tenant mode there is
one instance, so behaviour is identical; in Phase 7 the schema is genuinely additive. The dedup helper
and `touchNode` now target the composite keys. D21 / multi-tenancy.md reworded: the schema is built
instance-scoped from Phase 0 — Phase 7 adds tables, not constraint migrations.
Files: `components/data-model.md`, `components/ingest.md`, `components/multi-tenancy.md`,
`components/api.md`, `decisions/D21-multi-tenancy.md`.

### F2 — Two of the five continuous aggregates could not be created
`cagg_daily_message_counts` (over `messages`) and `cagg_daily_advert_counts` (over `advertisements`)
were declared as TimescaleDB continuous aggregates, but CAGGs require a **hypertable** source and both
tables are deliberately plain OLTP (uuid PK, content-hash dedup). Promoting them to hypertables would
break `event_hash` dedup (a hypertable unique must include the partition column). `cagg_node_count_history`
has no append-only time-series source either.

**Resolution:** only the two `raw_receptions`-sourced CAGGs remain (`cagg_daily_packet_counts`,
`cagg_packet_breakdown_by_type`). Daily message counts, advert counts, and node-count history become
**worker-maintained dashboard rollup tables** (instance-scoped, RLS'd), refreshed by a new
`dashboard-rollups` DerivedStateWorker job — the same "can't be a CAGG, so the worker owns it" pattern
already used for route health. Files: `components/data-model.md`, `components/derived-state.md`,
`components/api.md`, `phasing.md`, `testing.md`, `overview.md`.

### F3 — RLS had three silent-bypass / leakage gaps
1. **Owner bypass** — RLS is skipped for the table owner unless `FORCE ROW LEVEL SECURITY` is set and
   the app connects as a non-owner role. Neither was specified.
2. **`SET LOCAL` needs a transaction** — `current_setting('app.instance_id')` is NULL for any statement
   run in autocommit, so every read (not just the worker's writes) must run inside a transaction that
   sets the GUC. The read path never showed this.
3. **CAGGs and the response cache were not instance-scoped** — RLS does not propagate to continuous
   aggregates, and the cache key format (`{namespace}:{scope}:{query_hash}`) omitted `instance_id`,
   so tenants shared cache entries and `invalidate_for` flushed all tenants.

**Resolution:** added `FORCE ROW LEVEL SECURITY` + a dedicated non-owner `meshcore_app` role to the RLS
template; documented a per-request transaction that issues `SET LOCAL app.instance_id` for reads and
writes; dashboard CAGG reads now carry an explicit `instance_id` predicate; cache key is now
`{instance_id}:{namespace}:{scope}:{query_hash}` and `invalidate_for` deletes are instance-scoped.
Files: `components/data-model.md`, `decisions/D03-row-level-tenancy-rls.md`, `components/api.md`,
`components/multi-tenancy.md`.

### F5 — Circular phase dependency around the D5 schema decision
The D5 fold-vs-separate benchmark (which decides the `raw_receptions.path_hashes` shape) was scheduled in
Phase 2, but Phase 0 writes the full DDL migration and Phase 1's parallel-stack validation writes into
that schema — so the schema was "frozen" two phases before the benchmark that shapes it, and Phase 1
depended on Phase 2 outputs.

**Resolution:** the D5 benchmark moves to **Phase 0** (synthetic-data-only, needs only a throwaway
TimescaleDB — no cross-phase dependency), and the schema migration is authored after the outcome, still
within Phase 0. Phase 1 is now the **decode/classify shadow** (MqttIngester envelope diff, no DB); the
full **parallel-stack** validation (DB + workers + API diff) is Phase 2. Files: `phasing.md`,
`decisions/D05-fold-packet-path-hops.md`, `implementation-checklist.md`, `components/infrastructure.md`,
`testing.md`, `components/migration.md`.

## Design risks (resolved with corrections)

### F6 — FKs from compressed hypertables to `nodes` + hourly node cleanup
`raw_receptions.observer_node_id`, `event_observers.observer_node_id`, `telemetry.node_id`,
`event_logs.observer_node_id` were FKs to `nodes` with `ON DELETE SET NULL/CASCADE`. Hourly
`cleanup_inactive_nodes` deletes node rows, forcing SET NULL/CASCADE DML across hypertable chunks —
including **compressed** ones, where DML is restricted/costly.

**Resolution:** those columns are now **loose `uuid` references (no FK)**, matching the existing
`route_recent_matches.raw_reception_rowid` precedent and the plan's already-accepted tolerance for
orphaned hypertable rows (they compress and age out on retention). Files: `components/data-model.md`,
`components/derived-state.md`.

### F7 — Unstable per-instance advisory-lock key (double execution under HA)
`lock_key = base_key + instance_index` used a positional index that shifts when tenants are added/removed
and can differ between replicas, defeating D16's single-execution guarantee.

**Resolution:** the DerivedStateWorker now uses the two-argument `pg_advisory_xact_lock(job_key,
hashtext(instance_id))` — a stable per-(job, instance) key. Files: `components/multi-tenancy.md`,
`components/derived-state.md`, `decisions/D16-two-replica-worker-ha.md`.

### F8 — NATS per-instance stream vs. cross-tenant wildcard consumer
D4/ingest.md defined a per-instance `INGEST-<inst>` WorkQueuePolicy stream, but Phase 7's shared worker
pool subscribes to `meshcore.ingest.>` (all tenants). A consumer group cannot span multiple streams, and
the single-tenant worker example subscribed to `meshcore.ingest.*` (a token-count mismatch for the
4-token subject).

**Resolution:** one shared `INGEST` stream captures `meshcore.ingest.>`; a single durable consumer
`workers` is shared by all IngestWorker replicas; single-tenant is just one instance's subjects.
Worker subscribe corrected to `meshcore.ingest.>`. Files: `components/ingest.md`,
`decisions/D04-nats-jetstream-ingest.md`, `components/infrastructure.md`, `components/multi-tenancy.md`.

### F4 — Diff harness could not match events by hash
The harness compared `event_hash` between stacks, but the old stack uses MD5 and the new uses SHA-256,
so the same event has different hashes and coverage is always 0%.

**Resolution:** the hash-coverage check keys on `wire_hash` (the LetsMesh on-air hash, identical in both
stacks). Files: `components/migration.md`, `testing.md`.

### F10 — Spam-rescore sweep evaluated the scoring function twice per row
The sweep `WHERE spam_score IS DISTINCT FROM compute_spam_score(...)` plus `SET spam_score =
compute_spam_score(...)` ran the (COUNT-heavy) PL/pgSQL function twice per candidate every 120s.

**Resolution:** the sweep computes the score once in a subquery/CTE and filters + writes from that single
value. Files: `components/derived-state.md`.

### F11 — Smaller gaps
- **Telemetry dedup race** across concurrent worker replicas (no unique constraint possible on the
  hypertable) — documented as best-effort, backed by `Nats-Msg-Id` window dedup + read-side de-dup by
  `event_hash`. (`components/data-model.md`, `components/ingest.md`)
- **Observer (receiver) node upsert** was missing — `touchNode` now also find-or-creates the observing
  node before the FK-less reception/junction rows reference it. (`components/ingest.md`)
- **`route_recent_matches`** now stores `raw_reception_received_at` so match lookups get chunk exclusion
  instead of scanning every chunk. (`components/data-model.md`)
- **`telemetry` unbounded growth** — added an optional retention policy tied to a tuning setting.
  (`components/data-model.md`, `components/derived-state.md`)

## Notes / softer points (documented, not redesigned)

### F9 — Component-doc code is Python-shaped; some patterns don't survive the D22 TS switch
The illustrative snippets use `selectinload`, FastAPI `Depends` injection, and an `@cached` decorator,
which have no 1:1 Drizzle/Fastify equivalent. Added an explicit **TS translation note** in `api.md`
mapping them to Drizzle relational queries, Fastify `preHandler` hooks, and a cache plugin/hook, so the
sections aren't under-specified for implementation.

### F12 — First-run setup wizard reintroduces server-rendered HTML
The SSR wizard contradicts the static-shell principle (Principle 5). Documented the preferred approach —
a normal SPA route gated by a `needs_setup` flag in `/api/v1/config` (snake_case on the wire; the server-internal gate flag is `fastify.state.needsSetup`) — with SSR kept only as a fallback.
Files: `components/auth.md`.

### F13 — Greenfield rewrite + language switch + new infra + multi-tenancy is the highest-risk path
Added an explicit risk row and a short strategy note: Phases 0–5 are not independently *production*-
shippable (only collectively), the strangler-fig alternative was considered, and multi-tenancy (Phase 7)
and the language switch sit on the critical path. No timeline/effort estimate is asserted. Files:
`phasing.md`.
