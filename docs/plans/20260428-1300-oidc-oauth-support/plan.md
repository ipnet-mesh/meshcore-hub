# OIDC/OAuth2 Authentication — Implementation Plan

**Date:** 2026-04-26
**Status:** Approved

## Overview

Add native OIDC/OAuth2 authentication to the web application using a standard Client ID / Client Secret pattern. Supports any OIDC-compliant identity provider (LogTo, Keycloak, etc.) via OIDC Discovery. No provider-specific libraries or integrations.

## Library

**Authlib** (`authlib>=1.3.0`) — chosen over alternatives:

| Library | Rejected because |
|---|---|
| `pyoidc` | Less maintained, no native FastAPI/Starlette integration |
| `oauthlib` | Low-level; requires manual OIDC layer (Authlib wraps it) |
| `mozilla-django-oidc` | Django-specific |

Authlib provides:

- First-class async Starlette/FastAPI integration (`authlib.integrations.starlette_client`)
- OIDC Discovery via `server_metadata_url` — auto-configures from any provider
- ID token parsing, PKCE, token lifecycle
- No provider-specific code required

## Decisions

1. **OIDC replaces `WEB_ADMIN_ENABLED`** — Single toggle, removed entirely (no deprecation period, alpha release).
2. **Two roles: `member` and `admin`** — Configurable claim name and role values.
3. **No local user model** — Users managed entirely by the IdP. MeshCore Hub is a pure OIDC relying party.
4. **Session via signed cookies** — Starlette `SessionMiddleware`, no Redis/DB sessions.
5. **API unchanged** — Continues using static Bearer tokens internally. Auth gating happens at the web proxy layer.
6. **OIDC-only (no plain OAuth2 fallback)** — Provider must support OIDC Discovery. Plain OAuth2 providers (e.g. GitHub OAuth directly) are not supported. Use an IdP like LogTo to wrap social providers.
7. **All write methods gated at proxy** — POST/PUT/DELETE/PATCH through the API proxy require admin session when OIDC enabled. Simpler and more secure than path-specific gating.
8. **IdP setup is out of scope** — Configuring LogTo, Keycloak, or any other IdP is handled separately.

## Terminology

| Term | Meaning |
|---|---|
| IdP | Identity Provider (LogTo, Keycloak, etc.) |
| Relying Party | MeshCore Hub (the OIDC client) |
| Discovery URL | IdP's `.well-known/openid-configuration` endpoint |
| ID token | JWT issued by IdP containing user claims |
| Roles claim | ID token field containing user role assignments |

## Role Model

| Role | Access | IDP Configuration |
|---|---|---|
| Anonymous | Read-only dashboard (nodes, messages, map, etc.) | N/A |
| Member | Same as anonymous + future member-only features (no routes yet) | IdP assigns `member` role to user |
| Admin | `/a/*` routes + all write API proxy requests | IdP assigns `admin` role to user |

Role assignment flow:

1. User signs in via IdP (first sign-in = registration, handled by IdP)
2. IdP issues ID token with configured roles claim
3. MeshCore Hub reads roles from ID token, grants access accordingly
4. To promote to admin: add `admin` role in IdP admin console
5. Role changes take effect on next login (session expiry = `OIDC_SESSION_MAX_AGE`)

## Environment Variables

### New Variables

| Variable | Description | Default |
|---|---|---|
| `OIDC_ENABLED` | Enable OIDC authentication | `false` |
| `OIDC_CLIENT_ID` | Client ID from IdP | (required if enabled) |
| `OIDC_CLIENT_SECRET` | Client secret from IdP | (required if enabled) |
| `OIDC_DISCOVERY_URL` | IdP's `.well-known/openid-configuration` URL | (required if enabled) |
| `OIDC_REDIRECT_URI` | Explicit callback URL (overrides auto-derivation) | (auto-derived from request) |
| `OIDC_SCOPES` | OAuth scopes to request | `openid email profile` |
| `OIDC_ROLES_CLAIM` | ID token claim name containing roles array | `roles` |
| `OIDC_ADMIN_ROLE` | Role value that grants admin access | `admin` |
| `OIDC_MEMBER_ROLE` | Role value that grants member access | `member` |
| `OIDC_SESSION_SECRET` | Secret for signing session cookies | (required if enabled) |
| `OIDC_SESSION_MAX_AGE` | Session cookie lifetime in seconds | `86400` (24 hours) |
| `OIDC_COOKIE_SECURE` | HTTPS-only session cookies | `false` |

### Removed Variables

| Variable | Reason |
|---|---|
| `WEB_ADMIN_ENABLED` | Replaced by `OIDC_ENABLED` |

## Architecture

### Auth Flow

```
Browser                      Web App (:8080)                  OIDC Provider (IdP)
  |                               |                               |
  | GET /a/node-tags              |                               |
  |------------------------------>|                               |
  |                               | No session                    |
  | 302 /auth/login?next=/a/node-tags                              |
  |<------------------------------|                               |
  |                               |                               |
  | GET /auth/login               |                               |
  |------------------------------>|                               |
  |                               | Build auth URL + state        |
  | 302 → IdP authorize endpoint  |                               |
  |<------------------------------|                               |
  |                               |                               |
  | User authenticates at IdP     |                               |
  |------------------------------>|                               |
  |                               |                               |
  | GET /auth/callback?code=...&state=...                           |
  |------------------------------>|                               |
  |                               | Exchange code for tokens      |
  |                               |------------------------------>|
  |                               |     ID token + access token   |
  |                               |<------------------------------|
  |                               | Extract userinfo + roles      |
  |                               | Set session cookie            |
  | 302 → /a/node-tags            |                               |
  |<------------------------------|                               |
  |                               |                               |
  | GET /a/node-tags              |                               |
  |------------------------------>|                               |
  |                               | Session valid, role=admin     |
  |                               | Proxy to API with api_key     |
  | 200 HTML                      |                               |
  |<------------------------------|                               |
```

### Security Model

```
                         ┌─────────────────────────┐
                         │    Web App (:8080)       │
                         │    Exposed to internet   │
                         │                         │
  Browser ──────────────►│  Session cookie auth     │
                         │  Role-based gating on    │
                         │  admin routes + writes   │
                         │                         │
                         │  httpx + Bearer api_key  │
                         └──────────┬──────────────┘
                                    │ (internal network only)
                         ┌──────────▼──────────────┐
                         │    API (:8000)           │
                         │    Bound to 127.0.0.1   │
                         │                         │
                         │  Bearer token auth       │
                         │  (RequireRead /          │
                         │   RequireAdmin)          │
                         └─────────────────────────┘
```

- Web app is the only public surface
- API bound to localhost / internal Docker network — only reachable via proxy
- Browser never sees the `API_KEY`
- Session data stored in signed cookie (no server-side state)

### Navbar Auth UI

Location: `navbar-end` section, to the left of the theme toggle. Only visible when `OIDC_ENABLED=true`.

**Not logged in:**

```
┌─────────────────────────────────────────────┬──────────┬─────────┐
│  ... nav links ...                          │ [Login]  │ 🌙/☀️   │
└─────────────────────────────────────────────┴──────────┴─────────┘
```

**Logged in (admin):**

```
┌─────────────────────────────────────────────┬────────┬──────────┐
│  ... nav links ...                          │ [JD ▼] │ 🌙/☀️    │
└─────────────────────────────────────────────┴────────┴──────────┘
                                              │ John Doe (admin)  │
                                              │ ─────────────────│
                                              │ Admin             │
                                              │ Logout            │
                                              └───────────────────┘
```

**Logged in (member):**

```
┌─────────────────────────────────────────────┬────────┬──────────┐
│  ... nav links ...                          │ [JD ▼] │ 🌙/☀️    │
└─────────────────────────────────────────────┴────────┴──────────┘
                                              │ John Doe          │
                                              │ ─────────────────│
                                              │ Logout            │
                                              └───────────────────┘
```

- Avatar: `user.picture` from OIDC, fallback to initials
- Role badge: `admin` = `badge-primary`, `member` = `badge-ghost`
- Dropdown: DaisyUI `dropdown` component
- Implementation: Server-side placeholder in `spa.html`, populated by `components.js` using lit-html from `config.user`

## Implementation

### File Changes

| File | Change |
|---|---|
| `pyproject.toml` | Add `authlib>=1.3.0`, update mypy overrides |
| `common/config.py` | Add OIDC settings, remove `web_admin_enabled` |
| `web/oidc.py` | **New** — OIDC client init, role extraction, session helpers |
| `web/app.py` | Session middleware, auth routes, proxy write gating, config injection, remove `admin_enabled` |
| `web/cli.py` | Remove `admin_enabled` opts, add OIDC status display |
| `web/templates/spa.html` | Auth UI placeholder in navbar, remove `admin_enabled` conditionals |
| `web/static/js/spa/app.js` | Auth-aware routing |
| `web/static/js/spa/api.js` | 401 response interceptor → redirect to login |
| `web/static/js/spa/components.js` | Auth UI components (login button, user dropdown) |
| `web/static/js/spa/pages/admin/index.js` | Remove `admin_enabled` check |
| `web/static/locales/en.json` | Auth translation keys |
| `tests/test_web/conftest.py` | Replace `admin_enabled` fixtures with OIDC fixtures |
| `tests/test_web/test_admin.py` | Update for OIDC auth |
| `tests/test_web/test_oidc.py` | **New** — OIDC auth tests |
| `.env.example` | Remove `WEB_ADMIN_ENABLED`, add OIDC section |
| `README.md` | OIDC env vars, remove `WEB_ADMIN_ENABLED` |
| `docs/upgrading.md` | Migration from `WEB_ADMIN_ENABLED` |
| `AGENTS.md` | Updated env vars table, OIDC testing notes |

### Phase 1: Dependencies & Configuration

#### 1.1 `pyproject.toml`

- Add `authlib>=1.3.0` to `dependencies`
- Add `authlib.*` to mypy `ignore_missing_imports`

#### 1.2 `common/config.py`

Add to `WebSettings`:

```python
oidc_enabled: bool = Field(default=False, description="Enable OIDC authentication")
oidc_client_id: Optional[str] = Field(default=None, description="OIDC client ID")
oidc_client_secret: Optional[str] = Field(default=None, description="OIDC client secret")
oidc_discovery_url: Optional[str] = Field(default=None, description="OIDC discovery URL")
oidc_redirect_uri: Optional[str] = Field(default=None, description="OIDC callback URL (overrides auto-derivation)")
oidc_scopes: str = Field(default="openid email profile", description="OAuth scopes to request")
oidc_roles_claim: str = Field(default="roles", description="ID token claim containing user roles")
oidc_admin_role: str = Field(default="admin", description="Role value granting admin access")
oidc_member_role: str = Field(default="member", description="Role value granting member access")
oidc_session_secret: Optional[str] = Field(default=None, description="Secret key for signing session cookies")
oidc_session_max_age: int = Field(default=86400, description="Session cookie lifetime in seconds")
oidc_cookie_secure: bool = Field(default=False, description="HTTPS-only session cookies (enable in production)")
```

Remove `web_admin_enabled` from `WebSettings`.

### Phase 2: OIDC Module

#### 2.1 `web/oidc.py` (new)

```python
"""OIDC/OAuth2 authentication using Authlib."""

import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request

logger = logging.getLogger(__name__)

oauth = OAuth()


def init_oidc(client_id: str, client_secret: str, discovery_url: str, scopes: str) -> None:
    """Register the OIDC client on the OAuth registry."""
    oauth.register(
        name="oidc",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=discovery_url,
        client_kwargs={"scope": scopes},
    )


async def validate_discovery() -> bool:
    """Eagerly validate OIDC discovery endpoint is reachable."""
    try:
        await oauth.oidc.load_server_metadata()
        return True
    except Exception as e:
        logger.error("OIDC discovery failed: %s", e)
        return False


def get_session_user(request: Request) -> dict[str, Any] | None:
    """Get current user from session, or None."""
    return request.session.get("user")


def get_user_roles(request: Request, roles_claim: str, admin_role: str, member_role: str) -> tuple[bool, bool]:
    """Extract roles from session. Returns (is_member, is_admin)."""
    user = get_session_user(request)
    if not user:
        return False, False
    roles = user.get(roles_claim, [])
    if isinstance(roles, str):
        roles = [roles]
    is_admin = admin_role in roles
    is_member = member_role in roles
    return is_member, is_admin


def strip_userinfo(userinfo: dict[str, Any], roles_claim: str) -> dict[str, Any]:
    """Strip userinfo to essential fields for session storage."""
    return {
        "sub": userinfo.get("sub"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "picture": userinfo.get("picture"),
        roles_claim: userinfo.get(roles_claim, []),
    }
```

### Phase 3: Web App Changes

#### 3.1 `web/app.py` — Session middleware

In `create_app()`, add after `CacheControlMiddleware`:

```python
if settings.oidc_enabled:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.oidc_session_secret,
        session_cookie="meshcore-session",
        max_age=settings.oidc_session_max_age,
        same_site="lax",
        https_only=settings.oidc_cookie_secure,
    )
```

#### 3.2 `web/app.py` — Auth routes

Four endpoints, registered before the SPA catch-all:

| Route | Method | Purpose |
|---|---|---|
| `/auth/login` | GET | Initiate OIDC flow, store `next` URL in session |
| `/auth/callback` | GET | Exchange code for tokens, store stripped userinfo in session |
| `/auth/logout` | GET | Clear session, redirect to IdP end_session_endpoint |
| `/auth/user` | GET | Return current user + roles as JSON |

#### 3.3 `web/app.py` — Proxy write gating

In `api_proxy`, gate all write methods:

```python
if request.app.state.oidc_enabled and request.method in ("POST", "PUT", "DELETE", "PATCH"):
    _, is_admin = get_user_roles(request, ...)
    if not is_admin:
        return JSONResponse({"detail": "Admin access required", "code": "AUTH_REQUIRED"}, status_code=403)
```

#### 3.4 `web/app.py` — SPA catch-all admin protection

At top of `spa_catchall`, for `/a` paths when OIDC enabled:

- No session → 302 to `/auth/login?next=/{path}`
- Session but not admin → serve SPA shell (client-side shows access denied)

#### 3.5 `web/app.py` — SPA config injection

Update `_build_config_json()`:

```python
if request.app.state.oidc_enabled:
    user = get_session_user(request)
    is_member, is_admin = get_user_roles(request, ...)
    config.update(oidc_enabled=True, user=user, is_member=is_member, is_admin=is_admin)
else:
    config.update(oidc_enabled=False, user=None, is_member=False, is_admin=False)
```

Remove `admin_enabled` from config dict.

#### 3.6 `web/app.py` — Remove `admin_enabled`

- Remove from `create_app()` parameters and `app.state`
- Remove from template context in `spa_catchall`

#### 3.7 `web/app.py` — Eager OIDC discovery validation

In `lifespan()`, after HTTP client creation:

```python
if getattr(app.state, "oidc_enabled", False):
    ok = await validate_discovery()
    if not ok:
        logger.warning("OIDC discovery failed — login will not work until IdP is reachable")
```

### Phase 4: CLI

#### 4.1 `web/cli.py`

- Remove `--admin-enabled` option
- Add OIDC status to startup banner

### Phase 5: Frontend

#### 5.1 `web/templates/spa.html`

Add auth placeholder in `navbar-end` before theme toggle:

```html
{% if oidc_enabled %}
<div id="auth-section"></div>
{% endif %}
```

Remove `{% if admin_enabled %}` conditionals from footer.

#### 5.2 `web/static/js/spa/components.js`

Add `renderAuthSection(container, config)` — renders login button or user dropdown based on `config.user`.

#### 5.3 `web/static/js/spa/app.js`

- Call `renderAuthSection()` after config load
- Check `config.is_admin` for admin routes
- Remove dependency on `config.admin_enabled`

#### 5.4 `web/static/js/spa/api.js`

Add 401 interceptor — detect `401` responses and redirect to `/auth/login`.

#### 5.5 `web/static/js/spa/pages/admin/index.js`

Remove `config.admin_enabled` check.

### Phase 6: i18n

#### 6.1 `web/static/locales/en.json`

```json
{
  "auth": {
    "login": "Login",
    "logout": "Logout",
    "login_required": "Login required",
    "admin_required": "Admin access required",
    "login_hint": "Log in to access admin features",
    "logged_in_as": "Logged in as {{name}}",
    "session_expired": "Session expired, please log in again",
    "role_admin": "admin",
    "role_member": "member"
  }
}
```

### Phase 7: Tests

#### 7.1 `tests/test_web/conftest.py`

- Replace all `admin_enabled` parameters with `oidc_enabled`
- Add OIDC fixtures: `web_app_with_oidc`, `client_with_oidc_admin_session`, `client_with_oidc_member_session`, `client_with_oidc_no_session`

#### 7.2 `tests/test_web/test_oidc.py` (new)

- OIDC settings validation
- `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/user` tests
- Admin route protection (302 / 403 / 200)
- API proxy write gating
- Backward compatibility (OIDC disabled = current behavior)

#### 7.3 `tests/test_web/test_admin.py`

Update all tests for OIDC fixtures.

### Phase 8: Documentation

- `.env.example` — Remove `WEB_ADMIN_ENABLED`, add OIDC section with all 12 env vars
- `README.md` — OIDC env vars, remove `WEB_ADMIN_ENABLED`
- `docs/upgrading.md` — migration from `WEB_ADMIN_ENABLED`
- `AGENTS.md` — updated env vars table, OIDC testing notes

## Reverse Proxy Configuration (Traefik)

### 1. Forwarded Headers

Traefik automatically sends `X-Forwarded-For`, `X-Forwarded-Host`, and `X-Forwarded-Proto` headers. For `OIDC_REDIRECT_URI` auto-derivation to produce `https://` URLs, forwarded headers must be trusted.

**Recommended**: Set `OIDC_REDIRECT_URI` explicitly to avoid relying on header forwarding:

```yaml
environment:
  OIDC_REDIRECT_URI: "https://hub.example.com/auth/callback"
```

### 2. Traefik Labels

The auth callback route must be accessible without authentication. Since Traefik routes all traffic to the web app and auth gating is handled in application code, no special Traefik routing rules are needed.

```yaml
labels:
  - "traefik.http.routers.hub.rule=Host(`hub.example.com`)"
  - "traefik.http.services.hub.loadbalancer.server.port=8080"
```

### 3. Cookie Secure Flag

When behind Traefik with TLS termination:

```yaml
environment:
  OIDC_COOKIE_SECURE: "true"
```

### 4. CORS / SameSite

Session cookies use `SameSite=Lax` which is correct for the OIDC redirect flow:

- IdP redirect to `/auth/callback` is a top-level navigation → `SameSite=Lax` cookies are sent
- API calls from SPA are same-origin → cookies always sent
- Cross-origin cookie injection prevented by `SameSite=Lax`

### 5. Docker Compose Example

```yaml
services:
  web:
    build: .
    command: meshcore-hub web
    environment:
      # ... existing vars ...
      OIDC_ENABLED: "true"
      OIDC_CLIENT_ID: "${OIDC_CLIENT_ID}"
      OIDC_CLIENT_SECRET: "${OIDC_CLIENT_SECRET}"
      OIDC_DISCOVERY_URL: "https://auth.example.com/oidc/.well-known/openid-configuration"
      OIDC_REDIRECT_URI: "https://hub.example.com/auth/callback"
      OIDC_SESSION_SECRET: "${OIDC_SESSION_SECRET}"
      OIDC_COOKIE_SECURE: "true"
    labels:
      - "traefik.http.routers.hub.rule=Host(`hub.example.com`)"
      - "traefik.http.routers.hub.tls=true"
      - "traefik.http.routers.hub.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub.loadbalancer.server.port=8080"
    networks:
      - internal
      - traefik

  api:
    build: .
    command: meshcore-hub api
    environment:
      API_HOST: "0.0.0.0"
      API_PORT: "8000"
      API_ADMIN_KEY: "${API_ADMIN_KEY}"
    networks:
      - internal

networks:
  internal:
    internal: true
  traefik:
    external: true
```

## Known Limitations

1. **Role changes are not instant** — Take effect on next login (up to `OIDC_SESSION_MAX_AGE` seconds).
2. **OIDC-only** — No support for plain OAuth2 providers. Use an IdP like LogTo to wrap social providers.
3. **No token refresh** — Sessions are fixed-lifetime. Token refresh can be added later.
4. **IdP availability** — If the IdP is down, users cannot log in. Anonymous access still works. Existing sessions continue until expiry.
5. **No local user store** — No user list or audit trail. Can be added later.

## Execution Order

1. `pyproject.toml` + `common/config.py`
2. `web/oidc.py`
3. `web/app.py`
4. `web/cli.py`
5. `web/templates/spa.html` + `web/static/js/spa/` (frontend)
6. `web/static/locales/en.json` (i18n)
7. `tests/test_web/` (tests)
8. Documentation (`.env.example`, README, upgrading, AGENTS.md)
9. `pre-commit run --all-files` + `pytest tests/test_web/`
