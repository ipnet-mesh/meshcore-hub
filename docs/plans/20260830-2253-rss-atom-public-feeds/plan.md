# RSS/Atom Feeds for Public Mesh Data

**Target release**: v0.21.0 — the next release; the latest tag is `v0.20.0` (mandatory Redis).

## Summary

Expose the hub's public content as subscribable web feeds. Four feeds — public messages, node adverts, new nodes, and per-community-channel messages — each served in both RSS 2.0 (`.xml`) and Atom (`.atom`) formats. Feed generation and Redis caching live in the API tier; the web tier exposes clean public URLs (`/feeds/messages.xml`) that pass through to the API, mirroring how the SPA consumes data.

Feeds always reflect a **logged-out user's view**: visibility is hard-pinned to the anonymous level (community-visibility channels + the built-in public channel 17), spam is always excluded, and proxy-injected identity headers (`X-User-Id`, `X-User-Roles`) are deliberately ignored so feeds can never leak member/operator/admin-channel content. Every feed response is cached in Redis behind the existing `@cached`/ETag machinery (extended to support non-XML→non-JSON bodies), with mutation-driven invalidation and a `public, max-age` Cache-Control policy that is safe because the content is anonymous-pinned.

## Background & Motivation

MeshCore Hub currently has no feed capability: no RSS/Atom library in `pyproject.toml`, no feed routes, and the only machine-readable site endpoints are the hand-rolled `/sitemap.xml` and `/robots.txt` (`web/app.py:1165-1246`). Community members and observers want to subscribe to mesh activity (new nodes joining, channel chatter) in their feed readers instead of polling the dashboard.

Relevant current state:

- **Auth model** (`api/auth.py`): `RequireRead` is open when no `API_READ_KEY` is configured (the documented default); with a key set it 401s. Feeds inherit this gate — they are never broader than the anonymous site.
- **Channel visibility** (`api/channel_visibility.py`): `VISIBILITY_LEVELS = {"community": 0, "member": 1, "operator": 2, "admin": 3}`; `get_visible_channel_indices(session, max_level)` for anonymous (level 0) yields community channels plus hardcoded public channel idx 17. `list_messages` applies this plus a spam filter (`routes/messages.py:104-127`).
- **Caching** (`api/cache.py`): the `@cached` decorator stores a JSON envelope `{"body", "etag"}` in Redis, handles ETag/304/If-None-Match, and sets `request.state.cache_control_ttl`. It is JSON-shaped: on a cache HIT it returns the JSON-deserialized body, which would JSON-quote an XML string — it needs a small, opt-in extension (a `response_builder`) to round-trip XML. The API middleware forces `private, no-cache` on `/api/*` GETs **unless the handler sets its own Cache-Control** (`api/app.py:261-264`), so feeds can emit `public, max-age=<ttl>`.
- **Invalidation** (`api/cache_invalidation.py`): helpers drop Redis key prefixes after committed mutations, per the AGENTS.md mapping table. Feeds must join this system.
- **Web tier** (`web/app.py`): the `/api/{path:path}` proxy denies unlisted prefixes (`check_api_access`, `_build_endpoint_access` at lines 175-257), forwards only `content-type` plus injected `X-User-*` headers — it drops `If-None-Match` and sends no `X-Forwarded-Host`/`X-Forwarded-Proto`. Consequences: 304s never work through the public origin, and the API tier cannot build correct absolute links. Both need small proxy fixes that also benefit the SPA's ETag revalidation generally.
- **Redis is mandatory** since v0.20 (commit 3593d14; plan `20260830-2057-mandatory-redis`) — a Redis outage 503s cached reads, and feeds follow the same contract.

The user confirmed the following direction during planning: feeds are a web-facing feature (web tier passes through; resources reflect a logged-out user), all four feed types are in scope for v1, and XML is generated with stdlib `xml.etree.ElementTree` (zero new dependencies, automatic escaping — following the hand-rolled sitemap precedent rather than adding `feedgen`, which would drag in compiled `lxml`).

## Goals

- Provide RSS 2.0 + Atom feeds for: public messages, adverts, new nodes, and each community-visibility channel.
- Guarantee feeds only ever expose anonymous-visible, non-spam content — regardless of any identity/role headers on the request.
- Serve feeds at clean public URLs on the web tier (`/feeds/...`) backed by API-tier generation, with correct absolute item links pointing at the SPA pages.
- Cache all feed responses in Redis with ETag/304 support and prompt invalidation on relevant mutations.
- Support conditional GETs end-to-end through the web proxy (forward `If-None-Match`), improving the SPA's cache story as a side effect.
- Provide a `FEATURE_FEEDS` kill switch (default enabled) and configurable feed TTL (`REDIS_CACHE_TTL_FEEDS`, default 300s).
- Make feeds discoverable: feature-gated `<link rel="alternate">` autodiscovery tags in the SPA shell `<head>`.

## Non-Goals

- Authenticated or role-aware feeds (member/operator/admin channel content is never fed).
- Feed requests carrying per-user identity or personalization of any kind.
- New frontend SPA pages or React changes (the SPA is untouched; only the Jinja `spa.html` head gains link tags).
- Per-channel feeds for non-community visibility tiers; disabled channels 404.
- `feedgen`/`lxml` or any new runtime dependency.
- Publishing feed URLs in `sitemap.xml` or `robots.txt` (feeds are for readers, not crawlers).
- WebSub/WebMention push notification support.
- E2E Playwright specs for feeds (optional follow-up; unit/integration coverage is in scope).

## Requirements

### Functional Requirements

- **FR-1 — Feeds and formats.** Four feeds, each in RSS 2.0 and Atom:
  - `messages` — newest 50 messages across anonymous-visible channels (community + built-in public idx 17), non-channel message types included as the anonymous `/messages` page shows them, spam excluded (respecting the spam master switch).
  - `adverts` — **deduplicated by node**: the newest advert per `public_key` (limit 50 nodes, newest first). Nodes re-advertise constantly; raw rows would repeat the same handful of nodes within minutes.
  - `nodes` — 50 nodes by `created_at` descending ("who just joined the mesh").
  - `channels/{idx}` — newest 50 messages on one channel; **404 unless the channel is community-visibility AND enabled** (idx 17 always allowed). Note this is deliberately stricter than `/messages` (which still shows historical messages from disabled channels) and than the anonymous `/channels` list (which lists disabled community channels): a disabled channel no longer receives traffic, so its feed is dead and should 404 rather than serve stale history. Feed title uses the DB `Channel.name` (plaintext column, readable from the API tier); idx 17 uses the built-in decoder label ("Public") via `LetsMeshPacketDecoder(channel_keys=[]).channel_labels_by_index()` (same call the web tier makes; import from `meshcore_hub.collector.letsmesh_decoder`), literal `"Public"` fallback.
- **FR-2 — Item shape.** Each item has: title (sender/node display name via `resolve_sender_names` / node tag-name fallbacks), full text/description, guid, publication date, and an absolute `link` deep-linking the SPA (routes verified in `App.tsx`):
  - messages: guid `packet_hash` (isPermaLink=false; fallback guid `msg:{id}` when null), link `{base}/packets/hash/{packet_hash}` (the SPA's packet-detail route, which `Messages.tsx` already deep-links to; fallback `{base}/messages` when `packet_hash` is null), date `received_at`.
  - adverts: guid `advert:{id}` (the `Advertisement` model has no `packet_hash`), link `{base}/nodes/{public_key}` (SPA route `/nodes/:publicKey`), date `received_at` (advert payload time `advert_timestamp` in the description).
  - nodes: guid `node:{public_key}` (isPermaLink=false), link `{base}/nodes/{public_key}`, date `created_at`.
  - Per-channel feed-level link: `{base}/messages?channel_idx={idx}` (`Messages.tsx` reads `channel_idx` from search params).
- **FR-3 — Feed metadata.** Feed title uses `NETWORK_NAME`; channel feeds append the channel name; feed `link` points at the corresponding SPA page; Atom `updated`/RSS `lastBuildDate` reflect the newest item (or feed build time when empty).
- **FR-4 — Public URLs.** Web tier serves `GET /feeds/{path}` (e.g. `/feeds/messages.xml`, `/feeds/messages.atom`, `/feeds/channels/17.xml`) by proxying to API `v1/feeds/...`; `/api/v1/feeds/...` also works directly (proxy access map lists `v1/feeds: GET = _OPEN`). The alias delegates to the same proxy helper, so maintenance-mode 503 gating (`system_maintenance`) applies to feeds automatically.
- **FR-5 — Logged-out view pinning.** Feed handlers never read `X-User-*` headers; visibility is computed at anonymous level; spam filtering cannot be disabled via feed parameters; no user-controllable filters or pagination exist on feed endpoints (fixed limit 50 keeps cache keys stable).
- **FR-6 — Auth inheritance.** Feed routes use `RequireRead`: public in default keyless deployments; 401 under `API_READ_KEY` (identical to a logged-out user's proxied `/api/v1/messages` call).
- **FR-7 — Kill switch.** `FEATURE_FEEDS=false` → API feed routes 404, web alias 404s, autodiscovery links omitted, `features.feeds = false` in `__APP_CONFIG__`.
- **FR-8 — Discovery.** `spa.html` `<head>` includes `<link rel="alternate" type="application/rss+xml">` / `application/atom+xml` tags for the enabled feeds. Gating policy: **endpoints gate on `FEATURE_FEEDS` only** (consistent with API routes ignoring web feature flags — `/api/v1/messages` serves regardless of `FEATURE_MESSAGES` today); **autodiscovery links additionally gate per-feed** (e.g. the messages feed links render only when `features.messages` is also on), so disabled UI pages don't advertise feeds for themselves. Links are passed into the template as a `feed_links` context variable computed in `spa_catchall` from `app.state.features`.

### Technical Requirements

- **TR-1 — XML generation.** Stdlib `xml.etree.ElementTree` in a new `api/feed_xml.py`: RSS 2.0 (RFC 822 dates via `email.utils.format_datetime`) and Atom (RFC 3339 via `isoformat`) builders sharing one item-abstraction; all user text is ElementTree-escaped (guards against XML injection via message text); declared encoding UTF-8; Content-Types `application/rss+xml; charset=utf-8` / `application/atom+xml; charset=utf-8`.
- **TR-2 — Cache decorator extension.** `cached()` gains an optional `response_builder: Callable[[Any], Response] | None = None`. When set, both the cache-HIT body and the fresh handler result are wrapped via it before returning (304 short-circuit unchanged). Default `None` preserves current behavior for every existing endpoint.
- **TR-3 — Feed caching.** Routes use `@cached("feeds", ttl_setting="redis_cache_ttl_feeds", key_builder=...)` with a path-based key builder returning `f"feeds:{request.url.path}"` (URL-path key style, matching the existing `key_builder` convention; no query params → stable keys). Handlers return the XML string; `response_builder` wraps it into a `Response` carrying `Cache-Control: public, max-age=<ttl>` (safe: anonymous-pinned content; the API middleware preserves handler-set headers). Redis outage → 503 per the mandatory-backend contract.
- **TR-4 — Invalidation.** Add `_drop(request, "feeds")` (glob `feeds*`, matching the existing prefix style of `nodes`/`advertisements`/`dashboard`) to `invalidate_messages`, `invalidate_advertisements`, and `invalidate_channels` (node-tag renames and adoptions already route through these; node creation arrives via the collector and is TTL-bounded). Update the AGENTS.md invalidation table.
- **TR-5 — Proxy improvements.** Refactor the `/api/{path:path}` proxy body into a shared helper; forward `If-None-Match` (enables end-to-end 304s, also for the SPA) and `X-Forwarded-Host`/`X-Forwarded-Proto` (from the incoming request) so the API builds absolute URLs matching the public origin; the `/feeds/{path}` alias route delegates to the same helper with the rewritten API path.
- **TR-6 — Base URL derivation.** Feed link builder prefers `X-Forwarded-Host`/`X-Forwarded-Proto`, falling back to `request.base_url` (direct API access).
- **TR-7 — Settings.** `APISettings.feeds_enabled: bool = True` and `APISettings.redis_cache_ttl_feeds: int = 300` (env `FEATURE_FEEDS`, `REDIS_CACHE_TTL_FEEDS`), wired to `app.state` in `create_app`; `WebSettings.feature_feeds: bool = True` plus a `"feeds"` entry in the `features` dict. Move `network_name` from `WebSettings` to `CommonSettings` (env name unchanged) so both tiers can title feeds — additive; verify web/collector settings tests still pass.
- **TR-8 — Web cache policy.** Verified no middleware change is needed: the proxy copies every API response header except hop-by-hop ones (`web/app.py:898-907`), so the API's `Cache-Control: public, max-age` and `ETag` arrive intact, and `CacheControlMiddleware` skips any response that already carries `cache-control` (`web/middleware.py:39-41`). The `/feeds/*` alias reuses the same proxy helper, so it inherits this. Keep a regression test asserting the header survives the alias round-trip.
- **TR-9 — Tests.**
  - New `tests/test_api/test_feeds.py`: well-formed RSS/Atom (ElementTree/bs4 parse, root elements/namespaces); community message present; member/admin-channel message absent **even with `X-User-Roles: admin`**; spam excluded; escaping of `<script>`/`&` payloads; adverts dedup (two adverts for one node → one item, the newest); per-channel 404 for member/disabled channels; per-channel title from `Channel.name` and `"Public"` for idx 17; item links point at `/packets/hash/…`, `/nodes/…`, `/messages?channel_idx=…`; Content-Type; `Cache-Control: public`; ETag + 304 + `X-Cache: HIT`; flag off → 404; Redis outage → 503 (mock raising `RedisError`).
  - `tests/test_api/test_cache.py`: `TestMutationInvalidationIntegration` asserts the three helpers drop `feeds:`; `TestKeyBuilders` asserts the feeds key builder's prefix; a `response_builder` round-trip test (MISS returns wrapped Response, HIT returns wrapped stored body).
  - `tests/test_web/`: `/feeds/messages.xml` proxy passthrough anonymous-OK via `MockHttpClient` (assert proxied path/params and that `If-None-Match`/`X-Forwarded-*` are forwarded); SPA head contains autodiscovery links when enabled and omits them under `FEATURE_FEEDS=false` / `feature_messages=false`.
- **TR-10 — Docs/config surface.** `.env.example` entries (`FEATURE_FEEDS`, `REDIS_CACHE_TTL_FEEDS`), README feeds section, AGENTS.md invalidation-table row for feeds, and a new `## v0.21.0` section in `docs/upgrading.md` (inserted above `## v0.20.0`, following the repo's per-release convention — cf. the v0.20 plan's own upgrading-notes deliverable). The v0.21 section is informational — no breaking changes: new `/feeds/*` + `/api/v1/feeds/*` endpoints, two optional env vars with defaults, `NETWORK_NAME` moved between settings classes with its env name unchanged. No `pyproject.toml` version bump — this repo versions via git tags only (`version = "0.0.0"` in pyproject).

## Implementation Plan

### Phase 1: Cache layer + settings groundwork
- Extend `cached()` in `src/meshcore_hub/api/cache.py` with `response_builder` (opt-in, default `None`); unit-test both wrappers (sync + async) for wrap-on-MISS and wrap-on-HIT.
- `src/meshcore_hub/common/config.py`: add `APISettings.feeds_enabled` + `APISettings.redis_cache_ttl_feeds`; add `WebSettings.feature_feeds` + `features["feeds"]`; move `network_name` to `CommonSettings`.
- Wire `app.state.feeds_enabled` / `app.state.redis_cache_ttl_feeds` in `api/app.py::create_app` (and `create_app_from_env` path).
- Verify: `pytest --no-cov tests/test_api/test_cache.py tests/test_common/`.

### Phase 2: Feed generation (API tier)
- New `src/meshcore_hub/api/feed_xml.py`: item dataclass + `build_rss(feed_meta, items) -> str` + `build_atom(feed_meta, items) -> str` (ElementTree, escaped, dated, generator comment optional).
- New `src/meshcore_hub/api/routes/feeds.py` with eight route handlers (4 feeds × 2 formats) sharing per-kind query functions: anonymous-pinned visibility (`get_visible_channel_indices(session, 0)` — never consult request headers), spam filter always on (`spam_detection_enabled` + threshold from `app.state`, mirroring `routes/messages.py:104-115`), fixed limit 50; adverts query dedups by `public_key` keeping the newest advert per node (e.g. distinct-on / subquery join on max `received_at`); nodes query orders by `Node.created_at desc` (TimestampMixin); per-channel handler validates community-visibility + enabled (404 otherwise) and resolves the channel title (DB `Channel.name`; idx 17 → built-in decoder label, `"Public"` fallback); item links built per FR-2 via a shared base-URL helper (TR-6).
- Decorate with `@cached("feeds", ttl_setting="redis_cache_ttl_feeds", key_builder=<path-based>)` + `response_builder` producing the XML `Response` with `Cache-Control: public, max-age=<ttl>`; 404 fast-path when `app.state.feeds_enabled` is false.
- Register the router in `api/routes/__init__.py` under `prefix="/feeds", tags=["Feeds"]`.
- Verify: `pytest --no-cov tests/test_api/test_feeds.py` (written alongside).

### Phase 3: Invalidation wiring
- `src/meshcore_hub/api/cache_invalidation.py`: `_drop(request, "feeds:")` in `invalidate_messages`, `invalidate_advertisements`, `invalidate_channels`.
- Extend `tests/test_api/test_cache.py::TestMutationInvalidationIntegration` + `TestKeyBuilders`; update the AGENTS.md mapping table.

### Phase 4: Web tier — proxy, alias, discovery
- `src/meshcore_hub/web/app.py`: refactor the proxy body (`web/app.py:829-931`) into a reusable internal helper (maintenance gate included, so the alias inherits it); forward `If-None-Match`, `X-Forwarded-Host`, `X-Forwarded-Proto`; add `"v1/feeds": {"GET": _OPEN}` to `_build_endpoint_access` (longest-prefix match covers `v1/feeds/channels/…` sub-paths); add `GET /feeds/{path:path}` alias delegating with `v1/feeds/{path}` (respecting `feeds_enabled` → 404); compute `feed_links` in `spa_catchall` from `app.state.features` and pass into the `spa.html` render context (explicit context dict at `web/app.py:1383-1398`).
- `src/meshcore_hub/web/middleware.py`: no change expected (TR-8) — add the regression test only.
- `src/meshcore_hub/web/templates/spa.html`: feature-gated autodiscovery `<link rel="alternate">` tags in `<head>`.
- Verify: `pytest --no-cov tests/test_web/`.

### Phase 5: Tests, docs, polish
- Complete the TR-9 test matrix; update `.env.example`, `README.md`, `AGENTS.md`, and add the `docs/upgrading.md` `## v0.21.0` section (TR-10).
- Full verification: `pytest -nauto --no-cov 2>&1 | grep -iE "passed|failed" | tail -3`, then `pre-commit run --all-files`. No frontend TS changes → `tsc` unaffected. No Docker builds (per policy — user builds manually).
- Optional follow-up (separate effort): Playwright e2e spec asserting `GET /feeds/messages.xml` returns 200 + parseable XML on the throwaway stack.

## References

- Prior plans:
  - `docs/plans/20260609-2106-redis-api-cache/plan.md` — introduced `@cached`, ETag/304, key prefixes, invalidation design (this plan extends it with `response_builder`).
  - `docs/plans/20260830-2057-mandatory-redis/plan.md` — Redis as mandatory backend; feeds inherit the 503-on-outage contract.
  - `docs/plans/20260519-2051-channel-model-db-decrypt/plan.md` — channel model + visibility tiers the feeds must respect.
  - `docs/plans/20260622-2243-spam-detection/plan.md` — spam scoring/filter semantics reused by the messages feed.
- Key source: `api/cache.py`, `api/cache_invalidation.py`, `api/channel_visibility.py`, `api/routes/messages.py`, `api/routes/advertisements.py`, `api/app.py` (middleware), `web/app.py` (proxy/endpoint-access/sitemap precedent), `web/templates/spa.html`.
- Relevant commits: `3593d14` feat(api): make Redis a required cache dependency; `c643c50` chore(db): remove v0.19 Postgres-transition shims.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-08-30 (initial review); 2026-08-30 (second pass — v0.21 release scoping)

### Resolutions

- **v0.21 release scoping (second pass)**: Confirmed the release train — the latest tag is `v0.20.0` (mandatory Redis; untagged at first check during review, tagged shortly after), so this plan targets **v0.21.0**, the next release. Added the target-release line to the Summary. No other `docs/plans/*/plan.md` targets v0.21, so there are no same-release conflicts; the plan's dependency on mandatory Redis is already released in v0.20.
- **Upgrading notes gap (second pass)**: The repo convention (established by the v0.20 plan) is a per-release `## v0.XX.0` section in `docs/upgrading.md`. TR-10 and Phase 5 now include a `## v0.21.0` section (inserted above `## v0.20.0`): informational — new feed endpoints, `FEATURE_FEEDS` + `REDIS_CACHE_TTL_FEEDS` env vars (both optional with defaults), `NETWORK_NAME` settings-class move with env name unchanged; no breaking changes, no required operator actions.
- **Version-bump non-task (second pass)**: The project versions via git tags only (`pyproject.toml` stays `0.0.0`), so no version-file bump is needed — noted in TR-10 to prevent a spurious task.
- **SPA deep-link targets (open question)**: Resolved from code — SPA route `/packets/hash/:hash` exists (`App.tsx:189`) and `Messages.tsx` already deep-links messages there when packets are enabled; `/nodes/:publicKey` route confirmed (`App.tsx:128`); `Messages.tsx` reads `channel_idx` from search params. Item links: messages → `/packets/hash/{packet_hash}` (fallback `/messages`), adverts/nodes → `/nodes/{public_key}`, per-channel feed link → `/messages?channel_idx={idx}`. No `search` URL param exists on the messages page, so per-message search-permalinks are not used.
- **Per-feature endpoint gating (open question)**: Resolved — endpoints gate on `FEATURE_FEEDS` only (consistent with API routes ignoring web feature flags); autodiscovery links additionally gate per-feed (FR-8).
- **Channel title source (open question)**: Resolved — `Channel.name` is a plaintext DB column readable from the API tier (no decryption involved; the `channel-model-db-decrypt` plan concerns channel *keys*, not names). idx 17 (no DB row) uses the built-in decoder label via `LetsMeshPacketDecoder(channel_keys=[]).channel_labels_by_index()` (import from `meshcore_hub.collector.letsmesh_decoder`, same as the web tier), literal `"Public"` fallback.
- **Feed max-age value (open question)**: Resolved — pinned to `REDIS_CACHE_TTL_FEEDS` (default 300s); readers revalidate cheaply via ETag/304 and invalidation keeps freshness, matching the rest of the cache layer.
- **Adverts feed noise (user decision)**: Deduplicate by `public_key` — newest advert per node, limit 50 — confirmed by the user; raw-row mode rejected as too noisy. Incorporated into FR-1/TR-9.
- **Adverts guid**: `Advertisement` model has no `packet_hash` — plan corrected to guid `advert:{id}` (was "packet_hash for adverts").
- **TR-8 web cache policy**: Verified no middleware change is needed — the proxy forwards all non-hop-by-hop API response headers (`web/app.py:898-907`) and `CacheControlMiddleware` skips responses that already carry `cache-control` (`web/middleware.py:39-41`). Reduced to a regression test.
- **Invalidation prefix style**: Corrected `_drop(request, "feeds:")` → `_drop(request, "feeds")` to match existing helper style (`nodes`, `dashboard`, …); `delete(prefix)` globs `{prefix}*` so all feed keys are covered.
- **Cache key format**: Specified as `f"feeds:{request.url.path}"` (URL-path key style consistent with existing `key_builder` endpoints).
- **Maintenance mode**: `/feeds/{path}` alias delegates to the refactored proxy helper, so the `system_maintenance` 503 gate applies to feeds automatically (FR-4/Phase 4).
- **Disabled-channel strictness**: Documented as deliberate — per-channel feed 404s for disabled channels even though `/messages` still shows their historical messages and the anonymous `/channels` list includes them (a disabled channel receives no new traffic, so a live feed for it is meaningless).
- **Messages item guid fallback**: `packet_hash` can be null on some message rows — added `msg:{id}` guid fallback and `/messages` link fallback (FR-2/TR-9).
- **Settings hierarchy**: Verified `CollectorSettings`/`APISettings`/`WebSettings` all extend `CommonSettings` (config.py:27/175/404/469), so moving `network_name` to `CommonSettings` is additive and safe; TTL setting name `redis_cache_ttl_feeds` matches the existing `redis_cache_ttl_dashboard` pattern (config.py:441-445).
- **Plan-overlap check**: grep across all `docs/plans/*/plan.md` found no conflicting or overlapping plans (other "feed" mentions are MQTT feed types).

### Remaining Action Items

- Implement per the five phases; run targeted suites after each phase and `pre-commit run --all-files` at the end.
- Confirm the adverts dedup query shape (Postgres `DISTINCT ON (public_key)` vs subquery join) during Phase 2 — either is acceptable; prefer whichever the existing query style in `routes/advertisements.py` matches.
- Optional follow-up (separate effort): Playwright e2e spec asserting `GET /feeds/messages.xml` returns 200 + parseable XML on the throwaway stack.
