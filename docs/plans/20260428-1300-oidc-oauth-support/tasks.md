# OIDC/OAuth2 Authentication — Task Checklist

**Plan:** `docs/plans/20260428-1300-oidc-oauth-support/plan.md`
**Status:** In Progress

---

## Phase 1: Dependencies & Configuration

- [ ] **1.1** `pyproject.toml` — Add `authlib>=1.3.0` to `dependencies` list (after `httpx>=0.25.0`)
- [ ] **1.2** `pyproject.toml` — Add `"authlib.*"` to mypy `ignore_missing_imports` overrides module list (line 114-122)
- [ ] **1.3** `src/meshcore_hub/common/config.py` — Remove `web_admin_enabled` field from `WebSettings` (lines 283-287)
- [ ] **1.4** `src/meshcore_hub/common/config.py` — Add OIDC settings block to `WebSettings` after `api_key` field (after line 294): `oidc_enabled`, `oidc_client_id`, `oidc_client_secret`, `oidc_discovery_url`, `oidc_redirect_uri`, `oidc_scopes`, `oidc_roles_claim`, `oidc_admin_role`, `oidc_member_role`, `oidc_session_secret`, `oidc_session_max_age`, `oidc_cookie_secure`

## Phase 2: OIDC Module

- [ ] **2.1** Create `src/meshcore_hub/web/oidc.py` — New file with `OAuth` registry, `init_oidc()`, `validate_discovery()`, `get_session_user()`, `get_user_roles()`, `strip_userinfo()` functions per plan Phase 2.1

## Phase 3: Web App Changes

- [ ] **3.1** `src/meshcore_hub/web/app.py` — Add `SessionMiddleware` import (from `starlette.middleware.sessions`)
- [ ] **3.2** `src/meshcore_hub/web/app.py` — In `create_app()`: remove `admin_enabled` parameter (line 181), remove `effective_admin` computation (lines 231-233), remove `app.state.admin_enabled = effective_admin` (line 253)
- [ ] **3.3** `src/meshcore_hub/web/app.py` — In `create_app()`: add OIDC state initialization — set `app.state.oidc_enabled` from settings, conditionally add `SessionMiddleware`, call `init_oidc()` when enabled
- [ ] **3.4** `src/meshcore_hub/web/app.py` — In `lifespan()`: add eager OIDC discovery validation after HTTP client creation (after line 94)
- [ ] **3.5** `src/meshcore_hub/web/app.py` — In `_build_config_json()`: replace `"admin_enabled"` key (line 156) with `oidc_enabled`, `user`, `is_member`, `is_admin` based on OIDC state and session
- [ ] **3.6** `src/meshcore_hub/web/app.py` — Add four auth route endpoints before SPA catch-all: `/auth/login` (GET), `/auth/callback` (GET), `/auth/logout` (GET), `/auth/user` (GET)
- [ ] **3.7** `src/meshcore_hub/web/app.py` — In `api_proxy()`: add OIDC write gating — block POST/PUT/DELETE/PATCH for non-admin sessions when `oidc_enabled` (after line 346)
- [ ] **3.8** `src/meshcore_hub/web/app.py` — In `spa_catchall()`: replace `admin_enabled` template context (line 684) with `oidc_enabled`; add admin route protection (302 redirect to `/auth/login` for `/a` paths when OIDC enabled and no session)
- [ ] **3.9** `src/meshcore_hub/web/app.py` — Update `create_app()` docstring to remove `admin_enabled` param and add OIDC notes

## Phase 4: CLI

- [ ] **4.1** `src/meshcore_hub/web/cli.py` — Remove `admin_enabled` usage from `create_app()` call in production path (line 207-219)
- [ ] **4.2** `src/meshcore_hub/web/cli.py` — Add OIDC status line to startup banner (after line 185): show `OIDC: enabled` or `OIDC: disabled`

## Phase 5: Frontend — Templates & Components

- [ ] **5.1** `src/meshcore_hub/web/templates/spa.html` — Replace `{% if admin_enabled %}` conditional in footer (line 169) with `{% if oidc_enabled %}`; admin link requires `is_admin` session check
- [ ] **5.2** `src/meshcore_hub/web/templates/spa.html` — Add `<div id="auth-section"></div>` placeholder in `navbar-end` before the loading spinner (before line 128), wrapped in `{% if oidc_enabled %}`
- [ ] **5.3** `src/meshcore_hub/web/static/js/spa/components.js` — Add `renderAuthSection(container, config)` function: renders login button or user dropdown based on `config.user`
- [ ] **5.4** `src/meshcore_hub/web/static/js/spa/app.js` — Call `renderAuthSection()` after config load (after line 34)
- [ ] **5.5** `src/meshcore_hub/web/static/js/spa/app.js` — Replace `config.admin_enabled` checks with `config.is_admin` for admin route gating (lines 91-94); remove admin routes registration when OIDC is enabled and user is not admin
- [ ] **5.6** `src/meshcore_hub/web/static/js/spa/api.js` — Add 401/403 response interceptor to `apiPost`, `apiPut`, `apiDelete`: detect auth errors and redirect to `/auth/login`
- [ ] **5.7** `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` — Replace `!config.admin_enabled` check (line 8) with `!config.is_admin` when `config.oidc_enabled`, show login redirect instead of enable hint
- [ ] **5.8** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Replace `!config.admin_enabled` check (line 13) with `!config.is_admin` when `config.oidc_enabled`
- [ ] **5.9** `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` — Replace `!config.admin_enabled` check (line 12) with `!config.is_admin` when `config.oidc_enabled`
- [ ] **5.10** `src/meshcore_hub/web/static/js/spa/pages/node-detail.js` — Replace `config.admin_enabled` check (line 129) with `config.is_admin` when `config.oidc_enabled`

## Phase 6: i18n

- [ ] **6.1** `src/meshcore_hub/web/static/locales/en.json` — Add `auth` section with keys: `login`, `logout`, `login_required`, `admin_required`, `login_hint`, `logged_in_as`, `session_expired`, `role_admin`, `role_member`
- [ ] **6.2** `src/meshcore_hub/web/static/locales/en.json` — Update `admin.admin_not_enabled` and `admin.admin_enable_hint` to reflect OIDC flow instead of `WEB_ADMIN_ENABLED`
- [ ] **6.3** `docs/i18n.md` — Document new `auth.*` translation keys and updated `admin.*` keys

## Phase 7: Tests

- [ ] **7.1** `tests/test_web/conftest.py` — Replace `admin_enabled=True/False` params in `web_app` and test fixtures with OIDC-aware equivalents
- [ ] **7.2** `tests/test_web/conftest.py` — Add OIDC test fixtures: `web_app_with_oidc`, `client_with_oidc_admin_session`, `client_with_oidc_member_session`, `client_with_oidc_no_session`
- [ ] **7.3** Create `tests/test_web/test_oidc.py` — Test OIDC settings validation (missing required fields when enabled)
- [ ] **7.4** `tests/test_web/test_oidc.py` — Test `/auth/login` redirects to IdP with correct parameters and stores `next` URL in session
- [ ] **7.5** `tests/test_web/test_oidc.py` — Test `/auth/callback` exchanges code, stores stripped userinfo in session, redirects to `next` URL
- [ ] **7.6** `tests/test_web/test_oidc.py` — Test `/auth/logout` clears session and redirects to IdP end_session_endpoint
- [ ] **7.7** `tests/test_web/test_oidc.py` — Test `/auth/user` returns current user JSON or 401 when not logged in
- [ ] **7.8** `tests/test_web/test_oidc.py` — Test admin route protection: no session → 302, member session → SPA shell (client-denied), admin session → 200
- [ ] **7.9** `tests/test_web/test_oidc.py` — Test API proxy write gating: non-admin session → 403, admin session → proxied
- [ ] **7.10** `tests/test_web/test_oidc.py` — Test backward compatibility: OIDC disabled = current behavior (admin_enabled controls admin UI)
- [ ] **7.11** `tests/test_web/test_oidc.py` — Test config injection: `oidc_enabled`, `user`, `is_member`, `is_admin` values in SPA config
- [ ] **7.12** `tests/test_web/test_admin.py` — Replace `admin_enabled=True/False` fixture params (lines 25, 44) with OIDC fixtures
- [ ] **7.13** `tests/test_web/test_admin.py` — Update `test_admin_home_config_admin_enabled` (line 82) to check OIDC config keys instead
- [ ] **7.14** `tests/test_web/test_admin.py` — Update `TestAdminFooterLink` tests (lines 135-149) for OIDC-aware admin link visibility
- [ ] **7.15** Run targeted tests: `pytest tests/test_web/ -v`
- [ ] **7.16** Run quality checks: `pre-commit run --all-files`

## Phase 8: Documentation

- [ ] **8.1** `.env.example` — Remove `WEB_ADMIN_ENABLED` section (lines 338-340); add OIDC section with all 12 environment variables
- [ ] **8.2** `README.md` — Remove `WEB_ADMIN_ENABLED` row from env vars table (line 372); add OIDC env vars rows
- [ ] **8.3** `docs/upgrading.md` — Add new version section documenting migration from `WEB_ADMIN_ENABLED` to `OIDC_ENABLED`
- [ ] **8.4** `AGENTS.md` — Remove `WEB_ADMIN_ENABLED` from env vars table (line 640); add OIDC env vars; update admin UI notes (line 693)
- [ ] **8.5** `docs/i18n.md` — Update `admin_enable_hint` description to reference OIDC instead of `WEB_ADMIN_ENABLED` (line 342)
- [ ] **8.6** `.agents/skills/docs-sync/references/docker-source-guide.md` — Replace `WEB_ADMIN_ENABLED` row (line 196) with OIDC env vars

---

## File Change Summary

| # | File | Action | Phase(s) |
|---|------|--------|----------|
| 1 | `pyproject.toml` | Modify | 1 |
| 2 | `src/meshcore_hub/common/config.py` | Modify | 1 |
| 3 | `src/meshcore_hub/web/oidc.py` | Create | 2 |
| 4 | `src/meshcore_hub/web/app.py` | Modify | 3 |
| 5 | `src/meshcore_hub/web/cli.py` | Modify | 4 |
| 6 | `src/meshcore_hub/web/templates/spa.html` | Modify | 5 |
| 7 | `src/meshcore_hub/web/static/js/spa/components.js` | Modify | 5 |
| 8 | `src/meshcore_hub/web/static/js/spa/app.js` | Modify | 5 |
| 9 | `src/meshcore_hub/web/static/js/spa/api.js` | Modify | 5 |
| 10 | `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` | Modify | 5 |
| 11 | `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` | Modify | 5 |
| 12 | `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` | Modify | 5 |
| 13 | `src/meshcore_hub/web/static/js/spa/pages/node-detail.js` | Modify | 5 |
| 14 | `src/meshcore_hub/web/static/locales/en.json` | Modify | 6 |
| 15 | `docs/i18n.md` | Modify | 6, 8 |
| 16 | `tests/test_web/conftest.py` | Modify | 7 |
| 17 | `tests/test_web/test_oidc.py` | Create | 7 |
| 18 | `tests/test_web/test_admin.py` | Modify | 7 |
| 19 | `.env.example` | Modify | 8 |
| 20 | `README.md` | Modify | 8 |
| 21 | `docs/upgrading.md` | Modify | 8 |
| 22 | `AGENTS.md` | Modify | 8 |
| 23 | `.agents/skills/docs-sync/references/docker-source-guide.md` | Modify | 8 |
