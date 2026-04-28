# Plan: Remove Header-Based Auth

**Date:** 2026-04-28
**Status:** Approved
**Scope:** Remove all header-based proxy authentication mechanisms; keep `WEB_ADMIN_ENABLED` as a simple feature flag and preserve Admin UI components.

## Background

The web dashboard currently uses a two-layer auth architecture:

1. **Web layer (header-based proxy auth)** — An external reverse proxy (OAuth2Proxy, Nginx with basic auth) authenticates users and injects headers (`X-Forwarded-User`, `X-Auth-Request-User`, `Authorization: Basic`). The web app reads these headers via `_is_authenticated_proxy_request()` to gate admin UI and block mutating API proxy calls.
2. **API layer (Bearer token auth)** — The backend API uses `HTTPBearer` tokens (`require_read`/`require_admin` in `api/auth.py`). This is independent and **not in scope**.

The plan is to implement native OAuth/OIDC support in a future unit of work. This plan removes the header-based login mechanisms only.

## Decisions

- **Keep `WEB_ADMIN_ENABLED`** as a simple feature flag (Option A). It toggles admin UI visibility without any auth dependency. The future OIDC work will add proper session auth.
- **Remove the `/oauth2/` skip rule** from the SPA router — no longer needed.
- **Keep `sign_in`/`sign_out` i18n keys** in `common` section — forward-compatible for future OIDC work.
- **API Bearer token auth** (`api/auth.py`, `require_read`, `require_admin`) is completely untouched.

---

## Phase 1: Python Source Changes

### 1.1 `src/meshcore_hub/common/config.py`

- **Remove** `web_trusted_proxy_hosts` field (lines 283-287) entirely
- **Update** `web_admin_enabled` description from `"requires OAuth2Proxy in front"` to `"Enable admin interface at /a/"`

### 1.2 `src/meshcore_hub/web/app.py`

- **Remove** `_is_authenticated_proxy_request()` function (lines 79-92)
- **Remove** `ProxyHeadersMiddleware` import and setup block (lines 248-254)
- **Remove** the startup warning block for trusted proxy hosts (lines 261-266)
- **In `_build_config_json()`**: Remove `"is_authenticated"` key (line 180)
- **In `api_proxy()` handler**:
  - Remove the auth proxy header forwarding block (lines 387-390)
  - Remove the 401 guard block for unauthenticated mutating requests (lines 392-404)
- **Keep** `admin_enabled` parameter in `create_app()` signature and `app.state.admin_enabled` (lines 199, 257-258, 286) — stays as a simple feature flag
- **Keep** `"admin_enabled"` in `_build_config_json()` (line 173)
- **Keep** `"admin_enabled"` in SPA catch-all template context (line 736)

---

## Phase 2: JavaScript SPA Changes

### 2.1 `src/meshcore_hub/web/static/js/spa/pages/admin/index.js`

- **Remove** the `!config.is_authenticated` block (lines 20-28) with `/oauth2/start` link
- **Remove** the Sign Out link to `/oauth2/sign_out` (line 42)
- **Keep** the `!config.admin_enabled` guard (lines 8-17) and the authenticated admin content (lines 31-69)

### 2.2 `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`

- **Remove** the `!config.is_authenticated` block (lines 24-32) with `/oauth2/start` link
- **Remove** the Sign Out link to `/oauth2/sign_out` (line 316)
- **Keep** the `!config.admin_enabled` guard and all CRUD logic

### 2.3 `src/meshcore_hub/web/static/js/spa/pages/admin/members.js`

- **Remove** the `!config.is_authenticated` block (lines 23-31) with `/oauth2/start` link
- **Remove** the Sign Out link to `/oauth2/sign_out` (line 97)
- **Keep** the `!config.admin_enabled` guard and all CRUD logic

### 2.4 `src/meshcore_hub/web/static/js/spa/pages/node-detail.js`

- **Change** line 129 from `(config.admin_enabled && config.is_authenticated)` to just `config.admin_enabled`

### 2.5 `src/meshcore_hub/web/static/js/spa/router.js`

- **Remove** `href.startsWith('/oauth2/') ||` from the skip-rules (line 149)

---

## Phase 3: Template Changes

### 3.1 `src/meshcore_hub/web/templates/spa.html`

- **No changes needed** — the admin footer link is gated by `admin_enabled` which stays

---

## Phase 4: I18N Changes

### 4.1 `src/meshcore_hub/web/static/locales/en.json`

- **Remove** `"auth_required"` and `"auth_required_description"` from `admin` section
- **Keep** `access_denied`, `admin_not_enabled`, `admin_enable_hint`, `welcome`, `members_description`, `tags_description`
- **Keep** `"sign_in"` and `"sign_out"` in `common` section (forward-compatible for OIDC)

### 4.2 `src/meshcore_hub/web/static/locales/nl.json`

- Same changes as `en.json` — remove `auth_required` and `auth_required_description`

### 4.3 `docs/i18n.md`

- **Remove** rows for `auth_required` and `auth_required_description` from the admin section table (lines 343-344)

---

## Phase 5: Test Changes

### 5.1 `tests/test_web/test_admin.py`

- **Remove** fixtures: `auth_headers`, `auth_headers_basic`, `auth_headers_auth_request` (lines 52-75)
- **Remove** entire `TestAdminApiProxyAuth` class (lines 240-347) — all server-side header auth enforcement tests
- **In `TestAdminHome`**:
  - Remove `test_admin_home_config_authenticated` (line 120)
  - Remove `test_admin_home_config_authenticated_with_basic_auth` (line 132)
  - Remove `test_admin_home_config_authenticated_with_auth_request_header` (line 146)
  - Remove `test_admin_home_unauthenticated_config` (line 194)
  - Remove `auth_headers` parameter from remaining tests that use it (lines 104, 110, 168, 172)
  - Keep `test_admin_home_returns_spa_shell`, `test_admin_home_config_admin_enabled`, `test_admin_home_disabled_*`
- **In `TestAdminNodeTags`**:
  - Remove `auth_headers` parameter from remaining tests (lines 210, 218, 225)
  - Keep route tests (they just test the shell is served)
  - Remove `test_node_tags_page_unauthenticated` (line 233)
- **Keep** `TestAdminFooterLink` class entirely

### 5.2 `tests/test_web/test_app.py`

- **Remove** entire `TestTrustedProxyHostsWarning` class (lines 149-279) — all 4 tests
- **Keep** `TestConfigJsonXssEscaping` class entirely (unrelated to auth)

### 5.3 `tests/test_web/test_home.py`

- **Remove** `test_home_unauthenticated` (line 91) — tests `is_authenticated: false`
- **Remove** `test_home_authenticated` (line 103) — tests `is_authenticated: true` with headers

### 5.4 `tests/test_web/test_advertisements.py`

- **Remove** `test_advertisements_config_unauthenticated` (line 94) — tests `is_authenticated: false`

### 5.5 `tests/test_web/conftest.py`

- **No changes needed** — the `admin_app` fixture uses `admin_enabled=True` which stays

---

## Phase 6: Documentation & Config Changes

### 6.1 `docs/hosting/nginx-proxy-manager.md`

- **Delete the entire file** — it's entirely about header-based auth proxy setup

### 6.2 `README.md`

- **Update** `WEB_ADMIN_ENABLED` row (line 376) — simplify description to `"Enable admin interface at /a/"` without the auth proxy mention
- **Remove** `WEB_TRUSTED_PROXY_HOSTS` row (line 377)

### 6.3 `AGENTS.md`

- **Update** `WEB_ADMIN_ENABLED` description (line 642) — remove `(default: false, requires auth proxy)` to `(default: false)`
- **Remove** `WEB_TRUSTED_PROXY_HOSTS` line (line 643)
- **Update** line 696 `WEB_ADMIN_ENABLED` reference if needed

### 6.4 `.env.example`

- **Update** the `WEB_ADMIN_ENABLED` comment block (lines 338-340) — remove "requires auth proxy in front"
- **Remove** the `WEB_TRUSTED_PROXY_HOSTS` comment block (lines 342-346)

### 6.5 `docker-compose.yml`

- **Keep** `WEB_ADMIN_ENABLED` line (line 268) — it's still a valid env var for the feature flag

### 6.6 `.agents/skills/docs-sync/references/documentation-checklist.md`

- **Remove** the entire NPM checklist block (lines 158-165) since the doc is being deleted
- **Remove** the `WEB_ADMIN_ENABLED` checklist item (line 162)

### 6.7 `.agents/skills/docs-sync/references/docker-source-guide.md`

- **Keep** the `WEB_ADMIN_ENABLED` row (line 196) since it's still a valid env var

---

## Phase 7: Verification

After all changes:

1. `pytest tests/test_web/` — all web tests pass
2. `pytest tests/test_api/test_auth.py` — API auth tests untouched, still pass
3. `pre-commit run --all-files` — linting/type checking passes
4. `pytest` — full suite passes with no regressions

---

## Files Modified Summary

| # | File | Action |
|---|------|--------|
| 1 | `src/meshcore_hub/common/config.py` | Remove `web_trusted_proxy_hosts`, update `web_admin_enabled` description |
| 2 | `src/meshcore_hub/web/app.py` | Remove `_is_authenticated_proxy_request()`, `ProxyHeadersMiddleware`, header forwarding, 401 guard, `is_authenticated` in config |
| 3 | `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` | Remove auth guard + sign in/out links |
| 4 | `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` | Remove auth guard + sign out link |
| 5 | `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` | Remove auth guard + sign out link |
| 6 | `src/meshcore_hub/web/static/js/spa/pages/node-detail.js` | Simplify `admin_enabled && is_authenticated` → `admin_enabled` |
| 7 | `src/meshcore_hub/web/static/js/spa/router.js` | Remove `/oauth2/` skip rule |
| 8 | `src/meshcore_hub/web/static/locales/en.json` | Remove `auth_required*` keys |
| 9 | `src/meshcore_hub/web/static/locales/nl.json` | Remove `auth_required*` keys |
| 10 | `tests/test_web/test_admin.py` | Remove auth fixtures, `TestAdminApiProxyAuth`, auth-related assertions |
| 11 | `tests/test_web/test_app.py` | Remove `TestTrustedProxyHostsWarning` class |
| 12 | `tests/test_web/test_home.py` | Remove auth-related tests |
| 13 | `tests/test_web/test_advertisements.py` | Remove unauthenticated config test |
| 14 | `docs/hosting/nginx-proxy-manager.md` | **Delete file** |
| 15 | `README.md` | Update env var table |
| 16 | `AGENTS.md` | Update env var descriptions |
| 17 | `.env.example` | Update/remove env var comments |
| 18 | `docs/i18n.md` | Remove `auth_required*` rows |
| 19 | `.agents/skills/docs-sync/references/documentation-checklist.md` | Remove NPM checklist |
| 20 | `.agents/skills/docs-sync/references/docker-source-guide.md` | Update `WEB_ADMIN_ENABLED` row |
