# Next-Generation Architecture — MeshCore Hub Rewrite

> **Status:** Design complete (iterations 1–9). All 23 architectural decisions locked. All design
> questions resolved. Iteration 8 applied 13 review corrections — see
> [review-findings.md](review-findings.md) — four of them schema-level (multi-tenant uniqueness, CAGG
> vs hypertable, RLS enforcement, phase sequencing) resolved before the Phase 0 DDL freeze.
> Iteration 9 added [D23](decisions/D23-test-pyramid-coverage.md) (test pyramid & CI coverage policy).
> **Supersedes:** The monolithic `REWRITE.md` (split into these files).

This directory contains the complete design for a from-scratch rewrite of MeshCore Hub.
The product and domain model are preserved; the **system architecture** is reshaped around
a durable ingest pipeline, polyglot persistence, a single derived-state worker, explicit
JWT auth, and a generated frontend client.

## How to navigate

**Start here:** [overview.md](overview.md) for the current-system analysis and pain points.
Then read the [decisions](decisions/) for the locked architectural choices, and the
[component docs](components/) for the detailed designs. When ready to implement, follow the
[implementation checklist](implementation-checklist.md).

### Index

| Document | Purpose |
|---|---|
| [review-findings.md](review-findings.md) | Iteration-8 design-review findings (13 issues) and their resolutions, cross-referenced (F1–F13) into the docs below |
| [overview.md](overview.md) | Current system inventory, pain points, target architecture principles, topology |
| [code-warts.md](code-warts.md) | Catalog of 52 antipatterns and gotchas from the current codebase (lessons for the new repo) |
| [phasing.md](phasing.md) | The 7-phase plan, risks, and design retrospective (what shifted across iterations) |
| [implementation-checklist.md](implementation-checklist.md) | Single-page actionable checklist for every task across all 7 phases |
| [testing.md](testing.md) | Test strategy (vitest + Playwright pyramid, D23), D5 benchmark plan, and phase exit criteria |
| [open-questions.md](open-questions.md) | All resolved — 2 deferred measurements remain (D5 benchmark, D8 compression check) |

### Component design documents

| Document | Component | Key decisions |
|---|---|---|
| [components/infrastructure.md](components/infrastructure.md) | Topology, NATS, Postgres+TimescaleDB, Redis, provisioning | D1, D4, D10, D14, D22 |
| [components/data-model.md](components/data-model.md) | Schema DDL, hypertables, CAGGs, RLS, tenancy | D1, D3, D5, D8, Q-A, Q-B |
| [components/ingest.md](components/ingest.md) | MqttIngester, IngestWorker, NATS envelopes, dedup, webhook delivery | D4, D5, D19, D22 |
| [components/auth.md](components/auth.md) | JWT, local passwords, OIDC, setup wizard | D6, D12, D18, D22 |
| [components/api.md](components/api.md) | Cache contract, SSE, settings API, custom pages API, middleware | D6, D7, D11, D19, D20, D22 |
| [components/frontend.md](components/frontend.md) | Generated client, code-splitting, static shell, SSE hooks, pages admin | D7, D9, D20 |
| [components/derived-state.md](components/derived-state.md) | Worker jobs, spam, retention, observability | D15, D16, D19, D22 |
| [components/migration.md](components/migration.md) | Greenfield strategy, config export/import, parallel-stack | D13, D14 |
| [components/multi-tenancy.md](components/multi-tenancy.md) | Shared platform, observer scoping, per-tenant OIDC, hostname resolution | D3, D4, D12, D21, D22 |

### Architecture Decision Records

All 23 decisions are locked. See [decisions/](decisions/) for individual records.

| # | Decision | Status |
|---|---|---|
| [D01](decisions/D01-timescaledb-for-history.md) | TimescaleDB for high-volume history | Locked |
| [D02](decisions/D02-keep-event-logs-compressed.md) | Keep `event_logs` as a compressed hypertable | Locked |
| [D03](decisions/D03-row-level-tenancy-rls.md) | Row-level `instance_id` + RLS for multi-tenancy | Locked |
| [D04](decisions/D04-nats-jetstream-ingest.md) | NATS JetStream for ingest queue + realtime fan-out | Locked |
| [D05](decisions/D05-fold-packet-path-hops.md) | Fold `packet_path_hops` into array column (spike) | Locked (spike) |
| [D06](decisions/D06-jwt-auth-boundary.md) | JWT issued by web tier, verified at API | Locked |
| [D07](decisions/D07-sse-realtime.md) | SSE for live pages, polling as fallback | Locked |
| [D08](decisions/D08-raw-bytes-compress-in-db.md) | Compress raw bytes in-DB; defer object storage | Locked |
| [D09](decisions/D09-orval-client-generation.md) | orval for generated TS client (committed upfront) | Locked |
| [D10](decisions/D10-drop-sqlite.md) | Drop SQLite; Postgres-only from Phase 0 | Locked |
| [D11](decisions/D11-three-tier-config.md) | Three-tier config: env vars / DB settings / entities | Locked |
| [D12](decisions/D12-multi-source-auth.md) | Multi-source auth: local passwords + optional OIDC | Locked |
| [D13](decisions/D13-channels-in-export.md) | Include channels in config export | Locked |
| [D14](decisions/D14-five-day-parallel-window.md) | 5-day parallel-stack validation window | Locked |
| [D15](decisions/D15-plpgsql-spam-scoring.md) | PL/pgSQL function for spam scoring | Locked |
| [D16](decisions/D16-two-replica-worker-ha.md) | Two-replica worker with advisory locks | Locked |
| [D17](decisions/D17-d5-fold-threshold.md) | D5 fold threshold (1.5x / 500ms / 40%) | Locked |
| [D18](decisions/D18-cli-for-ops-not-config.md) | CLI for ops only; one config surface per item | Locked |
| [D19](decisions/D19-webhook-nats-subscriber.md) | Webhook delivery via NATS core subscriber | Locked |
| [D20](decisions/D20-custom-pages-to-db.md) | Custom pages move to DB (Tier-3 entity) | Locked |
| [D21](decisions/D21-multi-tenancy.md) | Multi-tenancy: shared platform, self-provisioning tenants, shared worker pool | Locked |
| [D22](decisions/D22-node-typescript-backend.md) | Node/TypeScript backend (Fastify); primary decoder + first-party NATS | Locked |
| [D23](decisions/D23-test-pyramid-coverage.md) | Test pyramid & CI coverage policy: vitest (unit/integration/component) + Playwright e2e | Locked |

## Decision summary at a glance

| Area | From | To |
|---|---|---|
| Ingest | Sync MQTT callback, 1 thread | `MqttIngester` → NATS → `IngestWorker` pool |
| History tables | `raw_packets` + `packet_path_hops`, 2-day cap | TimescaleDB hypertables, 30-day retention, compressed |
| Route health | 7 tables + 2 background cadences | 3 worker-maintained tables + dashboard CAGGs (packets) & rollup tables (messages/adverts/nodes) |
| IDs/enums | `String(36)` UUIDs, string enums | Native `uuid`, Postgres enums, `JSONB` |
| Auth | Header injection (implicit trust) | Short-lived JWT + local passwords + optional OIDC |
| Cache | Dual/tri key format, hand-coded invalidation | Single key format + declarative dependency graph |
| Config | ~200 env vars, restart to change | Three-tier: env (bootstrap) / DB settings (runtime) / entities |
| Frontend | Hand-copied types, 776 KB bundle, polling | Generated client, lazy chunks, SSE-driven live pages |
| Background work | 6 daemon threads | One `DerivedStateWorker` process + `WebhookWorker` NATS subscriber |
| CLI | Full Click group with config-mirroring flags | Ops-only commands; config via env + Admin UI |
| Webhooks | Env-var-only config, in-memory queue, daemon thread | Tier-2 settings, NATS subscriber, filter DSL wired |
| Custom pages | File-based (`CONTENT_HOME`), no admin UI | DB-backed Tier-3 entity, CRUD API, admin UI |
| Multi-tenancy | Single instance per deployment | Shared platform, self-provisioning tenants, wildcard DNS, shared worker pool (Phase 7) |
| Backend language | Python (FastAPI, SQLAlchemy, nats-py) | **TypeScript** (Fastify, Drizzle, @nats-io/jetstream, primary decoder) |
