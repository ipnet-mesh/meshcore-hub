# Remove Header-Based Auth — Task Checklist

**Plan:** `docs/plans/20260428-1251-remove-header-auth/plan.md`
**Status:** Complete

---

## Phase 1: Python Source Changes

- [x] **1.1** `src/meshcore_hub/common/config.py` — Remove `web_trusted_proxy_hosts` field (lines 283-287)
- [x] **1.2** `src/meshcore_hub/common/config.py` — Update `web_admin_enabled` description to remove `"requires OAuth2Proxy in front"`
- [x] **1.3** `src/meshcore_hub/web/app.py` — Remove `_is_authenticated_proxy_request()` function (lines 79-92)
- [x] **1.4** `src/meshcore_hub/web/app.py` — Remove `ProxyHeadersMiddleware` import and setup block (lines 248-254)
- [x] **1.5** `src/meshcore_hub/web/app.py` — Remove startup warning block for trusted proxy hosts (lines 261-266)
- [x] **1.6** `src/meshcore_hub/web/app.py` — Remove `"is_authenticated"` key from `_build_config_json()` (line 180)
- [x] **1.7** `src/meshcore_hub/web/app.py` — Remove auth proxy header forwarding in `api_proxy()` handler (lines 387-390)
- [x] **1.8** `src/meshcore_hub/web/app.py` — Remove 401 guard block for unauthenticated mutating requests in `api_proxy()` handler (lines 392-404)

## Phase 2: JavaScript SPA Changes

- [x] **2.1** `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` — Remove `!config.is_authenticated` block with `/oauth2/start` link (lines 20-28)
- [x] **2.2** `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` — Remove Sign Out link to `/oauth2/sign_out` (line 42)
- [x] **2.3** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Remove `!config.is_authenticated` block with `/oauth2/start` link (lines 24-32)
- [x] **2.4** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Remove Sign Out link to `/oauth2/sign_out` (line 316)
- [x] **2.5** `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` — Remove `!config.is_authenticated` block with `/oauth2/start` link (lines 23-31)
- [x] **2.6** `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` — Remove Sign Out link to `/oauth2/sign_out` (line 97)
- [x] **2.7** `src/meshcore_hub/web/static/js/spa/pages/node-detail.js` — Change `(config.admin_enabled && config.is_authenticated)` to `config.admin_enabled` (line 129)
- [x] **2.8** `src/meshcore_hub/web/static/js/spa/router.js` — Remove `href.startsWith('/oauth2/') ||` from skip-rules (line 149)

## Phase 3: I18N Changes

- [x] **3.1** `src/meshcore_hub/web/static/locales/en.json` — Remove `"auth_required"` and `"auth_required_description"` from `admin` section
- [x] **3.2** `src/meshcore_hub/web/static/locales/nl.json` — Remove `"auth_required"` and `"auth_required_description"` from `admin` section

## Phase 4: Test Changes

- [x] **4.1** `tests/test_web/test_admin.py` — Remove `auth_headers`, `auth_headers_basic`, `auth_headers_auth_request` fixtures (lines 52-75)
- [x] **4.2** `tests/test_web/test_admin.py` — Remove entire `TestAdminApiProxyAuth` class (lines 240-347)
- [x] **4.3** `tests/test_web/test_admin.py` — In `TestAdminHome`: remove `test_admin_home_config_authenticated`, `test_admin_home_config_authenticated_with_basic_auth`, `test_admin_home_config_authenticated_with_auth_request_header`, `test_admin_home_unauthenticated_config`
- [x] **4.4** `tests/test_web/test_admin.py` — In `TestAdminHome`: remove `auth_headers` param from remaining tests (`test_admin_home_returns_spa_shell`, `test_admin_home_config_admin_enabled`, `test_admin_home_disabled_*`)
- [x] **4.5** `tests/test_web/test_admin.py` — In `TestAdminNodeTags`: remove `auth_headers` param from remaining tests, remove `test_node_tags_page_unauthenticated`
- [x] **4.6** `tests/test_web/test_app.py` — Remove entire `TestTrustedProxyHostsWarning` class (lines 149-279)
- [x] **4.7** `tests/test_web/test_home.py` — Remove `test_home_unauthenticated` and `test_home_authenticated`
- [x] **4.8** `tests/test_web/test_advertisements.py` — Remove `test_advertisements_config_unauthenticated`

## Phase 5: Documentation & Config Changes

- [x] **5.1** Delete `docs/hosting/nginx-proxy-manager.md` entirely
- [x] **5.2** `README.md` — Update `WEB_ADMIN_ENABLED` row to remove auth proxy mention; remove `WEB_TRUSTED_PROXY_HOSTS` row
- [x] **5.3** `AGENTS.md` — Update `WEB_ADMIN_ENABLED` description, remove `WEB_TRUSTED_PROXY_HOSTS` line
- [x] **5.4** `.env.example` — Update `WEB_ADMIN_ENABLED` comment to remove "requires auth proxy in front"; remove `WEB_TRUSTED_PROXY_HOSTS` block
- [x] **5.5** `docs/i18n.md` — Remove `auth_required` and `auth_required_description` rows from admin section table
- [x] **5.6** `.agents/skills/docs-sync/references/documentation-checklist.md` — Remove NPM checklist block and `WEB_ADMIN_ENABLED` checklist item
- [x] **5.7** `.agents/skills/docs-sync/references/docker-source-guide.md` — Update `WEB_ADMIN_ENABLED` row description

## Phase 6: Verification

- [x] **6.1** Run `pytest tests/test_web/ -v` — 170 passed
- [x] **6.2** Run `pytest tests/test_api/ -v` — 164 passed
- [x] **6.3** Run `pytest` — 572 passed, 22 skipped (E2E)
- [x] **6.4** Run `pre-commit run --all-files` — all hooks passed

---

## File Change Summary

| # | File | Action | Phase(s) |
|---|------|--------|----------|
| 1 | `src/meshcore_hub/common/config.py` | Modify | 1 |
| 2 | `src/meshcore_hub/web/app.py` | Modify | 1 |
| 3 | `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` | Modify | 2 |
| 4 | `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` | Modify | 2 |
| 5 | `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` | Modify | 2 |
| 6 | `src/meshcore_hub/web/static/js/spa/pages/node-detail.js` | Modify | 2 |
| 7 | `src/meshcore_hub/web/static/js/spa/router.js` | Modify | 2 |
| 8 | `src/meshcore_hub/web/static/locales/en.json` | Modify | 3 |
| 9 | `src/meshcore_hub/web/static/locales/nl.json` | Modify | 3 |
| 10 | `tests/test_web/test_admin.py` | Modify | 4 |
| 11 | `tests/test_web/test_app.py` | Modify | 4 |
| 12 | `tests/test_web/test_home.py` | Modify | 4 |
| 13 | `tests/test_web/test_advertisements.py` | Modify | 4 |
| 14 | `docs/hosting/nginx-proxy-manager.md` | Delete | 5 |
| 15 | `README.md` | Modify | 5 |
| 16 | `AGENTS.md` | Modify | 5 |
| 17 | `.env.example` | Modify | 5 |
| 18 | `docs/i18n.md` | Modify | 5 |
| 19 | `.agents/skills/docs-sync/references/documentation-checklist.md` | Modify | 5 |
| 20 | `.agents/skills/docs-sync/references/docker-source-guide.md` | Modify | 5 |
