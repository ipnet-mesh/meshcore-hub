# Code Warts & Antipatterns — Lessons from the Current Codebase

> **Purpose:** A reference catalog of implementation smells, dead code, fragile patterns, and
> gotchas discovered in the current MeshCore Hub codebase. This is the raw material for the new
> repo's `AGENTS.md` / `CONTRIBUTING.md` "we do X because the old code did NOT-X and it cost us Y"
> rules. Each entry links to the rewrite decision or component doc that addresses it.
>
> **This is not blame.** Every wart has an organic-growth explanation. The point is to prevent
> recurrence in the new codebase and preserve the hard-won lessons.

## Catalog structure

| Category | Prefix | What it covers |
|---|---|---|
| [Data modeling](#1-data-modeling) | DM | Types, schema shapes, indexes, naming |
| [Architecture & structure](#2-architecture--structure) | AR | Coupling, dead code, duplication, abstractions |
| [Concurrency](#3-concurrency) | CO | Threading, caching, execution models |
| [API layer](#4-api-layer) | AP | Routes, schemas, queries, auth |
| [Frontend](#5-frontend) | FE | Types, bundling, patterns, state |
| [Security](#6-security) | SE | Auth, tenancy, trust boundaries |
| [Testing & quality](#7-testing--quality) | TQ | Gaps, fragility, conventions |
| [Operational gotchas](#8-operational-gotchas) | OP | Tooling, build, deployment |

---

## 1. Data modeling

### DM1 — String UUIDs instead of native `uuid`
**Where:** `common/models/base.py:11-13,48-52` — `UUIDMixin` stores `id` as `str(uuid4())` in `String(36)`.
**Why it happened:** SQLite has no native UUID type; the codebase started SQLite-only.
**Cost:** On Postgres, every PK and every FK join (~25 FK columns across 17 tables) is a 36-char text comparison instead of a 16-byte native uuid compare. Pervasive storage + join penalty.
**Rewrite:** [D10](decisions/D10-drop-sqlite.md) drops SQLite; [data-model.md](components/data-model.md) uses native `uuid` with `gen_random_uuid()`.

### DM2 — String-typed "enums"
**Where:** `ChannelVisibility`, `RouteVisibility`, `RouteState`, `RouteQuality` all stored as `String(20)`. No DB-level check constraint. (`channel.py:42-44`, `route.py:61-65`, `route_result.py:71-78`)
**Cost:** Any arbitrary string validates at the DB level. Typos pass silently; no referential integrity on enum values.
**Rewrite:** [data-model.md](components/data-model.md) §3.1 — native Postgres `CREATE TYPE ... AS ENUM`.

### DM3 — `JSON` not `JSONB`
**Where:** `Telemetry.parsed_data`, `TracePath.path_hashes`/`snr_values`, `EventLog.payload`, `RawPacket.decoded` — all `JSON` not `JSONB`.
**Cost:** No GIN indexing possible without a type migration. Query operators limited.
**Rewrite:** [data-model.md](components/data-model.md) — `JSONB` everywhere, with GIN indexes where queried.

### DM4 — Parallel-array JSON antipattern
**Where:** `TracePath.path_hashes` (`["4a","b3fa"]`) and `snr_values` (`[25.3,18.7]`) — positionally coupled, no DB enforcement of equal length.
**Cost:** Any reader must zip them mentally; adding a third per-hop attribute means a third parallel array + edits to every reader.
**Rewrite:** [data-model.md](components/data-model.md) — single `hops jsonb` array of `{"hash","snr"}` objects (Q-B agreed).

### DM5 — Redundant / inconsistent indexes
**Where:**
- `UserProfileNode`: `Index("ix_user_profile_nodes_node_id")` (`user_profile_node.py:59`) duplicates the auto-created index backing `UniqueConstraint("node_id")` (`:58`).
- `RouteResultHistory`: `ix_route_result_history_route_id_date` (`5e3b712ccf10:321-325`) duplicates the unique constraint `uq_route_result_history_route_date`.
- `Node.ix_nodes_public_key`: recreated as a **non-unique** index (`5e3b712ccf10:524-525`) despite the column being `unique=True` at the ORM level.
**Cost:** Wasted write cost (every insert maintains a duplicate index); confusion about uniqueness enforcement.
**Rewrite:** [data-model.md](components/data-model.md) — fresh schema, each index deliberate, unique constraints enforced.

### DM6 — Dual-hash identity confusion
**Where:** `event_hash` (MD5 content dedup) and `packet_hash` (the on-air wire hash) both appear on `Message`, `Advertisement`, `Telemetry`, `TracePath`, `RawPacket`, and denormalized onto `PacketPathHop`. The evaluator "prefers `event_hash` over `packet_hash`" with fallback logic. (`raw_packet.py:25-33`, `packet_path_hop.py:30-35`)
**Cost:** Two nullable columns with fallback logic spread across 6 tables = real complexity and storage duplication.
**Rewrite:** [data-model.md](components/data-model.md) §1.2 — `event_hash` (SHA-256) on dedup'd event tables; `wire_hash` only on `raw_receptions`.

### DM7 — MD5 for dedup hashes
**Where:** `common/hash_utils.py:43,89,103,144` — all four `compute_*_hash` functions use MD5.
**Cost:** Not a security issue (not auth tokens), but MD5 collisions are cheaply producible. For a 32-hex-char dedup key across very high volume, accidental collisions aren't impossible.
**Rewrite:** [D10](decisions/D10-drop-sqlite.md) era — SHA-256 truncated to 16 bytes.

### DM8 — Roles stored as CSV text
**Where:** `UserProfile.roles` is `Text`, parsed by a `role_list` property that splits on comma. (`user_profile.py:48-52,69-74`)
**Cost:** Cannot index, cannot enforce at DB level, allows dirty strings. `UserProfile.roles.contains("admin")` is a substring match, not a set membership.
**Rewrite:** [data-model.md](components/data-model.md) — `user_profile_roles` join table.

### DM9 — Mixed table-naming conventions
**Where:** `events_log` (singular-ish, model is `EventLog`), `route_result_history` (singular), `route_recent_matches` (plural), `node_tags` (plural). No single rule.
**Cost:** Minor, but cognitive friction when writing queries/migrations by hand.
**Rewrite:** [data-model.md](components/data-model.md) — plural tables consistently; `events_log` → `event_logs`.

### DM10 — No soft-delete anywhere
**Where:** Node cleanup physically deletes rows after `node_cleanup_days` (default 30). CASCADE/SET NULL only. Historical joins to deleted nodes become silently NULL.
**Cost:** Data loss is irreversible; historical accuracy degrades.
**Rewrite:** Not addressed (deliberate — RF data repopulates; preserved-config is the only permanent data). But worth noting as a conscious decision, not an oversight.

---

## 2. Architecture & structure

### AR1 — God-class inheritance
**Where:** `Subscriber(LetsMeshNormalizer)` (`subscriber.py:40`) inherits ~1,200 lines of pure normalization logic just to call `self._normalize_*`. The normalizer has no instance state — it's a mixin dressed as a base class.
**Cost:** Impossible to test the normalizer without a `Subscriber` harness; tight coupling between MQTT plumbing and decode logic.
**Rewrite:** [ingest.md](components/ingest.md) §2 — composition (`self.normalizer = PacketFields`), not inheritance.

### AR2 — Dead code surface
**Where:**
- `MQTTClient.publish_*` / `parse_event_topic` / `parse_command_topic` / `all_events_topic` / `all_commands_topic` (`common/mqtt.py:46-84,356-386`) — describe a native MeshCore event/command topic schema the collector never subscribes to or publishes. Dead at ingest time.
- `webhook.py:398-451` — `set_dispatch_callback`, `dispatch_event`, `get_queued_events` — an entire second dispatch mechanism with its own module-global queue, unused outside tests.
- `api/dependencies.py:48-86` — `get_mqtt_client` builds a fresh MQTT client per request; no route handler injects it.
**Cost:** Confusion for new contributors ("is this used?"); maintenance burden; false surface area in the type system.
**Rewrite:** Greenfield — only what's used gets built.

### AR3 — Duplicated maps and constants
**Where:**
- `_ROUTE_TYPE_MAP` in both `letsmesh_normalizer.py:557-562` and `handlers/raw_packet.py:23-28` with a "mirrors" comment.
- The payload-type → event-type table similarly duplicated.
- Frontend: `EVENT_TYPES` list of 21 strings hardcoded in `Packets.tsx:28-50` must track the backend enum manually.
**Cost:** Drift between copies; the "mirrors" comment is a promise, not enforcement.
**Rewrite:** [ingest.md](components/ingest.md) §2 — single declarative `CLASSIFIERS` table; [D09](decisions/D09-orval-client-generation.md) — generated client eliminates frontend enum duplication.

### AR4 — `schemas/messages.py` catch-all
**Where:** `common/schemas/messages.py` (378 lines) holds message, advertisement, trace, telemetry, AND every dashboard schema. `schemas/routes.py` forward-refs `BreakdownBucket` from it. (`routes.py:334-336`)
**Cost:** Coupling — any dashboard schema change touches the "messages" file; import cycles.
**Rewrite:** Greenfield — schemas split along domain lines.

### AR5 — `meshcoredecoder` library quirks papered over
**Where:** `_enrich_payload_decoded` (`letsmesh_decoder.py:291-314`) and `_flatten_control_parsed` (`:316-335`) exist solely because the lib's `to_dict()` omits subclass attrs and nests control-subtype fields differently than expected.
**Cost:** Fragile — a library update could silently break the enrichers; the workaround is undocumented in the lib.
**Rewrite:** [ingest.md](components/ingest.md) §2 — contribute typed `DecodedPacket` models upstream if possible; at minimum, type the decoder output so deviations are caught by the type system.

### AR6 — Dialect branches everywhere
**Where:** `if conn.dialect.name == "postgresql"` appears in `event_observer.py:143-158` (INSERT ON CONFLICT), `5e3b712ccf10:437-440` (STRING_AGG vs GROUP_CONCAT), `a59611449e2a:79-88` (postgresql_include/concurrently), `env.py:73,111` (render_as_batch). And `batch_alter_table` wrapping every SQLite ALTER.
**Cost:** Every migration must think about two backends; testing matrix doubles.
**Rewrite:** [D10](decisions/D10-drop-sqlite.md) — Postgres-only, all dialect branches deleted.

### AR7 — No naming-convention registry on Base
**Where:** `Base = DeclarativeBase()` with no `metadata.naming_convention`. (`base.py:21-24`) Alembic must hand-name every constraint/index.
**Cost:** Inconsistent constraint names across migrations; harder to write generic migration utilities.
**Rewrite:** [data-model.md](components/data-model.md) — set a naming convention on the declarative base.

---

## 3. Concurrency

### CO1 — Single-threaded MQTT ingestion
**Where:** `_on_message` runs on paho's network thread (`common/mqtt.py:230`). One DB session per message, fully synchronous, no batching, no internal queue. A slow DB stalls all topics.
**Cost:** Under burst load the broker queues messages and eventually disconnects the collector on keepalive timeout. No backpressure.
**Rewrite:** [ingest.md](components/ingest.md) §1 — MqttIngester → NATS → IngestWorker pool. [D04](decisions/D04-nats-jetstream-ingest.md).

### CO2 — Three execution models in one process
**Where:** Sync-on-MQTT-thread (handlers), async-in-dedicated-thread (webhooks, cleanup), sync-in-dedicated-thread (channel-refresh, spam-rescore, route-evaluator, route-history). (`subscriber.py`)
**Cost:** Cognitive overhead; three different error-handling patterns; three different session-lifecycle patterns.
**Rewrite:** [derived-state.md](components/derived-state.md) — one async scheduler; [ingest.md](components/ingest.md) — one async worker pool.

### CO3 — Five near-identical daemon-thread loops
**Where:** `_start_channel_refresh_scheduler`, `_start_spam_rescore_scheduler`, `_start_route_evaluator_scheduler`, `_start_route_history_backfill_scheduler`, and the inner loop of `_start_cleanup_scheduler` are structurally identical: spawn thread → `while running: for _ in range(interval): sleep(1); try: <work>`. (`subscriber.py:563-748`)
**Cost:** ~250 LOC of boilerplate; five `_stop_*` methods with identical join-with-timeout logic.
**Rewrite:** [derived-state.md](components/derived-state.md) — one `PeriodicJob` abstraction + single loop.

### CO4 — Decode cache not thread-safe
**Where:** `_decode_cache` dict (`letsmesh_decoder.py:230-238`) is read/written without holding `_state_lock` (which `reload_keys` *does* take). FIFO eviction via `pop(next(iter(...)))` during concurrent insert is fragile under GIL edge cases.
**Cost:** Latent data race between the paho thread and the channel-refresh thread.
**Rewrite:** [ingest.md](components/ingest.md) — the ingester is single-purpose; cache is either process-local to one thread or uses an immutable-snapshot swap (ChannelKeyCache pattern).

### CO5 — Broad `except Exception` swallows events silently
**Where:** `_dispatch_event` catches broad exceptions (`subscriber.py:353-354`); after `session.rollback()` the handler re-opens with `add_event_observer` and if *that* flush fails, the exception propagates out and is swallowed. The event is silently lost from logs.
**Cost:** Silent data loss under race conditions; hard to debug.
**Rewrite:** [ingest.md](components/ingest.md) §9 — ack-after-commit ordering; failed envelopes stay in the NATS stream for retry.

### CO6 — CLI truncates with unbounded `DELETE FROM`
**Where:** `cli.py:1246-1274` — `truncate` issues `DELETE FROM Table` with no `WHERE` inside a single transaction. For `--all` on a large SQLite DB this is a multi-second exclusive lock.
**Cost:** Operational footgun.
**Rewrite:** [derived-state.md](components/derived-state.md) — chunked operations; [D18](decisions/D18-cli-for-ops-not-config.md).

---

## 4. API layer

### AP1 — Dual cache-key format (the "hard rule")
**Where:** Keys coexist as `{endpoint_name}:{qs}` AND `{request.url.path}:role={role}:{qs}`, plus a third hand-rolled variant for messages/packets/packet_groups (`messages:role=...:`, `packets:role=...:`). `invalidate_dashboard` must drop **two** prefixes. AGENTS.md mandates the invalidation rules as a "hard rule" because the system is too fragile to change safely.
**Cost:** Every new cached endpoint requires updating the right helper(s) + a test. The "which prefix?" knowledge is tribal.
**Rewrite:** [api.md](components/api.md) — single `{namespace}:{scope}:{query_hash}` key format + declarative `ENTITY_INVALIDATION` graph.

### AP2 — N+1 hydration passes
**Where:** `list_messages` (`messages.py:162-187`) runs ~7 queries per page: paged query, count subquery, `resolve_sender_names` (2 queries), `selectinload(Node.tags)`, `fetch_observers_for_events` (2 queries). Same shape in `list_advertisements`, `list_raw_packets`, `list_packet_groups`.
**Cost:** Page load latency scales with hydration depth, not result count.
**Rewrite:** [api.md](components/api.md) — eager-load at ORM level; precompute observer data.

### AP3 — `get_visible_channel_indices` full scan every request
**Where:** `channel_visibility.py:44-62` — `SELECT * FROM channels` on every role-aware request, no caching of its own. A request hitting 5 dashboard endpoints = 5 full Channel scans.
**Cost:** Unnecessary DB load proportional to request count × channel count.
**Rewrite:** [api.md](components/api.md) — pre-resolved in the `Principal` at middleware; cached per role-tier.

### AP4 — Redaction reimplemented 3×
**Where:** The "null out raw_hex/decoded/source_pubkey_prefix on hidden channels" logic is in `raw_packets.py:_build_read` (`242-272`), `packet_groups.py` list (`185-209`), and `packet_groups.py` detail (`276-291`).
**Cost:** Three copies; easy to drift when one endpoint adds a new redacted field.
**Rewrite:** [api.md](components/api.md) — single `apply_visibility(query, principal)` construct.

### AP5 — Sync ORM in an async framework
**Where:** All route handlers use synchronous `Session` and `session.execute(...)`. FastAPI runs them in a threadpool. An async session factory exists (`database.py:291`) but is unused by the API.
**Cost:** Each request occupies a worker thread for the duration of DB I/O; the `@cached` decorator must branch on `iscoroutinefunction`.
**Rewrite:** [api.md](components/api.md) — async end-to-end with Drizzle ORM over node-postgres.

### AP6 — Count-via-subquery on every list
**Where:** Every list endpoint: `select(func.count()).select_from(query.subquery())`. Worst on `packet_groups` (inner query has `GROUP BY packet_hash`).
**Cost:** The count runs *in addition to* the paged query, doubling query cost.
**Rewrite:** [api.md](components/api.md) — keyset pagination where possible; precomputed counts for hot endpoints.

### AP7 — `get_profile` returns different schema by caller
**Where:** `user_profiles.py:160-210` — returns `UserProfileWithNodes` (includes `user_id`) if the caller is the owner, `UserProfilePublicWithNodes` otherwise. The proxy's `ENDPOINT_ACCESS` mapping doesn't model this (it only knows method + path).
**Cost:** Authorization behavior depends on data identity, not just route — hard to reason about.
**Rewrite:** [auth.md](components/auth.md) — the `Principal` carries the resolved identity; schema selection is explicit from `principal.user_id`.

### AP8 — Role-name resolution duplicated
**Where:** `channel_visibility.resolve_user_role` (API side, `channel_visibility.py:16-31`) and `_build_endpoint_access` (web side, `web/app.py:95-177`) both map configured role strings → canonical role. Two sources of truth.
**Cost:** Drift between the two mappings produces inconsistent authz.
**Rewrite:** [auth.md](components/auth.md) — one `Principal` resolution at the API middleware; the web tier doesn't do authz at all (just issues JWTs).

---

## 5. Frontend

### FE1 — No generated type layer (types hand-copied everywhere)
**Where:** `NodeTag` defined in `Nodes.tsx:32`, `NodeDetail.tsx:28`, `Messages.tsx:68` (different fields each time). `Channel` in 5 files. `Profile`/`MemberProfile`/`OperatorProfile`/`UserProfileData` across 5 files. `ObserverInfo` redefined in Messages + Advertisements. `ListResponse<T>` ad-hoc in every list page.
**Cost:** When the backend changes a field, every copy must be hand-updated. This is the single biggest maintainability risk.
**Rewrite:** [D09](decisions/D09-orval-client-generation.md) — generated client from OpenAPI; [frontend.md](components/frontend.md) — codegen'd client + typed queries.

### FE2 — No route-level code-splitting
**Where:** `vite.config.ts:23-39` configures only two manual chunks (`vendor` and `i18n`). Every page (Maps, Dashboard with charts, Markdown renderer) loads upfront. Main chunk: 776 KB.
**Cost:** Slow initial load, especially on mobile.
**Rewrite:** [frontend.md](components/frontend.md) — lazy routes + vendor-split heavy libs; target < 180 KB initial.

### FE3 — Four divergent data-fetching patterns
**Where:** (1) TanStack Query (most pages), (2) `useQueries` in Dashboard, (3) manual `useEffect` + `AbortController` in NodeDetail/CustomPage/PacketGroupDetail, (4) multi-fetch inside a single `queryFn` in Nodes/Messages/Advertisements/Packets.
**Cost:** Inconsistent caching/invalidation behavior; some data paths skip react-query's cache entirely.
**Rewrite:** [frontend.md](components/frontend.md) — one pattern: generated query hooks.

### FE4 — `__APP_CONFIG__` re-serialized per navigation
**Where:** `web/app.py:299-396` — `_build_config_json()` runs per request, inlined into HTML with user-specific fields (`user`, `roles`). The shell can never be a static file.
**Cost:** No CDN caching of the shell; unnecessary CPU per request.
**Rewrite:** [frontend.md](components/frontend.md) — static shell + `/api/v1/config` (public, cacheable) + `/api/v1/me` (user-specific).

### FE5 — Legacy vendored dead weight
**Where:** `static/vendor/lit-html/` and `static/vendor/qrcodejs/qrcode.min.js` are leftovers from a pre-React lit-html SPA. Charts come from `chart.js/auto` (npm), QR from `react-qr-code`, maps from npm `leaflet`.
**Cost:** Confusion; unnecessary repo size.
**Rewrite:** Greenfield — only fonts + tailwind build are vendored.

### FE6 — Hardcoded magic values scattered
**Where:**
- `limit: 500` for profiles/nodes/observers fetches (`Nodes.tsx:138`, `Messages.tsx:137`, `Advertisements.tsx:132`, `Members.tsx:161`, `web/app.py:855,868`).
- `EVENT_TYPES` list of 21 strings hardcoded in `Packets.tsx:28-50`.
- Channel-label parsing `parseInt(channel.channel_hash, 16)` repeated in `Dashboard.tsx:379`, `Messages.tsx:147`, `Packets` helpers, `Channels.tsx:67`.
- Quality color maps duplicated in `Dashboard.tsx:115-121` and `charts.ts:116-122`.
**Cost:** Magic numbers silently cap functionality (500-node observer filter breaks on larger networks); enum drift between frontend and backend.
**Rewrite:** [D09](decisions/D09-orval-client-generation.md) (generated enums); [frontend.md](components/frontend.md) (server-side aggregation for observer-area filtering).

### FE7 — Two title-management systems
**Where:** `usePageTitle(entityKey)` hook (13 pages) and `useNavActiveState()` in `App.tsx:35-75` both write `document.title`. Whichever runs last wins.
**Cost:** Title flicker; non-deterministic ordering.
**Rewrite:** Greenfield — one title-management path.

### FE8 — Error handling chaos
**Where:** `Channels.tsx:335,345` and `Routes.tsx:1441,1476,1488` use native `alert()`. `NodeDetail.tsx` and `Profile.tsx` use flash-message-via-query-string. `ErrorBoundary.tsx` renders a generic message. `apiGet` throws `Error("API error: 404 ...")`; pages detect 404 by string-matching the message (`NodeDetail.tsx:137`, `CustomPage.tsx:44`).
**Cost:** Inconsistent UX; brittle error detection (string-matching).
**Rewrite:** [frontend.md](components/frontend.md) — one toast-based error UX; typed error classes.

### FE9 — Map page divergence
**Where:** `MapPage` hits `/map/data` (server-aggregated in Python, `web/app.py:837-980`), NOT the `/api/v1/*` pattern every other page uses. Different cache key namespace, different filter model (local React state, not URL-synced).
**Cost:** Refresh loses filters; doesn't benefit from API caching/invalidation.
**Rewrite:** Greenfield — map uses the standard API pattern.

### FE10 — `window.t` global + `useTranslation()` split-brain
**Where:** `window.t` global (used in `App.tsx`, `ErrorBoundary.tsx`, `format.ts`) coexists with `useTranslation()` everywhere else. `window.t` is only assigned after `initI18n()` resolves (`i18n/index.ts:50`); code that runs before boot gets the raw key.
**Cost:** Pre-boot error messages show translation keys, not text.
**Rewrite:** Greenfield — one i18n path.

---

## 6. Security

### SE1 — Two overlapping auth planes with implicit trust
**Where:** Direct Bearer (`RequireRead`/`RequireAdmin`) for CLI/m2m; OIDC proxy headers (`X-User-Id`/`X-User-Name`/`X-User-Roles`) for browser flows. The API trusts the headers because "only the proxy holds the API key" — implicit, not enforced.
**Cost:** If a connection leaks or the proxy is misconfigured, cross-instance/cross-role data exposure is possible. The trust boundary is tribal knowledge.
**Rewrite:** [D06](decisions/D06-jwt-auth-boundary.md), [auth.md](components/auth.md) — JWT verified at API middleware; no header injection.

### SE2 — Some handlers read `X-User-*` headers directly
**Where:** `get_my_profile`, `get_profile`, `list_node_tags` read `X-User-Id`/headers directly off `request.headers` without a dependency, bypassing the central `auth.py` helpers.
**Cost:** Authz bypass risk if a new route copies the pattern without understanding the trust model.
**Rewrite:** [auth.md](components/auth.md) — one `AuthMiddleware` resolves the `Principal`; handlers never read headers.

### SE3 — Schema-only tenancy (no RLS)
**Where:** Multi-tenancy is connection-level only (`search_path`). No `tenant_id` column anywhere. Isolation depends entirely on `search_path` being set correctly on every pooled connection. (`database.py:79-84`)
**Cost:** A leaking connection or misconfigured session factory = cross-instance data exposure. No row-level guard.
**Rewrite:** [D03](decisions/D03-row-level-tenancy-rls.md), [data-model.md](components/data-model.md) §3.2 — `instance_id` + RLS policies.

---

## 7. Testing & quality

### TQ1 — E2E auth is forged, not logged in
**Where:** No mock IdP exists; the web tier fully trusts the signed `meshcore-session` cookie. `e2e/mint_session.py` mints admin/member cookies using the stack's secret. (`AGENTS.md`)
**Cost:** The OIDC flow itself is untested in E2E; the test surface diverges from production auth.
**Rewrite:** [D12](decisions/D12-multi-source-auth.md) — local auth is testable directly (real login flow); OIDC stays integration-tested.

### TQ2 — 404 detection by string-matching error messages
**Where:** `apiGet` throws `Error("API error: 404 ...")`; pages detect 404 by `e.message.includes("404")`. (`NodeDetail.tsx:137`, `CustomPage.tsx:44`)
**Cost:** A message-format change breaks error handling.
**Rewrite:** [frontend.md](components/frontend.md) — typed error classes from the generated client.

### TQ3 — Cache-invalidation correctness tested via an integration rule
**Where:** `tests/test_api/test_cache.py::TestMutationInvalidationIntegration` — AGENTS.md mandates a test here for every new cached endpoint, because the invalidation rules are hand-coded and fragile.
**Cost:** The test burden is a symptom of the AP1 problem; the rule exists because the system can't be trusted without it.
**Rewrite:** [api.md](components/api.md) — declarative invalidation graph; the test asserts the graph, not every endpoint.

---

## 8. Operational gotchas

### OP1 — Parenthesized exception tuples (Python 2 syntax)
**Where:** AGENTS.md calls this out as "the most common error that passes visual review but breaks the app." `except ValueError, TypeError:` is Python 2 syntax; must be `except (ValueError, TypeError):`.
**Cost:** Fails at import time in Python 3. Easy to write by mistake if you're switching between languages.
**Rewrite:** New codebase — keep the AGENTS.md linting rule.

### OP2 — Never hand-pick Alembic revision IDs
**Where:** AGENTS.md: "use `secrets.token_hex(6)` or let `alembic revision` auto-generate. Never hand-pick sequential or guessable IDs — they collide with existing migrations and cause cycle errors."
**Cost:** Migration cycles at upgrade time.
**Rewrite:** New codebase — keep the rule.

### OP3 — Cache invalidation is a "hard rule" because the system is fragile
**Where:** AGENTS.md mandates calling `invalidate_*` helpers after every mutation, with a detailed mapping table. The rule exists because the dual cache-key format (AP1) makes hand-rolling prefixes error-prone.
**Cost:** The rule is a band-aid for an architectural problem; contributors must memorize the invalidation map.
**Rewrite:** [api.md](components/api.md) — the declarative graph replaces the hard rule.

### OP4 — The assistant never builds Docker images
**Where:** AGENTS.md: "Never build the Docker images or run `make build` / `make up` — the user builds manually to test."
**Cost:** Slows the dev loop for AI-assisted development.
**Rewrite:** New repo should decide explicitly whether this rule carries forward (likely yes, if the same workflow applies).

### OP5 — Derived-var chaining is undocumented tribal knowledge
**Where:** `FEATURE_PACKETS` → `RAW_PACKET_CAPTURE_ENABLED` + web toggle; `FEATURE_SPAM_DETECTION` → collector + api + web. The derivation happens in `docker-compose.yml` env wiring, not in code.
**Cost:** Adding a feature flag requires editing compose + collector + api + web env sections.
**Rewrite:** [D11](decisions/D11-three-tier-config.md) — one settings row read by whoever needs it.

---

## How to use this catalog

When writing the new repo's `AGENTS.md` / `CONTRIBUTING.md`, derive "we do / we don't" rules from these entries. Examples:

- *"We use native `uuid` PKs because the old codebase's `String(36)` UUIDs cost a 2× join penalty on every FK (DM1)."*
- *"We generate the frontend client from OpenAPI because hand-copied types drifted across 5 files (FE1)."*
- *"We use one cache key format because the old codebase's dual/tri format required a tribal-knowledge invalidation map (AP1/OP3)."*
- *"We resolve auth at one middleware because the old codebase had handlers reading `X-User-*` headers directly (SE2)."*

Each wart in this catalog should map to either an ADR, a component-doc design choice, or an explicit "we accept this risk" note in the new repo's conventions.
