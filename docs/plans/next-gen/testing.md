# Testing & Validation — Strategy, Policy & Phase Exit Criteria

> Consolidated validation plan for the MeshCore Hub rewrite. Two complementary axes:
> (1) the **test pyramid** — fast, CI-runnable regression tests authored with the code
> ([below](#test-strategy-the-test-pyramid), locked in [D23](decisions/D23-test-pyramid-coverage.md));
> and (2) **phase exit criteria** — the acceptance gates each phase ships behind. Cross-cutting
> benchmarks are listed at the end. Phase context lives in [phasing.md](phasing.md).

## Test strategy (the test pyramid)

Locked in [D23](decisions/D23-test-pyramid-coverage.md). **Every rewritten component and every
piece of business logic ships with automated tests at the appropriate layer, and the suite must
pass in CI.** Coverage is qualitative — deliberately **no numeric floor**.

| Layer | Runner | Infra | Owns |
|---|---|---|---|
| **Unit** | vitest | none | Pure logic: classifier table, dedup hash, `computeQualityAvg`, spam-score wrapper, cache-key builder, `apply_visibility`, the `meshcore.ingest.v1` envelope Zod schema, webhook filter DSL, `PacketFields`. |
| **Integration** | vitest | dev-compose / throwaway Postgres+NATS+Redis | DB- and bus-touching paths: Drizzle repositories, RLS enforcement (`SET LOCAL app.instance_id`), the `@cached` decorator + declarative invalidation graph, `IngestWorker` batch-commit + ack ordering, `ChannelKeyCache`/`ObserverAllowlistCache` reload, `SettingsCache`, API handlers via Fastify `inject`. |
| **Frontend component** | vitest + Testing Library | jsdom | `useEventStream`, generated-client wrappers, admin pages (Settings/Users/Pages/Observers), chart helpers (`averageRouteTier` threshold sync), login rendering per `auth_mode`. |
| **E2E** | Playwright (headless Chromium) | throwaway stack (own Postgres, isolated volumes) | User flows: registration → login → admin → observer allowlist; SSE live updates; custom pages; settings. |

vitest is the single runner for the first three layers (D22); Playwright is the only second
runner, used solely for browser E2E.

**E2E auth — real login, forged only where unavoidable (closes `code-warts.md` TQ1):** specs drive
the real local-login flow (argon2id `local_users` path, D12). Session forging is permitted **only**
for the un-automatable OIDC callback, and is documented in the spec directory so the divergence
from production auth stays visible.

### Component → required layers

| Component | Unit | Integration | Frontend | E2E |
|---|:---:|:---:|:---:|:---:|
| [ingest.md](components/ingest.md) | ✓ | ✓ | | |
| [data-model.md](components/data-model.md) (repos, RLS) | | ✓ | | |
| [derived-state.md](components/derived-state.md) | ✓ | ✓ | | |
| [auth.md](components/auth.md) | ✓ | ✓ | ✓ | ✓ |
| [api.md](components/api.md) (cache, SSE, settings, pages) | ✓ | ✓ | | ✓ |
| [frontend.md](components/frontend.md) | | | ✓ | ✓ |
| [multi-tenancy.md](components/multi-tenancy.md) | ✓ | ✓ | ✓ | ✓ |
| [migration.md](components/migration.md) (export/import) | ✓ | ✓ | | |

> The exit criteria below are the **acceptance gates** for each phase; some are slow runtime
> observations (5-day parallel-stack diff, live-load throughput) that no unit test can reproduce.
> They complement the pyramid — a phase is done when its checkboxes are ticked, **its automated
> tests pass in CI**, and its exit criteria pass. Per-phase test deliverables are itemised in the
> [implementation checklist](implementation-checklist.md).

## Phase 1 — Ingest pipeline

- [ ] `MqttIngester` decodes + classifies identically to the old normalizer (diff = 0 over a 24h shadow run).
- [ ] `IngestWorker` batch throughput ≥ 5× the old single-threaded path under burst load.
- [ ] JetStream survives a worker kill -9 mid-batch with zero lost envelopes (ack-after-commit ordering).
- [ ] `channel.keys` refresh propagates to the ingester in <1s after a channel mutation.
- [ ] Server-side dedup (`Nats-Msg-Id`) suppresses MQTT redelivery with zero double-inserts.
- [ ] `WebhookWorker` dispatches matching events with correct retry/backoff; filter DSL evaluates correctly; config reload on `settings.updated.webhooks` works.

## Phase 0 — Foundations (added exit gate)

- [ ] **D5 benchmark decided fold-vs-separate**, decision recorded, target schema frozen accordingly — this runs in Phase 0, **before** the DDL migration is authored (it needs only a throwaway TimescaleDB; see [D5 plan](#d5-benchmark-plan-fold-vs-separate)). The schema is not frozen until the outcome is known.

## Phase 2 — Greenfield provisioning

- [ ] `db export-config` on the old stack produces a complete bundle; `db import-config` on a fresh DB reproduces user_profiles + roles, routes + nodes + observers, node_tags, adoptions, (channels) with zero FK violations.
- [ ] New infrastructure provisioned; `drizzle-kit migrate` creates the full schema cleanly; RLS policies enforced **as the non-owner `meshcore_app` role with `FORCE ROW LEVEL SECURITY`** (a cross-instance query returns 0 rows; verify the check runs as the app role, not the table owner).
- [ ] The **two** CAGGs (`cagg_daily_packet_counts`, `cagg_packet_breakdown_by_type`, over `raw_receptions`) created with active refresh policies; the **three** worker-maintained rollup tables (`dashboard_daily_message_counts`, `dashboard_daily_advert_counts`, `dashboard_node_count_history`) populated by the `dashboard-rollups` job; first buckets/rows populate within 10 minutes of live ingest.
- [ ] Dashboard CAGG reads carry an explicit `instance_id` predicate (RLS does not propagate to continuous aggregates); rollup tables enforce RLS like any tenant table.
- [ ] Hypertable compression + retention policies active and verified on all four hypertables (`raw_receptions`, `event_observers`, `telemetry`, `event_logs`): drop a chunk manually, confirm rows go; verify `event_observers` segments by `event_type` (query by event_type hits compressed batches correctly).
- [ ] Parallel-stack diff harness reports 0 divergence for 3 consecutive days within the 5-day window (D14).

## Phase 3 — Derived state consolidation

- [ ] All six daemon threads removed from the collector; the collector is now MQTT-receive-only (it just runs the MqttIngester).
- [ ] `DerivedStateWorker` runs all jobs; two-replica HA confirmed (advisory lock prevents double-execution).
- [ ] Spam scoring matches today's output on a 24h replay (per-message `spam_score` diff within ε).
- [ ] Route health tables rebuild correctly from `raw_receptions.path_hashes`; per-route `total_route_ms` within the D5 gate.
- [ ] `quality_avg` matches today's output on a 7-day replay: for each route, the rolling 7-day ordinal average (clear=2, marginal=1, else=0; thresholds ≥1.5/≥0.75) produces the same tier as the old `compute_persisted_quality_avg`.
- [ ] Retention enforces 30-day windows via chunk drops (verify `raw_receptions` row count stabilises).
- [ ] Dashboard endpoints read the CAGGs + the worker-maintained rollup tables exclusively; live-query fallback removed. The `dashboard-rollups` job maintains the message/advert/node-count rollups.

## Phase 4 — API & auth

- [ ] `AuthMiddleware` resolves a `Principal` from JWT / API key / anonymous; no handler reads `X-User-*` headers.
- [ ] Access JWT (5m) + session cookie (7d sliding) verified end-to-end; local login + OIDC callback both converge on the same issuance.
- [ ] Local password store: argon2id verify, exponential lockout, bootstrap admin via any of the three paths (env var / `admin create-user` CLI / setup wizard).
- [ ] `@cached` uses the single `{namespace}:{scope}:{query_hash}` key; the declarative invalidation graph replaces every hand-coded helper.
- [ ] SSE endpoint pushes live events; channel-visibility filter enforced per message; idle-clients survive 15s heartbeats.
- [ ] Settings API: `/config` (public), `/me`, `/settings` (admin), all reading/writing the `settings` table with category validation + NATS invalidation.
- [ ] Custom pages API: public list/detail, admin CRUD; `PublicConfig` includes enabled pages; mutations invalidate `pages` + `config` namespaces.

## Phase 5 — Frontend

- [ ] Generated client adopted for all pages; zero hand-written `interface NodeItem`/`Channel`/`Profile` copies remain.
- [ ] Initial JS chunk < 180 KB; Dashboard/Map/Markdown load lazily; Lighthouse first-contentful-paint improves ≥ 3×.
- [ ] Static shell cacheable (`Cache-Control: public`); `/api/v1/config` + `/api/v1/me` bootstrap; no per-request `__APP_CONFIG__` inlining.
- [ ] `useEventStream` drives Messages/Packets/Dashboard live updates; 30s poll is the fallback; SSE drop + recover verified.
- [ ] Login page renders local form / OIDC button / both per `auth_mode`; local 401 shows inline error.
- [ ] Settings + Users admin pages functional; feature flags toggle at runtime; branding change propagates to open tabs via SSE within seconds.
- [ ] Pages admin page: create/edit/delete custom pages with markdown editor; nav updates reflect changes.

## Phase 7 — Multi-tenancy (self-provisioning)

- [ ] **Self-service registration:** `POST /api/v1/register` creates a fully operational tenant (instance + hostname + settings + admin) in one transaction; the admin is redirected to their subdomain, logged in, with zero CLI/operator action.
- [ ] **Subdomain availability:** duplicate subdomain returns 409; reserved subdomains rejected; live check endpoint works.
- [ ] **Worker pickup:** after registration, the new tenant's packets are ingested, derived-state jobs run, and webhooks fire — all within one evaluator tick (≤300s), with no worker restart or Compose change.
- [ ] **Tenant isolation:** two tenants on one deployment; cross-instance queries return 0 rows on every tenant-scoped table (including `route_results`, `route_result_history`, `route_recent_matches`).
- [ ] **Shared observers:** an observer in two tenants' allowlists produces one dedup'd event per tenant; `Nats-Msg-Id` tenant-prefix prevents JetStream dedup suppression.
- [ ] **Per-tenant OIDC:** tenant A uses local-only, tenant B uses a different IdP; login pages render correctly per hostname.
- [ ] **Custom domains:** tenant admin adds a custom hostname via `POST /api/v1/domains`; after DNS CNAME is configured, the tenant is reachable at both the subdomain and the custom domain. TLS is provisioned automatically (ACME). The custom domain can be promoted to primary; the subdomain cannot be removed. Removing a custom domain stops routing within one cache reload cycle.
- [ ] **Soft-delete:** tenant admin deletes their community; hostname 404s within seconds; existing JWTs expire naturally; `undelete-instance` restores access.
- [ ] **Registration abuse controls:** rate limiting rejects >N registrations per IP per hour; `registration.enabled=false` disables the endpoint; reserved subdomains are blocked.

---

## Cross-cutting benchmarks

### D5 benchmark plan (fold vs separate)

Unchanged from the synthetic-only design — the greenfield strategy means the benchmark runs **only against generated data**, not a production-shape backfill.

#### Harness

A standalone script (`bench/route_match_benchmark.ts`) that:

1. **Seeds** two parallel test schemas in a throwaway Postgres+TimescaleDB:
   - Schema **F** (folded): `raw_receptions` with `path_hashes text[]` + GIN, no hops table.
   - Schema **S** (separate): `raw_receptions` without the array + a `packet_path_hops` hypertable (FK to `raw_receptions`), mirroring today's shape.
2. **Generates** a synthetic dataset with parameterised shape (see Dataset shape below).
3. **Runs** the route matcher (the subsequence algorithm ported from the old `routes.py`, adapted to each schema's candidate fetch) across a fixed route set.
4. **Measures** per-route and total-sweep metrics (see Metrics).
5. **Reports** a comparison table + the decision (see Decision rule).

#### Dataset shape (the variables that matter)

| Variable | Low | Medium | High | Why it matters |
|---|---|---|---|---|
| `raw_receptions` in window | 10k | 100k | 1M | scan scale |
| Routes | 10 | 50 | 200 | sweep fan-out |
| Distinct node hashes in routes | 5 | 20 | 80 | GIN selectivity — the key driver |
| Avg path length (hops) | 3 | 6 | 10 | array size + hop-table row count |
| Observers per packet | 1 | 4 | 8 | reception multiplicity |
| Hash commonality (frac of packets containing a given route hash) | 1% | 10% | 40% | **the breaker** — high commonality = large GIN candidate sets |

Generate paths so that a known fraction contain each route's hash sequence (to validate the matcher finds true positives), with the rest random (false-positive candidates the matcher must reject).

#### Metrics

Per route, per dataset shape:
- `candidate_query_ms` — the fetch (GIN containment vs hops-table scan+join).
- `candidate_count` — rows the fetch returned (drives downstream work).
- `match_ms` — the TS subsequence pass over candidates.
- `total_route_ms` = `candidate_query_ms + match_ms`.

Per sweep:
- `sweep_ms` = Σ `total_route_ms` across all routes.
- `p95_route_ms`, `p99_route_ms`.

#### Decision rule

Keep **folded (F)** if, at the **High** dataset shape (1M receptions, 200 routes, 40% commonality):
- `sweep_ms(F) ≤ 1.5 × sweep_ms(S)`, **and**
- `p95_route_ms(F) ≤ 500ms`.

Rationale: the folded schema eliminates the hops table's write amplification (a 6-hop packet × 4 observers = 24 rows today → 1 row folded). That write-cost win is worth up to a 1.5× read-cost tradeoff because reads happen on a 300s evaluator cadence while writes happen on every packet. The 500ms p95 guard prevents any single route becoming a latency outlier.

If folded fails the gate: fall back to the separate hypertable (still better than today because it's TimescaleDB-partitioned and no longer denormalized). The `raw_receptions.path_hashes` column stays either way (it's useful for the packet-group detail view); the hops table is additive.

#### Timing

Budget half a day. Record results in `docs/plans/<date>-d5-fold-benchmark/` with the dataset parameters and the decision. **Run this in Phase 0, before the new stack's schema is frozen**, so the DDL migration reflects the outcome (it needs only a throwaway TimescaleDB — no dependency on any later phase).
