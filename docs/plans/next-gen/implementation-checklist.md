# Implementation Checklist

> A single-page reference of everything that needs to happen to ship the rewrite, organised by
> phase. Each item links to the detailed design. Derived from the [phasing plan](phasing.md),
> [component docs](components/), and [exit criteria](testing.md).
>
> **Backend stack (D22):** Node/TypeScript — Fastify 5, Drizzle ORM, @nats-io/nats-core + @nats-io/jetstream,
> mqtt.js, ioredis, Zod, jose (JWT), argon2, commander (CLI), vitest (tests),
> `@michaelhart/meshcore-decoder` (primary decoder). See [D22](decisions/D22-node-typescript-backend.md)
> for the full library mapping.
>
> **How to use:** work top-to-bottom within each phase. A phase is done when all its checkboxes
> are ticked AND its [exit criteria](testing.md) pass.

---

## Phase 0 — Foundations

### Schema
- [ ] Write the initial Drizzle Kit migration for the full [target DDL](components/data-model.md#3-phase-0--schema-ddl-target-authoritative) (enums, entities, hypertables, CAGGs, RLS policies, retention policies). Hand-author TimescaleDB extension DDL (hypertables, CAGGs, compression, retention) as raw SQL — drizzle-kit handles OLTP tables only.
- [ ] Verify `drizzle-kit migrate` creates the schema cleanly on a fresh Postgres+TimescaleDB
- [ ] Verify RLS: a cross-instance query returns 0 rows
- [ ] Seed the `instances` table from `NETWORK_NAME`

### Typed decoder models
- [ ] Define Zod `DecodedPacket` schemas matching `@michaelhart/meshcore-decoder` output
- [ ] Build the declarative `CLASSIFIERS` table (payload-type → event-type → handler) — [ingest.md §2](components/ingest.md#2-normalize-to-typed-envelopes-not-dicts)
- [ ] Extract stateless `PacketFields` utility module (composition, not inheritance)

### Tooling
- [ ] Set up `orval` codegen: `orval.config.ts` + `make gen-client` target + CI drift check — [D09](decisions/D09-orval-client-generation.md). **Tooling only** — first real generation happens in Phase 4 against the new API spec.

---

## Phase 1 — Ingest pipeline

### NATS infrastructure
- [ ] Provision NATS with JetStream (file-backed persistence volume)
- [ ] Create the ingest stream (`INGEST-<inst>`, `duplicate_window=5m`, `max_age=7d`, `WorkQueuePolicy`)
- [ ] Create the core fan-out subject pattern (`events.new.<inst>.*`)
- [ ] Create the channel-keys subject (`channel.keys.<inst>.updated`)

### MqttIngester (pure decode + produce)
- [ ] Implement `MqttIngester.on_message`: parse topic → observer filter → decode → normalize → classify → produce envelope
- [ ] Implement the [`meshcore.ingest.v1` envelope](components/ingest.md#172-the-ingest-envelope-meshcoreingestv1) Zod schema
- [ ] Implement `ChannelKeyCache`: load on startup, reload on `channel.keys` NATS notification, thread-safe immutable-snapshot swap
- [ ] Set `Nats-Msg-Id` = `wire_hash` for server-side dedup

### IngestWorker (batched write)
- [ ] Implement `IngestWorker.run`: pull-subscribe `meshcore.ingest.*`, fetch batches of 100, `SET LOCAL app.instance_id`, process, commit, publish `events.new`, ack
- [ ] Implement [`persist_deduped_event`](components/ingest.md#74-dedup-as-a-first-class-service) helper (SHA-256 hash, `ON CONFLICT DO NOTHING`, observer attach)
- [ ] Implement the 4 structured handlers (~15 LOC each, using the dedup helper)
- [ ] Implement the fallback `handle_event_log` handler

### WebhookWorker (D19)
- [ ] Implement `WebhookWorker`: subscribe to `events.new.<inst>.>`, check Tier-2 webhook settings, dispatch via undici/fetch with 3 retries + exponential backoff
- [ ] Wire the JSONPath-like filter DSL into production (evaluate `filter_expression` against event payload)
- [ ] Verify webhook config reload on `settings.updated.<inst>.webhooks` NATS notification

### Parallel-stack validation
- [ ] Stand up new stack alongside old, both subscribed to the same MQTT
- [ ] Build the diff harness (per-hour event counts by hash, old API vs new API)
- [ ] Validate for 5 days (D14); diff = 0 for 3 consecutive days to proceed

---

## Phase 2 — Greenfield provisioning

### D5 benchmark (before schema freeze)
- [ ] Write `bench/route_match_benchmark.ts` — [testing.md → D5 plan](testing.md#d5-benchmark-plan-fold-vs-separate)
- [ ] Run at Low/Medium/High dataset shapes
- [ ] Record decision: fold (F) if `sweep_ms ≤ 1.5×` + `p95 ≤ 500ms` at High; else separate (S)
- [ ] Freeze schema accordingly

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

### Continuous aggregates
- [ ] Create the 5 CAGGs (`WITH NO DATA`) via migration
- [ ] Add refresh policies (5-min schedule, 7-day window)
- [ ] Rewrite dashboard handlers to read CAGGs (no live-query fallback in greenfield)
- [ ] Verify first buckets populate within 10 min of live ingest

---

## Phase 3 — Derived state consolidation

### DerivedStateWorker
- [ ] Implement `PeriodicJob` dataclass + `DerivedStateWorker` single-loop scheduler — [derived-state.md → Scheduler implementation](components/derived-state.md#scheduler-implementation)
- [ ] Register the 6 jobs: route-evaluator, route-history, spam-rescore, retention, metrics-gauges, cagg-health
- [ ] Implement `pg_advisory_xact_lock` per job (two-replica HA — D16)
- [ ] Verify two replicas don't double-execute the same job

### Spam scoring
- [ ] Write the `compute_spam_score` PL/pgSQL function — [derived-state.md → Spam rescoring](components/derived-state.md#spam-rescoring-as-a-sql-function-online--sweep)
- [ ] Wire it into the IngestWorker insert path (online score)
- [ ] Wire it into the `spam-rescore` job (symmetric sweep)
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

---

## Phase 4 — API & auth

### Async ORM
- [ ] All route handlers are `async` with Drizzle ORM over `node-postgres`
- [ ] Connection pool sized for async concurrency; `SET LOCAL app.instance_id` hook on the pool
- [ ] Verify the pool correctly scopes transactions (advisory lock + RLS)

### Auth
- [ ] Implement `AuthMiddleware` preHandler (JWT → cookie → API key → anonymous) — [auth.md](components/auth.md#authmiddleware-single-resolution-point)
- [ ] Implement `Principal` frozen object + resolution from JWT claims / session cookie / API key
- [ ] Implement JWT issuance in the web tier (5m access, HS256, `JWT_SESSION_SECRET`)
- [ ] Implement session-cookie sliding renewal (7d, JWS via `jose`)
- [ ] Implement local password store: `local_users` table, argon2id verify, exponential lockout
- [ ] Implement the shared 3-table bootstrap insert (user_profiles + local_users + user_profile_roles) in one transaction
- [ ] Implement bootstrap paths: env-var (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), CLI (`admin create-user`), setup wizard — all use the shared insert
- [ ] Implement the first-run setup wizard (5-step, server-rendered, `needsSetup` flag gated on the admin-existence query)
- [ ] Implement `/auth/login`, `/auth/logout` (local) + `/auth/callback` (OIDC)
- [ ] Remove all `X-User-*` header injection

### Cache contract
- [ ] Implement the single `{namespace}:{scope}:{query_hash}` key format — [api.md → Unified cache contract](components/api.md#unified-cache-contract-concrete)
- [ ] Implement the `NAMESPACES` / `ENTITY_INVALIDATION` declarative graph
- [ ] Implement the async `@cached` decorator (ETag, If-None-Match, 304, X-Cache header)
- [ ] Implement `invalidate_for(entity_changes, cache, instance_id)`
- [ ] Replace every mutation handler's invalidation call with `invalidate_for`

### SSE
- [ ] Implement `GET /api/v1/events/stream` (NATS subscribe → raw `reply.raw` streaming) — [api.md → SSE Auth](components/api.md#sse-auth-cookie-based-proxy-transparent)
- [ ] Per-event channel-visibility filter
- [ ] 15s heartbeat; bounded backpressure (NATS pending-msg cap 256)
- [ ] Web tier proxy: verify it pipes SSE chunks without buffering (streaming proxy, not buffered)
- [ ] If single-process mode: add cookie resolution path to AuthMiddleware (4th source after JWT-header / API-key / anonymous)

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
- [ ] Implement observer allowlist CRUD API (`GET/POST/DELETE /api/v1/observers`, admin-gated)
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
- [ ] `/admin/observers` page (allowlist CRUD + known-observer picker from `nodes WHERE is_observer`)
- [ ] Settings → Authentication section (per-tenant OIDC config form)
- [ ] Settings → Community section (custom domain management, soft-delete community)
- [ ] Landing page at platform root with "Create your community" flow
