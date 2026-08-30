# Tasks: RSS/Atom Feeds for Public Mesh Data

> Generated from `plan.md` on 2026-08-30 (target release: v0.21.0)

## 1. Cache Layer Groundwork (Phase 1)

- [x] Extend `@cached` in `src/meshcore_hub/api/cache.py` with optional `response_builder: Callable[[Any], Response] | None = None`
  - [x] On cache MISS, wrap the fresh handler result via `response_builder` before returning
  - [x] On cache HIT, wrap the JSON-deserialized stored body via `response_builder` (fixes XML round-trip JSON-quoting)
  - [x] Leave the 304/If-None-Match short-circuit unchanged
  - [x] Default `None` preserves exact current behavior for every existing endpoint
- [x] Unit-test `response_builder` on both wrappers (sync + async): MISS returns wrapped `Response`, HIT returns wrapped stored body
- [x] Verify: `pytest --no-cov tests/test_api/test_cache.py`

## 2. Settings (Phase 1)

- [x] `src/meshcore_hub/common/config.py`: add `APISettings.feeds_enabled: bool = True` (env `FEATURE_FEEDS`)
- [x] Add `APISettings.redis_cache_ttl_feeds: int = 300` (env `REDIS_CACHE_TTL_FEEDS`; naming matches `redis_cache_ttl_dashboard`)
- [x] Add `WebSettings.feature_feeds: bool = True` plus a `"feeds"` entry in the web `features` dict
- [x] Move `network_name` from `WebSettings` to `CommonSettings` (env `NETWORK_NAME` unchanged; additive — all settings classes extend `CommonSettings`)
- [x] Wire `app.state.feeds_enabled` / `app.state.redis_cache_ttl_feeds` in `api/app.py::create_app` and the `create_app_from_env` path
- [x] Verify: `pytest --no-cov tests/test_common/` and settings-related web tests still pass after the `network_name` move

## 3. Feed XML Builders (Phase 2)

- [x] Create `src/meshcore_hub/api/feed_xml.py` with a shared item dataclass (title, description/text, guid + isPermaLink flag, absolute link, publication date)
- [x] `build_rss(feed_meta, items) -> str`: RSS 2.0 via stdlib `xml.etree.ElementTree`; RFC 822 dates (`email.utils.format_datetime`); `lastBuildDate` = newest item date or feed build time
- [x] `build_atom(feed_meta, items) -> str`: Atom; RFC 3339 dates (`isoformat`); `updated` = newest item date or feed build time
- [x] Declare UTF-8 encoding; rely on ElementTree escaping for all user text (XML-injection guard for message payloads)
- [x] Feed metadata: title from `NETWORK_NAME` (channel feeds append the channel name), feed `link` points at the corresponding SPA page

## 4. Feed Routes (Phase 2)

- [x] Create `src/meshcore_hub/api/routes/feeds.py` with eight route handlers (4 feeds × RSS/Atom) sharing per-kind query functions
  - [x] Handlers return the XML string; `response_builder` wraps into a `Response` with `Cache-Control: public, max-age=<ttl>` and Content-Type `application/rss+xml; charset=utf-8` / `application/atom+xml; charset=utf-8`
  - [x] Decorate with `@cached("feeds", ttl_setting="redis_cache_ttl_feeds", key_builder=<path-based>)`; key = `feeds:{request.url.path}` (no query params → stable keys)
  - [x] 404 fast-path when `app.state.feeds_enabled` is false
  - [x] Auth via `RequireRead`: public keyless, 401 under `API_READ_KEY` (never read `X-User-*` headers)
- [x] Messages feed: newest 50 across anonymous-visible channels (`get_visible_channel_indices(session, 0)` — includes built-in idx 17), non-channel message types included, spam filter always on (mirror `routes/messages.py:104-115`: `spam_detection_enabled` + threshold from `app.state`), fixed limit 50
- [x] Adverts feed: dedup by `public_key` keeping the newest advert per node, limit 50 nodes newest-first (choose Postgres `DISTINCT ON` vs subquery to match the query style in `routes/advertisements.py` — review action item)
- [x] Nodes feed: 50 by `Node.created_at` descending (`TimestampMixin`)
- [x] Per-channel feed: 404 unless channel is community-visibility AND enabled (idx 17 always allowed — deliberately stricter than `/messages` and the anonymous `/channels` list); title from DB `Channel.name`, idx 17 via `LetsMeshPacketDecoder(channel_keys=[]).channel_labels_by_index()` (import from `meshcore_hub.collector.letsmesh_decoder`), literal `"Public"` fallback
- [x] Item shapes (FR-2), names via `resolve_sender_names` / node tag-name fallbacks:
  - [x] messages: guid `packet_hash` (isPermaLink=false; fallback `msg:{id}` when null), link `{base}/packets/hash/{packet_hash}` (fallback `{base}/messages`), date `received_at`
  - [x] adverts: guid `advert:{id}` (no `packet_hash` on the model), link `{base}/nodes/{public_key}`, date `received_at`, `advert_timestamp` in description
  - [x] nodes: guid `node:{public_key}` (isPermaLink=false), link `{base}/nodes/{public_key}`, date `created_at`
  - [x] per-channel feed-level link: `{base}/messages?channel_idx={idx}`
- [x] Base-URL helper (TR-6): prefer `X-Forwarded-Host`/`X-Forwarded-Proto`, fallback `request.base_url`
- [x] Register the router in `api/routes/__init__.py` under `prefix="/feeds", tags=["Feeds"]`

## 5. Feed Tests (Phase 2)

- [x] Create `tests/test_api/test_feeds.py` covering:
  - [x] Well-formed RSS/Atom (ElementTree/bs4 parse, root elements, namespaces)
  - [x] Community message present; member/admin-channel message absent **even with `X-User-Roles: admin`**
  - [x] Spam excluded (respecting the spam master switch)
  - [x] Escaping of `<script>` / `&` payloads
  - [x] Adverts dedup: two adverts for one node → one item, the newest
  - [x] Per-channel 404 for member-visibility and disabled channels
  - [x] Per-channel title from `Channel.name` and `"Public"` for idx 17
  - [x] Item links point at `/packets/hash/…`, `/nodes/…`, `/messages?channel_idx=…`
  - [x] Content-Type, `Cache-Control: public`, ETag + 304 + `X-Cache: HIT`
  - [x] `FEATURE_FEEDS=false` → 404
  - [x] Redis outage (mock raising `RedisError`) → 503
- [x] Verify: `pytest --no-cov tests/test_api/test_feeds.py`

## 6. Cache Invalidation (Phase 3)

- [x] `src/meshcore_hub/api/cache_invalidation.py`: add `_drop(request, "feeds")` (glob style, matches existing helpers) to `invalidate_messages`, `invalidate_advertisements`, and `invalidate_channels`
- [x] Extend `tests/test_api/test_cache.py::TestMutationInvalidationIntegration` to assert the three helpers drop `feeds:` keys
- [x] Extend `TestKeyBuilders` to assert the feeds key builder's prefix
- [x] Verify: `pytest --no-cov tests/test_api/test_cache.py`

## 7. Web Tier: Proxy, Alias, Discovery (Phase 4)

- [x] Refactor the `/api/{path:path}` proxy body (`web/app.py:829-931`) into a shared internal helper, maintenance gate (`system_maintenance` 503) included so the alias inherits it
- [x] Forward `If-None-Match`, `X-Forwarded-Host`, `X-Forwarded-Proto` from the incoming request (enables end-to-end 304s and correct absolute links)
- [x] Add `"v1/feeds": {"GET": _OPEN}` to `_build_endpoint_access` (longest-prefix match covers `v1/feeds/channels/…`)
- [x] Add `GET /feeds/{path:path}` alias delegating to the shared helper with rewritten path `v1/feeds/{path}`; 404 when `feeds_enabled` is false
- [x] `spa_catchall` (`web/app.py:1383-1398`): compute `feed_links` from `app.state.features` — per-feed gating (e.g. messages feed link renders only when `features.messages` is also on) — and pass into the `spa.html` render context
- [x] `web/templates/spa.html` `<head>`: feature-gated `<link rel="alternate" type="application/rss+xml">` / `application/atom+xml">` tags from `feed_links`
- [x] Web tests:
  - [x] `/feeds/messages.xml` anonymous passthrough via `MockHttpClient` (assert proxied path/params and that `If-None-Match` + `X-Forwarded-*` are forwarded)
  - [x] Regression (TR-8, no middleware change): `Cache-Control` and `ETag` survive the alias round-trip
  - [x] SPA head contains autodiscovery links when enabled; omitted under `FEATURE_FEEDS=false` and `feature_messages=false`
- [x] Verify: `pytest --no-cov tests/test_web/`

## 8. Docs & Config (Phase 5)

- [x] `.env.example`: add `FEATURE_FEEDS` and `REDIS_CACHE_TTL_FEEDS` entries with defaults and comments
- [x] `README.md`: add a feeds section (URLs, formats, gating)
- [x] `AGENTS.md`: add the feeds row to the cache-invalidation mapping table
- [x] `docs/upgrading.md`: new `## v0.21.0` section inserted above `## v0.20.0` — informational only (new `/feeds/*` + `/api/v1/feeds/*` endpoints, two optional env vars with defaults, `NETWORK_NAME` settings-class move with env name unchanged; no breaking changes, no required operator actions)
- [x] No `pyproject.toml` version bump (git-tag-only versioning)

## 9. Verification

- [x] `pytest -nauto --no-cov 2>&1 | grep -iE "passed|failed" | tail -3`
- [x] `pre-commit run --all-files`
- [x] Confirm no `spa-react` TS changes → `npx tsc --noEmit` unaffected
- [x] No Docker builds or `make build`/`make up` (user builds manually)

## 10. Optional Follow-Up (separate effort — do not block; out of scope per plan Non-Goals)

- [ ] Playwright e2e spec: `GET /feeds/messages.xml` returns 200 + parseable XML on the throwaway stack
