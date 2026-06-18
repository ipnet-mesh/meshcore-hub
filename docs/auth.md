# OIDC Authentication

MeshCore Hub supports OpenID Connect (OIDC) for authenticating web dashboard users. When enabled, the web dashboard uses role-based access control to gate API endpoints through the proxy layer.

When OIDC is **disabled** (the default), the web proxy only allows read (GET) access to API endpoints. Write operations (POST/PUT/DELETE) and unknown endpoints are blocked. Admin operations must be performed via the CLI or direct API access with Bearer tokens.

## Architecture

OIDC is implemented entirely in the web dashboard layer. The REST API uses static Bearer token authentication independently of OIDC. The web dashboard proxies API requests and gates access using a per-endpoint, per-method role mapping (`ENDPOINT_ACCESS` in `web/app.py`).

```
Browser → Web Dashboard (OIDC session + API proxy) → REST API (Bearer token)
```

### Role-Based Access

User roles are read from the OIDC token's `roles` claim (configurable via `OIDC_ROLES_CLAIM`). The web proxy checks these roles against the `ENDPOINT_ACCESS` mapping to determine which API endpoints and HTTP methods each user can access.

**Defined roles:**

| Role | Config Variable | Default | Description |
|------|----------------|---------|-------------|
| Admin | `OIDC_ROLE_ADMIN` | `admin` | Full write access to all API endpoints through the proxy |
| Operator | `OIDC_ROLE_OPERATOR` | `operator` | Reserved for future use — no endpoint assignments yet |
| Member | `OIDC_ROLE_MEMBER` | `member` | Read-only access (no endpoint assignments) |

The role names are configurable to match your IdP's role naming convention. For example, if your IdP uses `superuser` instead of `admin`, set `OIDC_ROLE_ADMIN=superuser`.

Additional roles can be added to the `ENDPOINT_ACCESS` mapping in `src/meshcore_hub/web/app.py` and the corresponding `OIDC_ROLE_*` config variable.

### Endpoint Access Mapping

The proxy uses a hardcoded per-endpoint, per-method mapping in `src/meshcore_hub/web/app.py`:

| Path prefix | Method | Access |
|-------------|--------|--------|
| `v1/nodes` | GET | Open |
| `v1/nodes/` | GET | Open |
| `v1/nodes/` | POST, PUT, DELETE | `admin` |
| `v1/members` | GET | Open |
| `v1/members` | POST, PUT, DELETE | `admin` |
| `v1/messages` | GET | Open |
| `v1/advertisements` | GET | Open |
| `v1/dashboard` | GET | Open |
| `v1/trace-paths` | GET | Open |
| `v1/telemetry` | GET | Open |

- **Open** = no authentication required (anonymous OK, works with or without OIDC)
- **`admin`** = requires OIDC enabled + user has the `admin` role
- Method not listed for a matched prefix = denied
- No prefix match = denied

### Client-Side Role Checks

The SPA receives the user's roles array in `window.__APP_CONFIG__.roles`. Client-side pages use the `hasRole(roleName)` helper, which returns `true` when OIDC is disabled (open access) or when the user has the specified role.

## Login Flow

1. User visits `/admin/` — no session exists — server redirects to `/auth/login?next=/admin/`
2. `/auth/login` stores the `next` URL in the session and redirects to the IdP
3. User authenticates at the IdP, which redirects back to `/auth/callback?code=...`
4. `/auth/callback` exchanges the authorization code for tokens, extracts userinfo and roles, stores them in a session cookie, and redirects to the `next` URL
5. The SPA receives `window.__APP_CONFIG__` with `oidc_enabled`, `user`, and `roles` flags
6. Admin routes are registered client-side only when `hasRole('admin')` is `true`
7. Write operations through the API proxy are checked against the `ENDPOINT_ACCESS` mapping
8. Logout (`/auth/logout`) clears the session and redirects to the IdP's end-session endpoint

## Configuration

All OIDC settings are environment variables. Set `OIDC_ENABLED=true` to activate. For the full variable reference (`OIDC_CLIENT_ID`, `OIDC_SCOPES`, `OIDC_ROLE_*`, `OIDC_SESSION_*`, etc.), see [configuration.md → Auth](configuration.md#auth).

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

Create an `admin` role in LogTo and assign it to users who should have write access through the web dashboard. The role name must match `OIDC_ROLE_ADMIN` (default: `admin`). If your LogTo setup uses a different role name, set `OIDC_ROLE_ADMIN` accordingly.
