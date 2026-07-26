# Implementation Phasing

> The 8-phase implementation plan (Phase 0–7), risks, and explicit non-goals for the MeshCore Hub rewrite.
> Each phase is independently shippable and backwards-compatible (data migrations provided).
> Phase exit criteria are consolidated in [testing.md](testing.md).

## How to use this plan during implementation

This plan is a **design contract**, not a project schedule. Three documents carry three different
things — read all three for the phase you're on:

- **[Component docs](components/)** — *what to build*: schemas, contracts, pseudocode, the authoritative design.
- **[implementation-checklist.md](implementation-checklist.md)** — *the ordered task list*: one-line checkboxes per phase, each linking back to its component section. Use it as the milestone tracker.
- **[testing.md](testing.md)** — *the acceptance gates*: phase exit criteria + the D5 benchmark + the test pyramid (D23).

What lives **outside** this plan: per-phase build order and PR-level task decomposition — turning
"Implement `AuthMiddleware` preHandler" into its ordered sub-tasks and review sequence. That is
execution planning: it evolves with the code, so put it in the implementation repo's issue tracker
and link each phase to it there. The plan deliberately asserts no timeline or effort estimate
([Strategy note](#strategy-note--scope-realism-f13)); a baked-in task breakdown would contradict
that posture and go stale on first contact with the code.

**Suggested per-phase sequence:** (1) read the component doc(s) for the phase, (2) work the
checklist in dependency order, (3) author the phase's `### Tests` deliverables alongside the code
(D23), (4) satisfy the `testing.md` exit criteria before declaring the phase done.

## Phase 0 — Foundations (no behavior change)

- **Run the D5 fold-vs-separate benchmark first** (synthetic data, throwaway TimescaleDB — testing.md → [D5 plan](testing.md#d5-benchmark-plan-fold-vs-separate)). Its outcome decides the `raw_receptions.path_hashes` shape, so it must land **before** the DDL is authored. This was previously (mis)scheduled in Phase 2, which created a circular dependency — the schema was "frozen" in Phase 0 but the benchmark that shapes it ran two phases later (F5).
- Fresh schema design (reflecting the D5 outcome); native `uuid`, enums, `JSONB`, SHA-256 hashes, instance-scoped composite uniques (F1), `FORCE ROW LEVEL SECURITY` + non-owner app role (F3).
- Decide datastore strategy (D1, D2, D3, D4). Provision the **single** platform-wide `INGEST` JetStream stream (`meshcore.ingest.>`) — not a per-instance stream (F8).
- Stand up the typed `DecodedPacket` models + declarative classification table.
- Set up the TS client tooling (orval config, `make gen-client`, CI drift check); first real generation happens in Phase 4 against the new API spec.

> **Detailed design:** schema DDL lives in [components/data-model.md](components/data-model.md).

## Phase 1 — Ingest pipeline

- Introduce **NATS JetStream** as the durable queue + the realtime fan-out bus (D4 locked). Redis narrows to API response cache only.
- Split `MqttIngester` (pure decode+produce) from `IngestWorker` (batched write).
- Centralize dedup helper; collapse handler boilerplate.
- **`WebhookWorker`** (D19): NATS core subscriber on `events.new.<inst>.*`; Tier-2 webhook settings; filter DSL wired into production.
- **Decode/classify shadow validation:** run the `MqttIngester` against the live feed and diff its **envelopes** (decoded + classified output) against the old normalizer — no DB, no workers required. This isolates "does the new decode/classify match?" from the full end-to-end diff. The full **parallel-stack** validation (both stacks writing to their DBs, compared at the API) is a Phase 2 activity, because it needs the provisioned schema and the D5 outcome — running it here would make Phase 1 depend on Phase 2 (F5).

> **Detailed design:** [components/ingest.md](components/ingest.md), [components/infrastructure.md](components/infrastructure.md). Exit criteria: [Phase 1](testing.md#phase-1--ingest-pipeline).

## Phase 2 — Greenfield provisioning

- **Greenfield infra:** fresh Postgres+TimescaleDB, NATS, new schema. No historical data migration.
- **Preserved-config export/import** (`db export-config` / `db import-config`): user_profiles + roles, routes + nodes + observers, node_tags, adoptions, channels, plus node identity stubs.
- **Full parallel-stack validation** (moved here from Phase 1): both stacks ingest the same live MQTT into their own DBs; the diff harness compares per-hour event counts and `wire_hash` coverage (F4) at the API. This is the DB-level gate; the decode-level shadow was Phase 1.
- **D5 outcome applied** (the benchmark itself ran in Phase 0, F5): the schema already reflects fold-vs-separate; here the route matcher is validated against real data at the D5 gate.
- **D8 step 1:** keep `raw_hex` in-DB but rely on TimescaleDB compression (10–20×). **D8 step 2 (only if measured necessary):** move bytes to a `BlobStore` (MinIO/local-volume) behind an interface.
- No historical data migration — preserved config only (see [migration.md](components/migration.md)).

> **Detailed design:** [components/migration.md](components/migration.md). Benchmark: [D5 fold-vs-separate](testing.md#d5-benchmark-plan-fold-vs-separate). Exit criteria: [Phase 2](testing.md#phase-2--greenfield-provisioning).

## Phase 3 — Derived state consolidation

- Replace the 6 background threads with the single `DerivedStateWorker`.
- Convert the **hypertable-sourced** dashboard aggregations (daily packet counts, packet breakdown by type — over `raw_receptions`) to TimescaleDB continuous aggregates. The message/advert/node-count aggregations source from OLTP/entity tables and **cannot be CAGGs** — they become worker-maintained rollup tables via the `dashboard-rollups` job (F2).
- Route health: rewrite the matcher against `raw_receptions.path_hashes` (D5 outcome); collapse the 3 derived tables into worker-maintained state.
- Move spam rescoring to a DB function + periodic sweep.

> **Detailed design:** [components/derived-state.md](components/derived-state.md). Exit criteria: [Phase 3](testing.md#phase-3--derived-state-consolidation).

## Phase 4 — API & auth

- Async ORM end-to-end (drop SQLite — D10 locked — so `node-postgres` unconditionally).
- JWT-based auth boundary; deprecate `X-User-*` header injection.
- Unify cache keying + declarative invalidation graph.
- SSE realtime endpoint (fed from NATS).
- Custom pages API (D20): `GET/POST/PUT/DELETE /api/v1/pages`; `PublicConfig` includes enabled pages.

> **Detailed design:** [components/auth.md](components/auth.md), [components/api.md](components/api.md). Exit criteria: [Phase 4](testing.md#phase-4--api--auth).

## Phase 5 — Frontend

- Adopt **orval** generated client everywhere (D09 — committed upfront, no spike); delete hand-copied types.
- Route-level code-splitting (lazy chunks for Dashboard/Map/Routes/CustomPage; vendor-split chart.js/leaflet/markdown).
- Static shell + `/api/v1/config` (public, cacheable) + `/api/v1/me` (user-specific).
- SSE-driven live pages: hybrid strategy (optimistic patch for unfiltered views, invalidate for filtered views; 30s poll as fallback).
- Login page (local/OIDC/hybrid per `auth_mode`); Settings + Users + Pages admin pages.

> **Detailed design:** [components/frontend.md](components/frontend.md). Exit criteria: [Phase 5](testing.md#phase-5--frontend).

## Phase 6 — Polish & decommission

The cleanup phase after all functional phases land. Three tracks:

### 6.1 Old-stack decommission
- [ ] Parallel-stack diff ([migration.md](components/migration.md#parallel-stack-validation-ship-gate)) clean for 3 consecutive days within the 5-day window (D14).
- [ ] DNS / reverse-proxy / MQTT subscription exclusivity cut over to the new stack.
- [ ] Old stack containers stopped; old volumes retained for 30 days as cold backup, then destroyed.
- [ ] Old-stack domain/SSL certificates repointed or retired.

### 6.2 Security hardening pass
- [ ] RLS audit: verify every tenant-scoped table enforces the `instance_id` policy; add a test that asserts cross-instance queries return 0 rows.
- [ ] Rate-limit review: confirm local-login lockout thresholds; verify reverse-proxy `limit_req` / `fail2ban` rules for the auth endpoint.
- [ ] JWT rotation drill: rotate `JWT_SESSION_SECRET`; verify all sessions invalidate gracefully.
- [ ] Dependency audit: `npm audit` clean (backend + frontend); no known CVEs in the lockfiles.

### 6.3 New-repo `AGENTS.md` / `CONTRIBUTING.md`
- [ ] Derive "we do / we don't" rules from [code-warts.md](code-warts.md) — each wart becomes an explicit convention.
- [ ] Document the one-config-surface rule (D18), the cache-invalidation graph (api.md → Unified cache contract), the auth boundary (D6/D12), and the codegen gate (D09).
- [ ] Port the still-relevant operational gotchas from the old AGENTS.md, updating for the TS stack (parenthesized exception tuples become irrelevant; random migration ID guidance becomes "let drizzle-kit generate")

### 6.4 Documentation overhaul
- [ ] Update README, deployment guide, observer guide, configuration reference for the new stack.
- [ ] Operator migration guide: old stack → new stack (export-config → provision → parallel-validate → cut over).
- [ ] API docs (Swagger/ReDoc) verified clean with `response_model` on every endpoint.

### 6.5 Performance validation
- [ ] Load test: simulate N observers × M packets/sec against the new stack; verify IngestWorker batch throughput and NATS backlog stays bounded.
- [ ] Dashboard latency: p95 < 200ms for all dashboard endpoints under load (CAGGs effective).
- [ ] Route evaluator sweep: p95 < 500ms per route at the D5 High dataset shape.

> Exit criteria: old stack decommissioned; security audit clean; `AGENTS.md` written; docs updated; load test passes.

## Phase 7 — Multi-tenancy (self-provisioning extension)

After the single-tenant stack (Phases 0–6) is stable, extend to shared-platform multi-tenancy (D21). The schema does not change — all tables are already instance-scoped. **Tenants self-provision — no platform-operator action required.**

- **Self-service registration:** `POST /api/v1/register` creates a fully operational tenant (instance + subdomain + settings seed + admin) in one transaction. The admin is immediately logged in at their subdomain. Abuse prevention via rate limiting + optional captcha.
- **Shared worker pool:** workers are tenant-agnostic — IngestWorkers subscribe to `meshcore.ingest.>` (wildcard), the DerivedStateWorker iterates over all active instances, WebhookWorkers subscribe to `events.new.>`. New tenants are picked up automatically via NATS `instance.created` notifications. No per-tenant processes, no Compose profiles.
- **Wildcard DNS + custom domains:** the platform runs `*.PLATFORM_DOMAIN` with a wildcard TLS certificate. Tenants pick a subdomain at registration. Custom domains are tenant-admin self-service (add hostname in Admin UI, configure CNAME, ACME provisions TLS automatically).
- **Observer scoping:** `tenant_observers` table (tenant-admin-managed allowlist); `ObserverAllowlistCache` in the MqttIngester; per-tenant NATS subject routing.
- **Per-tenant OIDC:** `tenant_oidc_configs` table; OIDC config moves from Tier-1 env to DB; web tier resolves per hostname.
- **Instance resolution:** `instance_hostnames` table + hostname middleware; `DEFAULT_INSTANCE_ID` fallback for single-tenant deployments.
- **Tenant management CLI (fallback):** `admin create-instance` / `delete-instance` (soft) / `undelete-instance` / `purge-instance` (hard) / `list-instances`.
- **Admin UI:** `/admin/observers` page (allowlist CRUD); Settings → Authentication (OIDC); Settings → Community (custom domains, soft-delete).

> **Detailed design:** [components/multi-tenancy.md](components/multi-tenancy.md). Exit criteria: a tenant registers via the public API, picks a subdomain, adds a custom domain, configures their own OIDC, manages their observer allowlist — all with zero platform-operator action; shared workers pick up the new tenant within seconds; tenant isolation verified (cross-instance queries return 0 rows on every table including route health).

---

## Testing (cross-cutting — every phase)

Locked in [D23](decisions/D23-test-pyramid-coverage.md). The rewrite ships with a regression suite,
not just acceptance gates: **every component and piece of logic carries tests at the appropriate
layer, and the suite must pass in CI** (qualitative coverage, no % floor).

- **vitest** (one runner, D22): unit (pure logic), integration (Drizzle/RLS/cache/workers against
  throwaway infra), and frontend component tests (Testing Library).
- **Playwright** (headless Chromium, throwaway stack): user-facing E2E, driving **real local login**
  where automatable (closing the `code-warts.md` TQ1 forged-session wart; OIDC stays forged/documented).

This is distinct from the [phase exit criteria](testing.md#test-strategy-the-test-pyramid): the
pyramid is fast and CI-runnable; the exit criteria include slow acceptance gates (5-day
parallel-stack diff, live-load throughput) no unit test can reproduce. A phase is done when its
checklist is ticked, its automated tests pass in CI, and its exit criteria pass.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Rewriting ingest risks losing/duplicating events during cutover | Parallel-stack validation ([migration.md](components/migration.md)): both stacks ingest live MQTT for 5 days; diff event counts by hash |
| TimescaleDB license/ops concern | Apache-2.0 community edition covers hypertables + CAGGs; if unacceptable, fall back to plain partitioning |
| NATS is a new infra dependency | Single binary, trivial to operate; JetStream persistence is file-backed; well-documented |
| JWT refresh UX complexity | Short-lived access token (5m) + refresh via the signed cookie; transparent to the user |
| Frontend codegen friction | CI gate + `make gen-client` target; generated code is a build artifact |
| Local-password auth becomes a brute-force target | argon2id + exponential lockout (auth.md → local auth) + reverse-proxy rate limiting |
| D5 fold benchmark fails (separate table needed) | Reversible — `raw_receptions.path_hashes` stays either way; hops table is additive |
| Scope creep | Each phase is independently valuable and shippable; we can stop after any phase |
| **Highest-risk migration shape:** greenfield rewrite + language switch (Python→TS) + two new infra deps (NATS, TimescaleDB) + multi-tenancy, all in one program | Sequenced so the language/infra risk is front-loaded (Phases 0–1) and de-risked by the decode-shadow (Phase 1) + parallel-stack (Phase 2) gates before any cutover; multi-tenancy is deferred to Phase 7 (fully additive). See the strategy note below. |

---

## Strategy note — scope realism (F13)

This is a candid caveat, not a decision reversal. The plan is a **from-scratch greenfield rewrite** of a
mature, feature-complete product that *also* switches backend language (Python→TypeScript, D22), adopts
two new infrastructure dependencies (NATS, TimescaleDB), and adds multi-tenancy. That is the highest-risk
combination on the migration-strategy spectrum, and two framing claims deserve qualification:

- **"Each phase is independently valuable and shippable" is true for *value*, not for *production*.**
  Phases 0–5 are not individually production-serviceable: the ingest pipeline (Phase 1) has no schema to
  write into until Phase 2's provisioning; the API (Phase 4) is not useful without auth; the frontend
  (Phase 5) needs the API. The honest statement is that the *program* is shippable at the Phase 6 cutover,
  with earlier phases being internally verifiable milestones. "We can stop after any phase" means we can
  stop *building*, not that an intermediate phase is a deployable product.
- **The strangler-fig alternative was considered and rejected in favour of greenfield** (the iteration-4
  greenfield decision). Worth keeping visible: a strangler approach — the new TS pipeline writing into the
  *existing* database, swapped in component-by-component behind the running Python app — trades the
  greenfield's clean schema for a lower-risk cutover (no big-bang, no 5-day all-or-nothing window). The
  greenfield was chosen because it eliminates the backfill subsystem entirely; the cost is that
  correctness across the whole feature surface must be proven within the parallel-stack window rather than
  incrementally in production.

No timeline or effort estimate is asserted here; the surface (19 tables, ~13 API routers, the full SPA, a
new language, new infra, multi-tenancy) is large, and the phase list is a dependency order, not a
schedule.

## Design retrospective (what shifted across iterations 1–7)

| Iteration | What was proposed | What changed | Why |
|---|---|---|---|
| 1 | Full historical backfill from old DB to new | **Greenfield strategy** (iteration 4): only preserved config migrates; RF repopulates the rest | User insight: "we don't care about historical adverts/messages/packets" — eliminated the riskiest, most complex phase |
| 2 | Redis Streams for the ingest queue | **NATS JetStream** (iteration 2) | User chose NATS — covers durable queue AND fan-out in one tool; Redis narrows to cache only |
| 2 | MD5→SHA-256 hash coexistence for backfilled rows | **Eliminated** (iteration 4): no backfill → no coexistence problem | Greenfield cascaded simplification |
| 2 | orval pending a Phase 0 validation spike | **Committed upfront** (iteration 6): no spike | The `x-invalidates` tag maps cleanly to the invalidation graph; the spike bought insurance we don't need |
| 4 | OIDC required for admin UI access | **Local password store** (D12): OIDC optional, `AUTH_MODE=hybrid` default | User insight: "not many people are willing to maintain an IdP" — biggest deployment-barrier reduction |
| 4 | All config as env vars (200+) | **Three-tier config model** (D11): DB-backed runtime settings + Admin UI | User insight: "move configuration into the API/UI" — no-restart announcements/maintenance/flags |
| 5 | "No CLI at all" | **CLI for ops only** (D18): one config surface per item | User clarification: keep CLI for migrations/management; just don't duplicate config |
| 5 | Optimistic SSE patch everywhere | **Hybrid** (iteration 6): patch unfiltered, invalidate filtered | Filtered views can't safely patch (the new item might not match the filter) |
| 7 | Webhook delivery undesigned; custom pages file-based | **D19** (WebhookWorker NATS subscriber) + **D20** (custom pages to DB) | Gap review: webhook delivery was asserted but never designed; D11's "already DB-backed" claim for custom pages was factually wrong |
| 7 | Single-language assumption (Python) | **D22** (Node/TypeScript backend) | Ecosystem research: the decoder is TS-primary; the NATS JetStream client is first-party in Node. One language for the whole stack. |
| 7 | Single-tenant only | **D21** (multi-tenancy as Phase 7) | Schema already instance-scoped; observer scoping via NATS routing; per-tenant OIDC + hostname resolution. |

**The single biggest scope reduction:** the greenfield strategy (iteration 4) eliminated the entire backfill subsystem — no parallel schemas, no validation gates on historical data, no hash-algorithm coexistence, no resumable checkpointing. What was the riskiest phase became a config export/import of ~5 tables.

---

## What This Document Does NOT Decide

- Specific column renames, new feature fields, or UI redesigns — those are per-phase design tasks.
- Historical data migration — the greenfield strategy (D13/D14, [migration.md](components/migration.md)) explicitly discards all RF-repopulatable data. Only preserved config (user_profiles, routes, tags, adoptions, channels, node stubs) is exported and imported. Raw bytes, messages, adverts, packets — all repopulate from live RF.

## Technology stack (D22)

The backend is **Node/TypeScript** (Fastify 5 + Drizzle ORM + @nats-io/jetstream + mqtt.js). The frontend is React 19 + Vite (unchanged). The packet decoder is `@michaelhart/meshcore-decoder` (the primary TypeScript implementation). See [D22](decisions/D22-node-typescript-backend.md) for the full library mapping and rationale.

Code examples in the component docs are **illustrative pseudocode** showing the design pattern (the shapes, flows, and contracts). The implementation uses the TypeScript stack. The design — NATS subjects, schema DDL, API contract, cache graph, auth boundary — is language-agnostic and does not change.
