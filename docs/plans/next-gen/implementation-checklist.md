# Implementation Checklist

> A single-page reference of everything that needs to happen to ship the rewrite, organised by
> phase. Each item links to the detailed design. Derived from the [phasing plan](phasing.md),
> [component docs](components/), and [exit criteria](testing.md).
>
> **Backend stack (D22):** Node/TypeScript — Fastify 5, Drizzle ORM, @nats-io/nats-core + @nats-io/jetstream,
> mqtt.js, ioredis, Zod, jose (JWT), argon2, commander (CLI),
> `@michaelhart/meshcore-decoder` (primary decoder). See [D22](decisions/D22-node-typescript-backend.md)
> for the full library mapping.
>
> **Testing (D23):** vitest (unit + integration + frontend component) + Playwright (e2e). Every
> component and piece of logic ships with tests at the appropriate layer; the suite is CI-required
> (qualitative coverage, no % floor). See [testing.md → Test strategy](testing.md#test-strategy-the-test-pyramid).
>
> **How to use:** work top-to-bottom within each phase. A phase is done when all its checkboxes
> are ticked, **its automated tests pass in CI** (each phase has a `### Tests` block below), AND
> its [exit criteria](testing.md) pass.

---

## Phase 0 — Foundations

### D5 benchmark (before the schema is authored — F5)
- [ ] Write + run `bench/route_match_benchmark.ts` at Low/Medium/High shapes — [testing.md → D5 plan](testing.md#d5-benchmark-plan-fold-vs-separate)
- [ ] Record the fold-vs-separate decision (fold if `sweep_ms ≤ 1.5×` + `p95 ≤ 500ms` at High); the DDL below reflects the outcome

### Schema
- [ ] Write the initial Drizzle Kit migration for the full [target DDL](components/data-model.md#3-phase-0--schema-ddl-target-authoritative) (enums, entities, hypertables, CAGGs, dashboard rollup tables, RLS policies, retention policies). Hand-author TimescaleDB extension DDL (hypertables, CAGGs, compression, retention) as raw SQL — drizzle-kit handles OLTP tables only.
- [ ] **Instance-scoped uniqueness (F1):** every business-key unique is `UNIQUE (instance_id, …)` — `nodes.public_key`, `messages/advertisements/trace_paths.event_hash`, `channels.name/key_hex`; `settings` PK is `(instance_id, key)`
- [ ] **Only the two `raw_receptions`-sourced CAGGs (F2):** `cagg_daily_packet_counts`, `cagg_packet_breakdown_by_type`. Message/advert/node-count counts are worker-maintained rollup tables (`dashboard_daily_message_counts`, `dashboard_daily_advert_counts`, `dashboard_node_count_history`), NOT CAGGs
- [ ] **Hypertable node references are loose (no FK) (F6):** `raw_receptions.observer_node_id`, `event_observers.observer_node_id`, `telemetry.node_id`, `event_logs.observer_node_id` are plain `uuid` (avoids cross-chunk DML on node cleanup)
- [ ] **RLS hardening (F3):** every policy'd table has `FORCE ROW LEVEL SECURITY`; create the non-owner `meshcore_app` role (DML-only); the app connects as it, migrations run as the owner
- [ ] Verify `drizzle-kit migrate` creates the schema cleanly on a fresh Postgres+TimescaleDB
- [ ] Verify RLS **as the `meshcore_app` role**: a cross-instance query returns 0 rows (running as the owner proves nothing)
- [ ] Seed the `instances` table from `NETWORK_NAME`

### NATS
- [ ] Provision the **single** platform-wide `INGEST` JetStream stream (subject `meshcore.ingest.>`) + one durable consumer `workers` — NOT a per-instance stream (F8)

### Typed decoder models
- [ ] Define Zod `DecodedPacket` schemas matching `@michaelhart/meshcore-decoder` output
- [ ] Build the declarative `CLASSIFIERS` table (payload-type → event-type → handler) — [ingest.md §2](components/ingest.md#2-normalize-to-typed-envelopes-not-dicts)
- [ ] Extract stateless `PacketFields` utility module (composition, not inheritance)

### Tooling
- [ ] Set up `orval` codegen: `orval.config.ts` + `make gen-client` target + CI drift check — [D09](decisions/D09-orval-client-generation.md). **Tooling only** — first real generation happens in Phase 4 against the new API spec.

### Tests
- [ ] Stand up the vitest workspace (unit + integration projects) + Playwright config; wire both into CI ([D23](decisions/D23-test-pyramid-coverage.md))
- [ ] Integration: `drizzle-kit migrate` creates the full schema on a throwaway Postgres+TimescaleDB
- [ ] Integration: RLS — a cross-instance query **as the `meshcore_app` role** returns 0 rows (`FORCE ROW LEVEL SECURITY` verified, not as owner)
- [ ] Unit: Zod `DecodedPacket` schemas accept/reject representative decoder output; the declarative `CLASSIFIERS` table maps every payload-type → event-type → handler

---

## Phase 1 — Ingest pipeline

### NATS infrastructure
- [ ] Provision NATS with JetStream (file-backed persistence volume)
- [ ] Configure the single `INGEST` stream (subject `meshcore.ingest.>`, `duplicate_window=5m`, `max_age=7d`, `WorkQueuePolicy`) — created in Phase 0 (F8)
- [ ] Create the core fan-out subject pattern (`events.new.<inst>.*`)
- [ ] Create the channel-keys subject (`channel.keys.<inst>.updated`)

### MqttIngester (pure decode + produce)
- [ ] Implement `MqttIngester.on_message`: parse topic → observer filter → decode → normalize → classify → produce envelope
- [ ] Implement the [`meshcore.ingest.v1` envelope](components/ingest.md#7-the-ingest-envelope-meshcoreingestv1) Zod schema
- [ ] Implement `ChannelKeyCache`: load on startup, reload on `channel.keys` NATS notification, thread-safe immutable-snapshot swap
- [ ] Set `Nats-Msg-Id` = `wire_hash` for server-side dedup

### IngestWorker (batched write)
- [ ] Implement `IngestWorker.run`: pull-subscribe `meshcore.ingest.>` (wildcard, not `*` — F8), fetch batches of 100, `SET LOCAL app.instance_id`, process, commit, publish `events.new`, ack
- [ ] Implement [`persist_deduped_event`](components/ingest.md#3-dedup-as-a-first-class-service) helper (SHA-256 hash, `ON CONFLICT (instance_id, event_hash) DO NOTHING` — composite target, F1; observer attach)
- [ ] Implement `touchNode` + the observer-node upsert (both keyed on `(instance_id, public_key)`, F1/F11)
- [ ] Implement the 4 structured handlers (~15 LOC each, using the dedup helper)
- [ ] Implement the fallback `handle_event_log` handler

### WebhookWorker (D19)
- [ ] Implement `WebhookWorker`: subscribe to `events.new.<inst>.>`, check Tier-2 webhook settings, dispatch via undici/fetch with 3 retries + exponential backoff
- [ ] Wire the JSONPath-like filter DSL into production (evaluate `filter_expression` against event payload)
- [ ] Verify webhook config reload on `settings.updated.<inst>.webhooks` NATS notification

### Decode/classify shadow validation (F5 — DB-free)
- [ ] Run the `MqttIngester` against the live feed; diff its envelopes (decoded + classified output) against the old normalizer (24h shadow, no DB/workers)
- [ ] Full parallel-stack validation (both DBs, API diff) is **Phase 2** — it needs the provisioned schema + D5 outcome

### Tests
- [ ] Unit: `MqttIngester.on_message` topic-parse → observer-filter → classify (table-driven across payload types); `meshcore.ingest.v1` envelope schema; `Nats-Msg-Id` = `wire_hash`
- [ ] Unit: `persist_deduped_event` SHA-256 hashing + `ON CONFLICT (instance_id, event_hash)` behaviour; the 4 structured handlers + fallback `handle_event_log`
- [ ] Integration: `ChannelKeyCache` load-on-startup + immutable-snapshot reload on `channel.keys` notification
- [ ] Integration: `IngestWorker` batch pull → `SET LOCAL app.instance_id` → commit → `events.new` publish → ack ordering (no ack before commit); server-side dedup suppresses a redelivered `Nats-Msg-Id`
- [ ] Integration: `WebhookWorker` dispatch with retry/backoff + filter-DSL evaluation; config reload on `settings.updated.<inst>.webhooks`

---

## Phase 2 — Greenfield provisioning

### D5 benchmark — done in Phase 0 (F5)
- [ ] (Moved to Phase 0 — the DDL already reflects the fold-vs-separate outcome.) Here: validate the route matcher against real ingested data at the D5 gate.

### Full parallel-stack validation
- [ ] Stand up the new stack alongside the old, both subscribed to the same MQTT, both writing to their own DBs
- [ ] Build the diff harness (per-hour event counts; `wire_hash` coverage — NOT `event_hash`, since MD5≠SHA-256 across stacks — F4)
- [ ] Validate for 5 days (D14); diff = 0 for 3 consecutive days to proceed

### Config migration
- [ ] Implement `meshcore-hub db export-config` on the old stack → JSON bundle
- [ ] Implement `meshcore-hub db import-config` on the new stack → idempotent upsert
- [ ] Verify roundtrip: export from old → import to fresh → all preserved data present with zero FK violations

### Provisioning
- [ ] Provision Postgres 17 + TimescaleDB extension
- [ ] Provision NATS (if not already from Phase 1)
- [ ] Run `drizzle-kit migrate` on fresh DB
- [ ] Run `db import-config config-bundle.json`
- [ ] Enable hypertable compression + retention policies
- [ ] Verify chunk drop works (manually drop one, confirm rows go)
- [ ] Implement `BlobStore` interface (`NoopBlobStore` default) — [ingest.md §5](components/ingest.md#5-raw-capture-compress-in-db-defer-object-storage)
- [ ] D8 measurement: after 1 week of live data, check `hypertable_compression_stats('raw_receptions')` — activate object storage only if compressed size > 50% of DB and growth exceeds budget

### Continuous aggregates + dashboard rollups (F2)
- [ ] Create the **2** CAGGs over `raw_receptions` (`cagg_daily_packet_counts`, `cagg_packet_breakdown_by_type`) `WITH NO DATA`; add refresh policies (5-min schedule, 7-day window)
- [ ] Create the **3** worker-maintained rollup tables (`dashboard_daily_message_counts`, `dashboard_daily_advert_counts`, `dashboard_node_count_history`) — sources are OLTP/entity tables, so they cannot be CAGGs
- [ ] Rewrite dashboard handlers to read CAGGs (with explicit `instance_id` predicate — RLS doesn't propagate to CAGGs) + the rollup tables (no live-query fallback in greenfield)
- [ ] Verify first CAGG buckets + rollup rows populate within 10 min of live ingest

### Tests
- [ ] Integration: `db export-config` → `db import-config` roundtrip on a fresh DB reproduces all preserved config with zero FK violations; re-import is idempotent
- [ ] Integration: the 2 CAGGs + 3 rollup tables exist with active refresh; a dashboard handler reads them with an explicit `instance_id` predicate (no live-query fallback)
- [ ] Integration: `BlobStore` interface with `NoopBlobStore` default; compression/retention policy presence asserted

---

## Phase 3 — Derived state consolidation

### DerivedStateWorker
- [ ] Implement `PeriodicJob` dataclass + `DerivedStateWorker` single-loop scheduler — [derived-state.md → Scheduler implementation](components/derived-state.md#scheduler-implementation)
- [ ] Register the 7 jobs: route-evaluator, route-history, spam-rescore, **dashboard-rollups** (F2), retention, metrics-gauges, cagg-health
- [ ] Implement the two-arg `pg_advisory_xact_lock(job_key, hashtext(instance_id))` per job — stable per-(job, instance) key, not a positional index (two-replica HA — D16; F7)
- [ ] Verify two replicas don't double-execute the same (job, instance)

### Spam scoring
- [ ] Write the `compute_spam_score` PL/pgSQL function — [derived-state.md → Spam rescoring](components/derived-state.md#spam-rescoring-as-a-sql-function-online--sweep)
- [ ] Wire it into the IngestWorker insert path (online score)
- [ ] Wire it into the `spam-rescore` job (symmetric sweep) — compute the score **once** per row in a subquery, filter + write from that value (do not call the function in both `WHERE` and `SET` — F10)
- [ ] Verify parity: 24h replay, per-message score diff within ε

### Route health
- [ ] Rewrite the matcher against `raw_receptions.path_hashes` (or the D5-decided schema)
- [ ] Implement the 3 worker-maintained tables (`route_results`, `route_result_history`, `route_recent_matches`)
- [ ] Implement `computeQualityAvg()` — ordinal mapping (clear=2, marginal=1, else=0), thresholds (≥1.5→clear, ≥0.75→marginal, else failing), brand-new-route null edge case — [derived-state.md](components/derived-state.md#route-quality-averaging-route-history-job)
- [ ] Verify frontend `qualityOf()` fallback chain: `quality_avg || quality || "unknown"`
- [ ] Sync the clear/marginal thresholds (1.5 / 0.75) between backend `computeQualityAvg` and frontend `averageRouteTier` chart helper
- [ ] Verify first evaluation tick rebuilds all three from fresh data

### Retention
- [ ] Activate TimescaleDB retention policies on hypertables (30-day default)
- [ ] Implement chunked DELETE for OLTP tables (`messages`, `advertisements`, `trace_paths`) — 5000-row batches
- [ ] Verify row counts stabilise at the retention boundary

### Tests
- [ ] Unit: `computeQualityAvg` ordinal mapping (clear=2/marginal=1/else=0) + thresholds (≥1.5/≥0.75) + brand-new-route null edge; the `PeriodicJob` scheduler cadence math
- [ ] Unit: route-matcher subsequence algorithm against `path_hashes` (true positives + false-positive rejection)
- [ ] Integration: two-replica advisory-lock — two `DerivedStateWorker`s never double-execute the same `(job, instance)` (`pg_advisory_xact_lock(job_key, hashtext(instance_id))`)
- [ ] Integration: `compute_spam_score` PL/pgSQL online + sweep parity (score computed once per row — not in both `WHERE` and `SET`, F10); the 3 route-health tables rebuild from fresh data
- [ ] Integration: chunked retention DELETE batches OLTP rows and stabilises at the boundary

---

## Phase 4 — API & auth

### Async ORM
- [ ] All route handlers are `async` with Drizzle ORM over `node-postgres`
- [ ] **Per-request transaction (F3):** a Fastify `preHandler` opens a transaction and issues `SET LOCAL app.instance_id` from the `Principal` for **every** request (reads included — `SET LOCAL` outside a tx is a no-op → RLS returns 0 rows)
- [ ] App connects as the non-owner `meshcore_app` role so `FORCE ROW LEVEL SECURITY` applies
- [ ] Verify the pool correctly scopes transactions (advisory lock + RLS), including read endpoints

### Auth
- [ ] Implement `AuthMiddleware` preHandler (JWT → cookie → API key → anonymous) — [auth.md](components/auth.md#authmiddleware-single-resolution-point)
- [ ] Implement `Principal` frozen object + resolution from JWT claims / session cookie / API key
- [ ] Implement JWT issuance in the web tier (5m access, HS256, `JWT_SESSION_SECRET`)
- [ ] Implement session-cookie sliding renewal (7d, JWS via `jose`)
- [ ] Implement local password store: `local_users` table, argon2id verify, exponential lockout
- [ ] Implement the shared 3-table bootstrap insert (user_profiles + local_users + user_profile_roles) in one transaction
- [ ] Implement bootstrap paths: env-var (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), CLI (`admin create-user`), setup wizard — all use the shared insert
- [ ] Implement the first-run setup wizard **backend** (F12 — SPA route, not SSR): a `needs_setup` boolean in `/api/v1/config`, a gate middleware redirecting all routes to `/setup` while it is true, and the JSON `GET/POST /setup` API. Server-rendering is a documented fallback only. The React wizard page itself lands in Phase 5
- [ ] Implement `/auth/login`, `/auth/logout` (local) + `/auth/callback` (OIDC)
- [ ] Remove all `X-User-*` header injection

### Cache contract
- [ ] Implement the single `{instance_id}:{namespace}:{scope}:{query_hash}` key format — the `instance_id` prefix is required so tenants never share a cache entry (F3) — [api.md → Unified cache contract](components/api.md#unified-cache-contract-concrete)
- [ ] Implement the `NAMESPACES` / `ENTITY_INVALIDATION` declarative graph
- [ ] Implement the async `@cached` decorator (ETag, If-None-Match, 304, X-Cache header)
- [ ] Implement `invalidate_for(entity_changes, cache, instance_id)`
- [ ] Replace every mutation handler's invalidation call with `invalidate_for`

### SSE
- [ ] Implement `GET /api/v1/events/stream` (NATS subscribe → raw `reply.raw` streaming) — [api.md → SSE Auth](components/api.md#sse-auth-cookie-based-proxy-transparent)
- [ ] Per-event channel-visibility filter
- [ ] 15s heartbeat; bounded backpressure (NATS pending-msg cap 256)
- [ ] Web tier proxy: verify it pipes SSE chunks without buffering (streaming proxy, not buffered)
- [ ] If single-process mode: enable the AuthMiddleware cookie source (the 2nd resolution step, between JWT-header and API-key — a no-op in split web/API deployments; see auth.md)

### Settings API
- [ ] Create the `settings` table + seed migration (defaults per known key)
- [ ] Implement `SettingsCache` (in-memory snapshot, NATS-refreshed)
- [ ] Implement `GET /api/v1/config` (public, cacheable), `GET /api/v1/me`, `GET/PUT /api/v1/settings` (admin)
- [ ] Wire `settings.updated.<inst>.<category>` NATS publish after mutation

### Channel visibility
- [ ] Implement single `apply_visibility(query, principal)` construct — replaces the 3 redaction copies
- [ ] Pre-resolve `channel_indices` in the `Principal` (cached per role-tier)

### Custom pages API (D20)
- [ ] Implement `GET /api/v1/pages` (public, enabled only, sorted by menu_order) + `GET /api/v1/pages/{slug}`
- [ ] Implement `POST/PUT/DELETE /api/v1/pages` (admin CRUD)
- [ ] Include enabled pages list in `PublicConfig` response (drives nav)
- [ ] Mutations invalidate `pages` + `config` namespaces

### Tests
- [ ] Unit: `AuthMiddleware` resolution order (JWT → cookie → API key → anonymous); `Principal` claim mapping; cache-key builder `{instance_id}:{namespace}:{scope}:{query_hash}`; single `apply_visibility` construct
- [ ] Unit: argon2id verify + exponential-lockout backoff math; the shared 3-table bootstrap insert shape
- [ ] Integration (Fastify `inject`): per-request transaction issues `SET LOCAL app.instance_id` on **read** endpoints too (RLS returns rows, not 0); cross-instance read returns 0 rows
- [ ] Integration: `@cached` ETag / If-None-Match / 304 / X-Cache round-trip; `invalidate_for` walks the `ENTITY_INVALIDATION` graph and evicts the right namespaces
- [ ] Integration: local login + OIDC callback converge on the same JWT/cookie issuance; SSE pushes with per-message channel-visibility filter + 15s heartbeat
- [ ] Integration: settings + custom-pages mutations invalidate `settings`/`pages`/`config` and surface in `PublicConfig`

---

## Phase 5 — Frontend

### Generated client
- [ ] Run `make gen-client` against the full OpenAPI spec
- [ ] Delete every hand-written `interface NodeItem`/`Channel`/`Profile` copy
- [ ] Annotate mutations with `x-invalidates` tags mapping to the `ENTITY_INVALIDATION` graph

### Code-splitting
- [ ] Add `lazy()` imports for Dashboard, Map, Routes, CustomPage
- [ ] Configure Vite `manualChunks` for vendor-react, vendor-query, vendor-charts, vendor-map, vendor-markdown
- [ ] Verify initial chunk < 180 KB

### Static shell
- [ ] Make the HTML shell a build-time artifact (no per-request inlining)
- [ ] Implement `main.tsx` bootstrap: `Promise.all([apiGet('/config'), apiGet('/me')])` → render
- [ ] Add `Cache-Control: public, max-age=60` on `/api/v1/config`

### SSE-driven live pages
- [ ] Implement `useEventStream(eventTypes)` hook — [frontend.md → SSE-driven live pages](components/frontend.md#sse-driven-live-pages)
- [ ] Hybrid strategy: patch for unfiltered views, invalidate for filtered
- [ ] Wire into Messages, Packets, Dashboard

### Auth UI
- [ ] Login page (local form / OIDC button / both per `auth_mode`)
- [ ] First-run setup wizard (React, but server-gated)
- [ ] Users admin page (local CRUD + OIDC role overrides — DB-additive)
- [ ] Settings admin page (category-grouped forms)
- [ ] Pages admin page (D20 — custom pages CRUD with markdown editor + live preview)

### Cleanup
- [ ] Remove legacy vendored assets (`lit-html`, `qrcodejs`)
- [ ] Remove the per-request `__APP_CONFIG__` inlining
- [ ] Replace all `alert()` with toast notifications
- [ ] Unify title management (one path)

### Tests
- [ ] Component (vitest + Testing Library): `useEventStream` hybrid patch/invalidate + 30s poll fallback; generated-client wrappers; login page renders local/OIDC/both per `auth_mode`
- [ ] Component: Settings / Users / Pages admin pages; `averageRouteTier` threshold sync with backend `computeQualityAvg` (1.5/0.75)
- [ ] E2E (Playwright, real local login — [D23](decisions/D23-test-pyramid-coverage.md)): login → dashboard; Messages/Packets SSE live update; create/edit/delete a custom page and see the nav update
- [ ] E2E: first-run setup wizard flow; settings/feature-flag change propagates to an open tab via SSE

---

## Phase 6 — Polish & decommission

### Old-stack decommission
- [ ] Parallel-stack diff clean for 3 consecutive days within the 5-day window (D14)
- [ ] Cut over DNS / reverse-proxy / MQTT exclusivity
- [ ] Stop old containers; retain volumes 30 days, then destroy

### Security hardening
- [ ] RLS audit: cross-instance query returns 0 rows on every tenant-scoped table
- [ ] Rate-limit review: local-login lockout + reverse-proxy rules
- [ ] JWT rotation drill: rotate secret, verify graceful session invalidation
- [ ] Dependency audit: `npm audit` clean (backend + frontend)

### Documentation
- [ ] Write new `AGENTS.md` / `CONTRIBUTING.md` from [code-warts.md](code-warts.md) lessons
- [ ] Update README, deployment guide, observer guide, configuration reference
- [ ] Operator migration guide (old → new)
- [ ] Verify Swagger/ReDoc clean with response schemas on every endpoint

### Performance validation
- [ ] Load test: N observers × M packets/sec; NATS backlog bounded; IngestWorker throughput ≥ 5× old
- [ ] Dashboard p95 < 200ms under load
- [ ] Route evaluator p95 < 500ms per route at D5 High shape

### Tests
- [ ] Integration: RLS audit suite — cross-instance query returns 0 rows on **every** tenant-scoped table (including route-health tables)
- [ ] Integration: JWT rotation — rotate `JWT_SESSION_SECRET`, assert in-flight sessions invalidate gracefully
- [ ] CI gate: `npm audit` clean (backend + frontend) enforced as a required check

---

## Phase 7 — Multi-tenancy (self-provisioning)

### Registration (self-service tenant creation)
- [ ] Implement `POST /api/v1/register` (public): validate subdomain, create instance + hostname + settings seed + admin bootstrap in one transaction — [multi-tenancy.md §8](components/multi-tenancy.md#creation-self-service-registration--no-platform-operator-action)
- [ ] Implement `GET /api/v1/register/check?subdomain=...` (live availability check)
- [ ] Build the registration page at the platform root domain (`PLATFORM_DOMAIN/register`)
- [ ] Implement platform-level settings (`registration.enabled`, `registration.rate_limit_per_ip`, `registration.require_captcha`, `registration.subdomain_reserved`)
- [ ] Publish `instance.created` on NATS after commit; verify all caches reload

### Observer scoping (D21)
- [ ] Create `tenant_observers` table (instance_id, observer_pubkey_prefix, label)
- [ ] Implement observer allowlist CRUD API (`GET/POST/PUT/DELETE /api/v1/observers`, admin-gated) — each row carries an optional per-tenant friendly name (`label`); `PUT` renames the label only (no ingester reload, routing is prefix-keyed)
- [ ] Implement `ObserverAllowlistCache` in MqttIngester (read-only snapshot, NATS reload on `observer.allowlist.updated.*`)
- [ ] Implement multi-tenant produce: `route(observer_pubkey) → set[tenant_id]`, publish to each tenant's NATS subject
- [ ] Tenant-prefix `Nats-Msg-Id` (`{tenant_id}:{wire_hash}`) for per-tenant JetStream dedup
- [ ] Empty allowlist = all observers (`_allow_all_tenants` set in routing cache)

### Shared worker pool (dynamic tenant discovery)
- [ ] IngestWorker: subscribe to `meshcore.ingest.>` (wildcard — all tenants); set `SET LOCAL app.instance_id` per batch from the envelope
- [ ] DerivedStateWorker: query active instances at startup + on `instance.created`/`instance.deleted`; run job manifest per instance with per-instance advisory lock keys
- [ ] WebhookWorker: subscribe to `events.new.>` (wildcard); load per-tenant settings from `SettingsCache`
- [ ] Verify new-tenant pickup: register a tenant → workers process their traffic within seconds, zero operator action

### ChannelKeyCache multi-tenant
- [ ] Load channel keys for ALL instances at startup (`dict[instance_id, frozenset[ChannelKey]]`)
- [ ] Reload per-tenant on `channel.keys.<inst>.updated`
- [ ] Tag decrypted `channel_idx` with the matching `instance_id`

### Per-tenant OIDC
- [ ] Create `tenant_oidc_configs` table (discovery_url, client_id, client_secret encrypted, auth_mode)
- [ ] Implement OIDC config resolution: per-tenant DB → platform env fallback → local-only
- [ ] Implement OIDC config CRUD API (admin-gated, client_secret write-only)
- [ ] Web tier resolves OIDC config per tenant for login/callback flows

### Instance resolution
- [ ] Create `instance_hostnames` table (hostname → instance_id, is_primary, is_custom, added_at)
- [ ] Implement `HostnameCache` (read-only snapshot, NATS reload on `hostname.updated`)
- [ ] Implement `InstanceResolutionMiddleware`: JWT claim → hostname → `DEFAULT_INSTANCE_ID` fallback
- [ ] Configure wildcard DNS (`*.PLATFORM_DOMAIN`) + wildcard TLS certificate
- [ ] Custom domains API: `POST /api/v1/domains` (add), `GET /api/v1/domains` (list), `DELETE /api/v1/domains/:hostname` (remove custom), `PUT /api/v1/domains/:hostname/primary` (promote) — [multi-tenancy.md §7](components/multi-tenancy.md#custom-domains)
- [ ] Custom domain TLS: configure reverse proxy for on-demand ACME (caddy built-in / certbot hook / traefik tlsChallenge)
- [ ] Admin UI: Settings → Community → custom domain management (add/remove/promote, CNAME target display)

### Tenant management (CLI fallback)
- [ ] CLI: `admin create-instance --name --hostname --admin-username --admin-password` (same transaction as registration API)
- [ ] CLI: `admin delete-instance --name` (soft-delete: sets `deleted_at`, hostname 404s, reversible via `undelete-instance`)
- [ ] CLI: `admin purge-instance --name` (hard-delete: explicit multi-table deletion in dependency order, then instance row)
- [ ] CLI: `admin undelete-instance --name` (clears `deleted_at`)
- [ ] CLI: `admin list-instances` (show deleted vs. active)
- [ ] Hostname cache excludes soft-deleted instances (`deleted_at IS NULL`)

### Admin UI
- [ ] `/admin/observers` page (allowlist CRUD + known-observer picker from `nodes WHERE is_observer`, pre-filling the friendly name from the node's known name; stored as a per-tenant `label`; inline rename)
- [ ] Settings → Authentication section (per-tenant OIDC config form)
- [ ] Settings → Community section (custom domain management, soft-delete community)
- [ ] Landing page at platform root with "Create your community" flow

### Tests
- [ ] Unit: `ObserverAllowlistCache` routing (`route(observer_pubkey) → set[tenant_id]`, `_allow_all_tenants` on empty allowlist); subdomain validation + reserved-list; tenant-prefix `Nats-Msg-Id`
- [ ] Integration: tenant isolation — cross-instance query returns 0 rows on every tenant-scoped table after registering two tenants; a shared observer yields one dedup'd event **per tenant**
- [ ] Integration: `HostnameCache` excludes soft-deleted instances; `InstanceResolutionMiddleware` (JWT claim → hostname → `DEFAULT_INSTANCE_ID`)
- [ ] E2E (Playwright, real login): register a tenant → land on subdomain logged in → manage observer allowlist (picker pre-fills the friendly name, inline rename) → add a custom domain; second tenant on the same deployment is isolated
- [ ] E2E: per-tenant auth — tenant A local-only vs tenant B renders its own IdP button per hostname (OIDC callback itself stays forged/documented per D23)
