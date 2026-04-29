# OIDC Authentication

MeshCore Hub supports OpenID Connect (OIDC) for authenticating web dashboard users. When enabled, the admin interface (`/admin/`) requires an authenticated session with the `admin` role.

When OIDC is **disabled** (the default), no admin functionality is exposed — the admin link is hidden from the navbar and admin routes are not registered.

## Architecture

OIDC is implemented entirely in the web dashboard layer. The REST API uses static Bearer token authentication independently of OIDC. The web dashboard proxies API requests and gates write operations (POST, PUT, DELETE, PATCH) by checking the user's session role.

```
Browser → Web Dashboard (OIDC session + API proxy) → REST API (Bearer token)
```

## Login Flow

1. User visits `/admin/` — no session exists — server redirects to `/auth/login?next=/admin/`
2. `/auth/login` stores the `next` URL in the session and redirects to the IdP
3. User authenticates at the IdP, which redirects back to `/auth/callback?code=...`
4. `/auth/callback` exchanges the authorization code for tokens, extracts userinfo and roles, stores them in a session cookie, and redirects to the `next` URL
5. The SPA receives `window.__APP_CONFIG__` with `oidc_enabled`, `user`, `is_member`, and `is_admin` flags
6. Admin routes are registered client-side only when `is_admin` is `true`
7. Write operations through the API proxy are blocked for non-admin sessions (HTTP 403)
8. Logout (`/auth/logout`) clears the session and redirects to the IdP's end-session endpoint

## Configuration

All OIDC settings are environment variables. Set `OIDC_ENABLED=true` to activate.

| Variable | Default | Description |
|----------|---------|-------------|
| `OIDC_ENABLED` | `false` | Enable OIDC authentication |
| `OIDC_CLIENT_ID` | _(none)_ | OAuth2 client ID from your IdP |
| `OIDC_CLIENT_SECRET` | _(none)_ | OAuth2 client secret from your IdP |
| `OIDC_DISCOVERY_URL` | _(none)_ | IdP base URL — `.well-known/openid-configuration` is appended automatically (e.g. `https://auth.example.com/oidc`) |
| `OIDC_REDIRECT_URI` | _(auto)_ | Override callback URL (auto-derived from request if not set) |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | _(auto)_ | Post-logout redirect URI (falls back to `OIDC_REDIRECT_URI` base or request URL) |
| `OIDC_SCOPES` | `openid email profile` | OAuth scopes to request. The `openid` scope is required. Quotes are stripped automatically. |
| `OIDC_ROLES_CLAIM` | `roles` | ID token claim name containing user roles |
| `OIDC_ADMIN_ROLE` | `admin` | Role value that grants admin access |
| `OIDC_MEMBER_ROLE` | `member` | Role value that grants member access |
| `OIDC_SESSION_SECRET` | _(none)_ | Secret for signing session cookies (generate with `openssl rand -hex 32`) |
| `OIDC_SESSION_MAX_AGE` | `86400` | Session cookie lifetime in seconds (default: 24 hours) |
| `OIDC_COOKIE_SECURE` | `false` | Set to `true` to require HTTPS for session cookies |

## Local Development (No HTTPS)

To test OIDC locally without TLS:

- Set `OIDC_REDIRECT_URI=http://localhost:8080/auth/callback` explicitly — auto-derivation may produce an incorrect URL depending on your setup
- Keep `OIDC_COOKIE_SECURE=false` (the default) — cookies won't be restricted to HTTPS
- Register `http://localhost:8080/auth/callback` as a redirect URI in your IdP
- Register `http://localhost:8080/` as a post-logout redirect URI in your IdP
- `OIDC_SESSION_SECRET` is still required — generate one even for local testing

## IdP Provider Guides

### LogTo

[LogTo](https://logto.io/) is an open-source identity provider that works well with MeshCore Hub.

**Setup:**

1. Create a new **Traditional Web** application in LogTo
2. Set the redirect URI to `https://your-hub-domain/auth/callback`
3. Set the post-logout redirect URI to `https://your-hub-domain/`
4. Copy the client ID and client secret into `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`
5. Set `OIDC_DISCOVERY_URL` to your LogTo endpoint (e.g. `https://auth.example.com/oidc`)

**Required scope changes:**

LogTo returns roles via the `roles` claim in the ID token. You must include `roles` in the scopes:

```bash
OIDC_SCOPES="openid email profile roles"
```

`OIDC_ROLES_CLAIM` defaults to `roles`, which matches LogTo's claim name — no change needed.

**Role assignment:**

Create `admin` and/or `member` roles in LogTo and assign them to users. The role names must match `OIDC_ADMIN_ROLE` and `OIDC_MEMBER_ROLE` (both default to `admin` and `member` respectively).
