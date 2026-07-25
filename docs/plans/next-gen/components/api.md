# API

> **Related decisions:** D6 (auth boundary — JWT verified at API middleware resolves the `Principal` that handlers and the cache layer key on), D7 (realtime transport — SSE for live pages, fed from NATS; polling remains the fallback), D11 (config model — three-tier: Tier 1 bootstrap env vars, Tier 2 DB-backed UI-editable settings, Tier 3 entities), D19 (webhook delivery via NATS core subscriber), D20 (custom pages as DB-backed Tier-3 entities).
>
> **Note:** Code examples are illustrative pseudocode showing design patterns (shapes, flows, contracts).
> The implementation uses the TypeScript stack (D22): Fastify, Drizzle ORM, Zod, ioredis, jose.

## Async end-to-end

- All handlers are `async` using **Drizzle ORM** over `node-postgres`, which provides native async I/O end-to-end.
- DB I/O off the event loop; connection pool sized to async concurrency.
- The `@cached` decorator's sync/async branch collapses to one async path.

## Error response format

One stable shape for every non-2xx response. The frontend's generated client (D9) types this; pages catch typed errors instead of string-matching `"404"` (FE8, TQ2).

```typescript
// Every error response — 4xx and 5xx alike
interface ApiError {
    status: number;          // HTTP status code (400, 401, 403, 404, 409, 422, 500)
    code: string;            // machine-readable: "not_found", "unauthorized", "conflict", "validation_error", "internal"
    detail: string;          // human-readable message (safe to display in a toast)
    errors?: FieldError[];   // present only on 422 validation failures
}

interface FieldError {
    field: string;           // dotted path: "body.username", "query.limit"
    message: string;         // "must be at least 3 characters"
}
```

**Fastify implementation:** a single `setErrorHandler` plugin maps all errors to this shape:

```typescript
fastify.setErrorHandler((error, request, reply) => {
    if (error.validation) {
        // Zod validation failure (via fastify-type-provider-zod)
        return reply.status(422).send({
            status: 422,
            code: "validation_error",
            detail: "Request validation failed",
            errors: error.validation.map(e => ({ field: e.path.join("."), message: e.message })),
        });
    }
    if (error.statusCode === 404) {
        return reply.status(404).send({ status: 404, code: "not_found", detail: error.message });
    }
    // Auth errors (thrown by AuthMiddleware with statusCode)
    if (error.statusCode && error.statusCode >= 400 && error.statusCode < 500) {
        return reply.status(error.statusCode).send({
            status: error.statusCode,
            code: statusCodeToErrorName(error.statusCode),
            detail: error.message,
        });
    }
    // Unexpected — log the full error, return a safe message
    request.log.error(error);
    return reply.status(500).send({ status: 500, code: "internal", detail: "Internal server error" });
});
```

**Handlers throw typed errors:**

```typescript
// Instead of returning raw status codes, handlers throw:
throw new ApiHttpError(404, "not_found", `Node '${publicKey}' not found`);
throw new ApiHttpError(409, "conflict", `Channel name '${name}' already exists`);
throw new ApiHttpError(403, "forbidden", "Admin role required");
```

**Frontend consumption:** the orval-generated client surfaces `ApiError` as a typed rejection. Pages use a shared `useApiErrorHandler` hook that routes errors to the `ToastProvider` (FE8) — no `alert()`, no `e.message.includes("404")`.

**Maintenance mode:** when `branding.maintenance_mode` is true, the middleware returns `503 { status: 503, code: "maintenance", detail: <announcement text> }` for all non-admin requests. The frontend shows a full-page maintenance banner with the announcement.

## One cache contract

Replace the dual/tri cache-key format with a single rule (detailed below):

- Every cached endpoint registers a **namespace** (e.g. `"nodes"`, `"routes:{id}"`).
- Each entity owns a **dependency graph**: mutating a node invalidates `nodes`, `messages`, `advertisements`, `dashboard` — declared once as data, not hand-coded per helper.
- Generate invalidation from the dependency graph; the `invalidate_dashboard` "drop two prefixes" hack disappears.

## Unified cache contract (concrete)

Replaces the dual/tri cache-key format and the hand-coded invalidation helpers.

**One key format:**
```
{namespace}:{scope}:{query_hash}
  namespace = endpoint family ("nodes", "messages", "routes", ...)
  scope     = "shared" | role_tier ("admin", "operator", "member", "community", "anonymous")
  query_hash = sha256(sorted_query_params)[:16]
```

**Declarative invalidation graph** — the single source of truth, replacing AGENTS.md's "hard rule" hand-mapping:

```typescript
NAMESPACES = {
    # namespace:     role_scoped?  invalidated_when_these_entities_change
    "nodes":         (False, {"node", "node_tag", "adoption"}),
    "messages":      (True,  {"message", "node", "node_tag"}),
    "advertisements":(False, {"advertisement", "node", "node_tag", "adoption"}),
    "routes":        (True,  {"route"}),
    "channels":      (True,  {"channel"}),
    "profiles":      (False, {"profile", "adoption"}),
    "packets":       (True,  {"raw_reception"}),
    "packet_groups": (True,  {"raw_reception"}),
    "dashboard":     (False, {"node","node_tag","message","advertisement","adoption","profile","route"}),
    "settings":      (False, {"setting"}),
    "me":            (False, {"profile", "adoption"}),
    "pages":         (False, {"custom_page"}),
    "config":        (False, {"setting", "custom_page"}),
}

# Inverted at startup: entity → set(namespaces to invalidate)
ENTITY_INVALIDATION = invert(NAMESPACES)
```

**The `@cached` decorator** (async-only now that the API is async end-to-end):
```typescript
def cached(namespace: str, *, ttl_setting: str = "cache_ttl"):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: Request, *args, **kwargs):
            ns = NAMESPACES[namespace]
            role = request.state.principal.role_tier if ns.role_scoped else "shared"
            qhash = sha256(sorted_query_string(request).encode())[:16].hex()
            key = f"{namespace}:{role}:{qhash}"

            # Conditional GET → 304
            inm = request.headers.get("if-none-match")
            cached_etag = await cache.get(f"{key}:etag")
            if cached_etag and etag_matches(inm, cached_etag):
                return Response(status_code=304, headers={"ETag": cached_etag})

            # Cache lookup
            if (body := await cache.get(key)) is not None:
                request.state.cache_status = "HIT"
                return Response(content=body, media_type="application/json",
                                headers={"ETag": cached_etag or "", "X-Cache": "HIT"})

            # Miss → execute, serialize, store
            request.state.cache_status = "MISS"
            result = await handler(request, *args, **kwargs)
            payload, etag = serialize(result)
            ttl = getattr(request.app.state, ttl_setting)
            await cache.set(key, payload, ttl=ttl)
            await cache.set(f"{key}:etag", etag, ttl=ttl)
            return Response(content=payload, media_type="application/json",
                            headers={"ETag": etag, "X-Cache": "MISS"})
        return wrapper
    return decorator
```

**Invalidation after a mutation** — one call, the graph does the rest:
```typescript
async def invalidate_for(session_changes: Iterable[str], cache: CacheBackend, instance_id):
    namespaces = set()
    for entity in session_changes:
        namespaces |= ENTITY_INVALIDATION.get(entity, set())
    for ns in namespaces:
        await cache.delete(f"{ns}:*")   # SCAN + DEL by prefix
```

A mutation handler declares what it changed:
```typescript
@router.put("/nodes/{pk}/tags/{key}")
async def update_tag(...) -> NodeTagRead:
    ... mutate, commit ...
    await invalidate_for({"node_tag", "node"}, cache, instance_id)   # drops nodes + messages + adverts + dashboard
    return tag
```

This replaces today's per-endpoint `_invalidate_node_tag_caches`/`_invalidate_adoption_caches` helpers and the dual-prefix `invalidate_dashboard` hack with a single declarative map.

## Redaction in one place

A single `applyVisibility(query, principal)` Drizzle query builder construct that all list/detail endpoints use. Implemented once, tested once. The three reimplementations vanish.

## Kill the N+1 and the count-subquery

- **Eager-load** observer + tag data with `selectinload` at the ORM level (already done for nodes; extend to events).
- **Precompute `total`** for hot list endpoints as a denormalized counter or a separate `count` query that doesn't wrap the full filtered query (keyset pagination where possible; for `packet_groups` use a `count(distinct wire_hash)` materialized helper).
- **Cache `get_visible_channel_indices`** per request (it's role-scoped and stable) — compute once in the `Principal`.

## OpenAPI as the contract

- Enforce a clean OpenAPI schema (already generated). Add Zod response schemas everywhere (some detail endpoints are loose).
- **Generate the TypeScript client** with `orval` (D9 locked) as a build step. One source of truth. The frontend stops hand-copying shapes.
- CI gate: the generated client must be up to date with the schema.

## Realtime (SSE)

A thin **SSE** endpoint (`/api/v1/events/stream`) backed by NATS pub/sub. The ingest workers publish "new message/advert/packet" events after commit; the SSE endpoint fans them out to subscribed clients. Live pages subscribe to the relevant channels and update incrementally instead of polling. Auto-refresh becomes a *fallback*, not the primary refresh mechanism.

- SSE over HTTP is simpler than WebSocket (no upgrade, plays nice with proxies, one connection per tab).
- Backpressure: cap fan-out buffer; clients fall back to polling on disconnect.

### SSE auth (cookie-based, proxy-transparent)

The browser's `EventSource` API cannot set custom headers, so the SSE connection authenticates via the **session cookie** (sent automatically, same-origin). The auth flow:

```
Browser ──EventSource('/api/v1/events/stream')──→ Web tier
         (cookie sent automatically)              reads cookie → mints JWT
                                                   opens upstream to API with Authorization: Bearer <jwt>
         ←──streamed SSE chunks─────────────────── pipes response chunks without buffering
                                                   API's AuthMiddleware resolves Principal from JWT
                                                   per-event channel-visibility filter applied
```

The web tier already proxies all `/api/v1/*` calls — SSE is just a long-lived, streaming variant of the same proxy pattern. The implementation requirement: **the proxy must pipe chunks as they arrive, not buffer the response.** In Fastify, this means writing to `reply.raw` (the underlying `ServerResponse`) and calling `reply.raw.flushHeaders()` before the first chunk, or using `@fastify/http-proxy` which handles streaming correctly out of the box.

**Single-process alternative:** if the deployment runs web + API as one Fastify process (the simpler model for small/community deployments), no proxy is needed. The `AuthMiddleware` resolves the Principal directly from the cookie (same `OIDC_SESSION_SECRET`, same JWS verification the web tier uses). This adds a fourth resolution path to the middleware (after JWT-header, API-key, anonymous): cookie → verify JWS → resolve Principal. The auth boundary is unchanged — the middleware is still the single resolution point; the Principal is still the single authz artifact. The JWT becomes optional in this mode (the cookie is the credential, verified inline rather than transmitted over a network).

### SSE realtime endpoint (concrete)

`GET /api/v1/events/stream` — one HTTP connection per tab, fed from NATS. The handler writes SSE frames directly to the raw Node.js `ServerResponse` (`reply.raw`) — no buffering, no plugin dependency:

```typescript
// Fastify route — streaming SSE via reply.raw
fastify.get("/api/v1/events/stream", { preHandler: authMiddleware }, async (request, reply) => {
    const principal = request.principal;
    reply.raw.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    });
    reply.hijack();  // tell Fastify we're handling the response ourselves

    const sub = await nats.subscribe(`events.new.${principal.instanceId}.>`);
    let lastHeartbeat = Date.now();

    try {
        for await (const msg of sub) {
            const event = JSON.parse(decoder.decode(msg.data));
            // Per-event visibility: drop events on channels the caller can't see
            if (event.channel_idx !== undefined && !principal.channelIndices.has(event.channel_idx))
                continue;
            reply.raw.write(`event: ${event.type}\ndata: ${JSON.stringify(event.payload)}\n\n`);
            // Heartbeat every 15s so proxies don't kill idle connections
            if (Date.now() - lastHeartbeat > 15_000) {
                reply.raw.write("event: ping\ndata: \n\n");
                lastHeartbeat = Date.now();
            }
        }
    } finally {
        await sub.unsubscribe();
        reply.raw.end();
    }
});
```

**Backpressure:** the NATS subscription uses a bounded pending-messages limit (e.g. 256); if the client can't keep up, messages are dropped and the client's TanStack Query `refetchOnReconnect` + the 30s poll fallback recover. Live pages degrade to polling gracefully rather than blocking.

**What flows over it:** the IngestWorker publishes `{type, payload}` after every commit. Event types: `message.new`, `advertisement.new`, `raw_reception.new`, `route.updated`, `settings.updated`. The frontend subscribes to the relevant types per page.

## Settings: env vars vs DB-backed

Today ~200 env vars configure everything from branding to tuning to feature flags, and changing any of them (even an announcement banner) requires a container restart. The rewrite moves most of that into a **DB-backed, UI-editable settings store** — the infrastructure for it already exists in the target architecture (NATS for change notification, RLS for instance-scoping, the `/api/v1/config` endpoint the static shell needs anyway), so adopting it in the rewrite is nearly free. Retrofitting later is expensive.

### A three-tier model (the line-drawing rule)

Not all config is the same. Split by *when it can change*:

**Tier 1 — Bootstrap (env vars, immutable at runtime).** Needed to start the process; can't be read from the DB because it's *how you reach the DB*. ~15–20 vars. Never moves.

```
DATABASE_URL, NATS_URL, MQTT_HOST/PORT/..., REDIS_HOST/..., OIDC_CLIENT_ID/SECRET/DISCOVERY,
OIDC_SESSION_SECRET, API_HOST/PORT, LOG_LEVEL, INSTANCE_NAME
```

Rule of thumb: if changing it requires reconnecting to an external system or re-authenticating, it's Tier 1. Secrets stay here (or in a secret manager) — they shouldn't sit in a DB backup.

**Tier 2 — Runtime settings (DB-backed, UI-editable, cached + event-invalidated).** Everything an admin would reasonably want to tune without a restart. Stored in a `settings` table, exposed via `GET/PUT /api/v1/settings`, cached in-memory per service, invalidated across services via NATS (`settings.updated.<instance>`). This is the tier that *moves* from env to DB:

| Category | Examples | Why runtime |
|---|---|---|
| **Branding/content** | network name, city, country, contact links, welcome text, announcements, maintenance flag, default theme, locale | community changes, incident comms — restart-for-an-announcement is the current pain point |
| **Feature flags** | FEATURE_DASHBOARD/NODES/PACKETS/ROUTES/… | toggle a page off during an incident, A/B a new feature |
| **Tuning** | retention days, spam thresholds/weights, evaluator intervals, cache TTLs, auto-refresh seconds | adjust under load without downtime |
| **Webhooks** | URLs, secrets, event filters, retry config | operators add integrations at runtime |
| **Radio display** | frequency, bandwidth, spreading factor, profile name | cosmetic display values the community sets |

**Tier 3 — First-class entities (already DB-backed, unchanged).** Channels, routes, tags, profiles. Custom pages become a DB-backed entity via D20.

### The settings table

```sql
CREATE TABLE settings (
  key         text PRIMARY KEY,
  value       jsonb NOT NULL,           -- typed per category (validated server-side)
  category    text NOT NULL,            -- 'branding' | 'features' | 'tuning' | 'webhooks' | 'radio'
  description text,                     -- surfaced in the settings UI
  updated_by  text,                     -- user_id of last editor (audit)
  updated_at  timestamptz NOT NULL DEFAULT now(),
  instance_id uuid NOT NULL REFERENCES instances(id)
);
```

A typed Zod schema per category validates writes (`PUT /api/v1/settings` accepts a partial category payload). Defaults ship as a seed migration (one row per known key) so a fresh DB is fully configured out of the box — env vars override the seed at first boot only (one-time bootstrap), then the DB is authoritative.

### Settings seed inventory (the complete Tier-2 key list)

Every key below is seeded at instance creation (registration or CLI). The `value` column holds typed JSONB; the Zod schema per category validates writes. Keys are namespaced `{category}.{name}`.

**Branding** (`branding.*`) — surfaced in `PublicConfig`, drives the UI shell:

| Key | Type | Default | Notes |
|---|---|---|---|
| `branding.network_name` | string | `"MeshCore Network"` | From `NETWORK_NAME` env at first boot |
| `branding.city` | string | `""` | |
| `branding.country` | string | `""` | |
| `branding.contact_links` | `{label, url}[]` | `[]` | Footer / about links |
| `branding.welcome_text` | string | `""` | Landing page hero text (markdown) |
| `branding.announcement` | string | `""` | Banner shown on all pages when non-empty |
| `branding.system_announcement` | string | `""` | Urgent banner (distinct style) |
| `branding.maintenance_mode` | boolean | `false` | When true, non-admin requests get a 503 + the announcement |
| `branding.default_theme` | `"light" \| "dark"` | `"light"` | User preference overrides |
| `branding.locale` | string | `"en"` | UI language |
| `branding.datetime_locale` | string | `"en-US"` | Date/time formatting |

**Features** (`features.*`) — boolean page/capability toggles, surfaced in `PublicConfig`:

| Key | Default | Gates |
|---|---|---|
| `features.dashboard` | `true` | Dashboard page |
| `features.nodes` | `true` | Nodes list + detail |
| `features.advertisements` | `true` | Advertisements page |
| `features.messages` | `true` | Messages page |
| `features.map` | `true` | Map page |
| `features.members` | `true` | Members page (requires OIDC or local auth) |
| `features.pages` | `true` | Custom pages (D20) |
| `features.channels` | `true` | Channels page |
| `features.radio_config` | `true` | Radio display section |
| `features.packets` | `true` | Packets page + raw capture in the IngestWorker |
| `features.spam_detection` | `true` | Spam scoring in the IngestWorker + rescore job |
| `features.routes` | `true` | Routes page + route-evaluator job |

**Tuning** (`tuning.*`) — operational knobs, not surfaced in `PublicConfig`:

| Key | Type | Default | Notes |
|---|---|---|---|
| `tuning.data_retention_days` | int | `30` | OLTP chunked DELETE window (messages, adverts, traces) |
| `tuning.data_retention_enabled` | boolean | `true` | |
| `tuning.node_cleanup_days` | int | `30` | Inactive node purge |
| `tuning.node_cleanup_enabled` | boolean | `true` | |
| `tuning.cache_ttl_seconds` | int | `30` | Default `@cached` TTL |
| `tuning.cache_ttl_dashboard_seconds` | int | `300` | Dashboard-specific TTL (longer — CAGG-backed) |
| `tuning.auto_refresh_seconds` | int | `30` | Frontend poll fallback interval |
| `tuning.metrics_cache_ttl_seconds` | int | `60` | `_metrics_cache` refresh cadence |
| `tuning.spam_score_threshold` | float | `0.65` | Score ≥ this → flagged |
| `tuning.spam_window_seconds` | int | `300` | Sliding window for frequency counts |
| `tuning.spam_path_hops` | int | `3` | Leading hops forming the path prefix |
| `tuning.spam_min_path_hops` | int | `3` | Min `path_len` for path signal |
| `tuning.spam_path_threshold` | int | `6` | Count saturating the path signal |
| `tuning.spam_name_threshold` | int | `10` | Count saturating the name signal |
| `tuning.spam_weight_path` | float | `0.75` | Path signal weight |
| `tuning.spam_weight_name` | float | `0.25` | Name signal weight |
| `tuning.spam_rescore_interval_seconds` | int | `120` | Sweep cadence (0 disables) |
| `tuning.route_evaluator_interval_seconds` | int | `300` | `route-evaluator` job cadence |
| `tuning.route_history_interval_seconds` | int | `3600` | `route-history` job cadence |
| `tuning.route_recent_matches_limit` | int | `3` | Max recent matches per route |

**Webhooks** (`webhooks.*`) — array of webhook configs:

| Key | Type | Default | Notes |
|---|---|---|---|
| `webhooks.configs` | `WebhookConfig[]` | `[]` | Each: `{id, url, secret, event_types[], filter_expression?, retries, backoff_base_seconds, enabled}` |

`WebhookConfig` Zod schema: `url` (url string, required), `secret` (string, optional — HMAC signing), `event_types` (subset of `["advertisement.new", "message.new"]`, default both), `filter_expression` (string, optional — JSONPath-like DSL), `retries` (int, default 3), `backoff_base_seconds` (int, default 2), `enabled` (boolean, default true).

**Radio** (`radio.*`) — cosmetic display values, surfaced in `PublicConfig`:

| Key | Type | Default | Notes |
|---|---|---|---|
| `radio.frequency` | string | `"869.618"` | Display only |
| `radio.bandwidth` | string | `"62.5"` | Display only |
| `radio.spreading_factor` | string | `"8"` | Display only |
| `radio.profile_name` | string | `""` | Display only |

**Registration** (`registration.*`) — platform-level (Phase 7; stored on the platform instance):

| Key | Type | Default | Notes |
|---|---|---|---|
| `registration.enabled` | boolean | `true` | Kill switch for `POST /api/v1/register` |
| `registration.rate_limit_per_ip` | string | `"3/hour"` | Reverse-proxy `limit_req` hint |
| `registration.require_captcha` | boolean | `false` | hCaptcha/Turnstile on the form |
| `registration.subdomain_reserved` | string[] | `["www","api","admin","mail"]` | Subdomains that can't be registered |
| `registration.max_domains_per_tenant` | int | `5` | Custom domain cap |

**Total: 45 keys** across 6 categories. The seed migration inserts one row per key with the default value, `updated_by = 'seed'`, and the instance's `instance_id`. On first boot, Tier-1 env vars (`NETWORK_NAME`, etc.) override the matching seed values — this is the one-time bootstrap. After that, the DB is authoritative and the Admin UI is the edit surface.

### Cross-service propagation

A setting change flows through the existing NATS bus:

```
admin saves setting → API writes settings row + commits
                    → API publishes settings.updated.<instance>.{category}
                    → collector, ingester, worker, web all hold a subscription
                    → each reloads its in-memory snapshot for that category
```

Propagation semantics must be documented per category:
- **Branding/announcements/maintenance:** effective on next request (web tier re-reads its snapshot).
- **Feature flags:** effective on next request for the UI; for the collector (e.g. `features.packets` → raw capture), effective on the *next packet* — not retroactive.
- **Tuning (retention/spam/evaluator):** effective on the worker's next tick.
- **Webhooks:** effective on the next event dispatch.

This is more nuanced than "env var read at boot," but the alternative (restart to change a spam threshold) is worse, and the categories map cleanly to the services that care about each one.

### What this collapses

- The `__APP_CONFIG__` per-request rebuild becomes `GET /api/v1/config` reading the cached settings snapshot — aligns with the static-shell design for free.
- The "derived-var chaining" (`FEATURE_PACKETS` → `RAW_PACKET_CAPTURE_ENABLED` + web toggle; `FEATURE_SPAM_DETECTION` → collector + api + web) collapses into one settings row read by whoever needs it.
- Operators get an admin Settings page instead of editing `.env` + redeploying — which fits the community-operated nature of the project (the operator isn't always the deployer).
- Config changes are auditable (`updated_by`, `updated_at`) and revertible, unlike env-var changes which are git commits + deploys.

### The risks (and why they're manageable)

| Risk | Mitigation |
|---|---|
| Split-brain config source (some env, some DB) | The three-tier rule is explicit; Tier 1 is a small documented allowlist, everything else is DB |
| Secrets in the DB | Secrets stay in Tier 1 (env/secret manager); the `settings` table holds no secrets |
| Bad value bricks the app | Per-category Zod validation on write; a `settings reset --category=...` CLI escape hatch |
| Cross-service staleness | NATS `settings.updated` invalidation; documented per-category propagation lag |
| Reproducibility | Seed migration + `db export-config` captures settings alongside other preserved config |

## Settings API (D11)

```typescript
# Public — the static shell bootstraps from this (no auth)
@router.get("/config", response_model=PublicConfig)
async def get_public_config(settings: SettingsCache) -> PublicConfig:
    """Branding + feature flags + radio display. No secrets, no tuning params."""
    return settings.public_snapshot()

# Authenticated self
@router.get("/me", response_model=PrincipalRead)
async def get_me(principal: RequireMember) -> PrincipalRead:
    return PrincipalRead(user_id=principal.user_id, roles=list(principal.roles), ...)

# Admin-only — full settings, all categories
@router.get("/settings", response_model=SettingsByCategory, dependencies=[Depends(require_role("admin"))])
async def list_settings(settings: SettingsCache) -> SettingsByCategory:
    return settings.full_snapshot()

@router.put("/settings/{category}", dependencies=[Depends(require_role("admin"))])
async def update_settings(category: str, body: CategoryUpdate, settings: SettingsCache,
                          bus: NatBus, principal: RequireAdmin) -> SettingsByCategory:
    await settings.update_category(category, body, updated_by=principal.user_id)  # validate + write + commit
    await bus.publish(f"settings.updated.{principal.instance_id}.{category}")    # cross-service invalidate
    return settings.full_snapshot()
```

**`SettingsCache`** — in-memory snapshot per instance, refreshed on NATS notification:
```typescript
class SettingsCache:
    async def load(self, instance_id: UUID) -> None: ...          # boot: SELECT * FROM settings
    async def public_snapshot(self) -> PublicConfig: ...           # branding + features + radio
    async def full_snapshot(self) -> SettingsByCategory: ...       # all categories (admin)
    async updateCategory(cat, values, updatedBy) { ... }  // Zod-validate, UPSERT, commit
    async def on_settings_updated(self, msg): ...                  # NATS subscriber → reload category
```

Each category has a typed Zod schema validating writes — a bad value is rejected at the API, not discovered when a service reads it. The escape hatch if a value somehow bricks a service is the ops CLI `meshcore-hub settings reset --category=<cat>` (D18 — operational, not config-mirroring) or a "Reset to defaults" button per category in the Settings UI.

## Custom pages API (D20)

Custom pages move from file-based `CONTENT_HOME` to a DB-backed Tier-3 entity:

```typescript
@router.get("/pages", response_model=list[CustomPageRead])
async def list_pages(db: DbSession) -> list[CustomPageRead]:
    """Public — enabled pages only, sorted by menu_order. Drives nav + CustomPage route."""

@router.get("/pages/{slug}", response_model=CustomPageRead)
async def get_page(slug: str, db: DbSession) -> CustomPageRead:
    """Public — single page by slug (includes markdown content)."""

@router.post("/pages", response_model=CustomPageRead, dependencies=[Depends(require_role("admin"))])
async def create_page(body: CustomPageCreate, db: DbSession) -> CustomPageRead: ...

@router.put("/pages/{slug}", response_model=CustomPageRead, dependencies=[Depends(require_role("admin"))])
async def update_page(slug: str, body: CustomPageUpdate, db: DbSession) -> CustomPageRead: ...

@router.delete("/pages/{slug}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def delete_page(slug: str, db: DbSession) -> None: ...
```

Mutations invalidate the `pages` + `config` namespaces (nav metadata is served from `/api/v1/config`). The `PublicConfig` response includes `custom_pages: [{slug, title, url, menu_order}]` for the enabled pages — replacing the per-request `__APP_CONFIG__.custom_pages` injection.

## Carried-forward endpoints (current features, new contracts)

These endpoints exist today and are preserved in the rewrite. The designs below note what changes.

### API versioning

The API is served under `/api/v1/*`. There is no v2 plan — the rewrite *is* the v1. Breaking changes within v1 are avoided by the generated-client contract (D9): any schema change that breaks the client fails the CI drift check. If a breaking change is ever unavoidable, it ships as `/api/v2/*` alongside v1 (the Fastify router supports prefix mounting), with a deprecation window. This is a "cross that bridge" policy, not a design — no v2 is planned.

### Packet-group detail

```typescript
// All receptions of a single on-air packet (grouped by wire_hash)
fastify.get("/api/v1/packet-groups/:wireHash", async (request, reply) => {
    // Query raw_receptions WHERE wire_hash = :wireHash, ordered by received_at
    // Include path_hashes (D5 folded array), decoded_summary, observer info
    // Redact per channel visibility (applyVisibility)
    // Returns: { wire_hash, first_seen, last_seen, reception_count, receptions: [...] }
});
```

Replaces today's `packet_groups.py` detail endpoint. The `path_hashes` array (D5) backs the per-reception hop display — no separate `packet_path_hops` join.

### Map data

```typescript
// Server-aggregated node positions for the Leaflet map
fastify.get("/api/v1/map/data", async (request, reply) => {
    // Query nodes WHERE lat IS NOT NULL AND lon IS NOT NULL
    // Include: public_key, name, adv_type, is_observer, last_seen, tags (area)
    // Optionally filter by observer area (query param: ?area=<tag_value>)
    // Returns: { nodes: [{ public_key, name, lat, lon, is_observer, area, last_seen }] }
});
```

Replaces today's `/map/data` server-rendered endpoint (FE9). Now a standard `/api/v1/*` endpoint — benefits from caching, invalidation, and the generated client. The observer-area filter is server-side (removes the 500-node client fetch — FE6).

### Route preview (live evaluation)

```typescript
// Evaluate a route definition against recent data without saving
fastify.post("/api/v1/routes/preview", { preHandler: requireMember }, async (request, reply) => {
    // Body: route definition (nodes, observers, thresholds, window)
    // Run the subsequence matcher against raw_receptions.path_hashes (D5)
    // Returns: { state, quality, matched_count, matches: [{ wire_hash, received_at, positions }] }
});
```

Same algorithm as the `route-evaluator` job, but on-demand and stateless (no writes). Used by the Routes modal's "Preview" button.

### Observer-area aggregation

```typescript
// Distinct area tag values + node counts (drives the map/messages area filter)
fastify.get("/api/v1/observers/areas", async (request, reply) => {
    // SELECT tag.value, COUNT(DISTINCT tag.node_id) FROM node_tags tag
    //   JOIN nodes n ON n.id = tag.node_id
    //   WHERE tag.key = 'area' AND n.is_observer = true
    //   GROUP BY tag.value ORDER BY tag.value
    // Returns: { areas: [{ value, node_count }] }
});
```

Replaces the client-side 500-node fetch + dedup (FE6, F6). One small query, cacheable in the `nodes` namespace.
