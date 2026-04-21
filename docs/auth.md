# Authorization

MeshCore Hub supports optional authentication for the admin interface using a self-hosted [Logto](https://logto.io/) OIDC provider. When enabled, users must log in to access admin pages (`/a/*`). Public pages (home, nodes, map, messages, etc.) remain accessible without authentication.

The API uses independent bearer token authentication (`API_READ_KEY` / `API_ADMIN_KEY`) and is not affected by Logto.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser                                                      │
│    │                                                          │
│    ├── Public pages ────────────────── no auth required       │
│    └── Admin pages (/a/*) ──────────── Logto login required   │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Web Service (FastAPI)                                        │
│    ├── /auth/login     → redirect to Logto OIDC              │
│    ├── /auth/callback  → exchange code, set session cookie   │
│    ├── /auth/logout    → clear session, redirect to Logto    │
│    ├── LOGTO_APP_ID not set → auth disabled (default)        │
│    └── LOGTO_APP_ID set → auth enabled, admin UI visible     │
│                                                               │
│    API proxy (web → api) uses server-side API_KEY             │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Logto (OIDC Provider)  ←── docker compose --profile auth   │
│    ├── Port 3001 — OIDC endpoint (sign-in, tokens)           │
│    └── Port 3002 — Admin Console (app setup, user mgmt)      │
└──────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker Compose with the `auth` profile enabled
- A reverse proxy in production (to expose Logto with TLS)

## Quick Start

### 1. Start the stack with the auth profile

Add `--profile auth` to your usual docker compose command:

```bash
# Development
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core --profile auth up -d

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile core --profile auth up -d
```

This starts two additional services alongside the hub:

| Service | Image | Description |
|---------|-------|-------------|
| `logto-database` | `postgres:17-alpine` | PostgreSQL database for Logto |
| `logto` | `ghcr.io/logto-io/logto` | OIDC authentication provider |

### 2. Open the Logto Admin Console

Navigate to [http://localhost:3002](http://localhost:3002) (or your production URL) and create an admin account.

### 3. Create an application

1. In the Logto Admin Console, go to **Applications** → **Create Application**
2. Select **Traditional Web** as the application type
3. Note the **App ID** and **App Secret** — you'll need these in step 5

### 4. Configure redirect URIs

In the application settings, set:

| Field | Value |
|-------|-------|
| Redirect URI | `http://localhost:8080/auth/callback` |
| Post Sign-out URI | `http://localhost:8080/` |

For production, replace `http://localhost:8080` with your actual web dashboard URL (e.g., `https://meshcore.example.com/auth/callback`).

### 5. Configure environment variables

Edit your `.env` file and set the Logto variables:

```bash
# OIDC application credentials (from step 3)
LOGTO_APP_ID=your_app_id_here
LOGTO_APP_SECRET=your_app_secret_here

# Redirect URIs (must match step 4)
LOGTO_REDIRECT_URI=http://localhost:8080/auth/callback
LOGTO_POST_LOGOUT_REDIRECT_URI=http://localhost:8080/

# External URLs (browser-facing — update for production)
LOGTO_ENDPOINT=http://localhost:3001
LOGTO_ADMIN_ENDPOINT=http://localhost:3002
```

### 6. Restart the web service

```bash
docker compose restart web
```

The admin interface at `/a/` will now require Logto authentication. A login link appears in the admin pages and optionally in the navigation bar.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGTO_APP_ID` | _(empty)_ | OIDC application ID. When empty, authentication is disabled. |
| `LOGTO_APP_SECRET` | _(empty)_ | OIDC application secret |
| `LOGTO_DISCOVERY_URL` | `http://logto:3001/oidc` | Internal OIDC discovery URL (container-to-container). Set this when Logto is hosted externally. |
| `LOGTO_EXTERNAL_URL` | `http://localhost:3001` | Browser-facing Logto URL used for redirects. Set to `https://auth.example.com` in production. |
| `LOGTO_REDIRECT_URI` | _(empty)_ | Callback URL after login (e.g., `https://meshcore.example.com/auth/callback`). If not set, derived from the request URL. |
| `LOGTO_POST_LOGOUT_REDIRECT_URI` | _(empty)_ | URL to redirect to after logout (e.g., `https://meshcore.example.com/`). If not set, defaults to `/`. |
| `SESSION_SECRET` | _(auto-generated)_ | Secret key for signing session cookies. If not set when Logto is configured, an ephemeral key is generated (sessions will not survive restarts). Set this in production for persistent sessions. |
| `LOGTO_ENDPOINT` | `http://localhost:3001` | Logto OIDC endpoint (passed to Logto container) |
| `LOGTO_ADMIN_ENDPOINT` | `http://localhost:3002` | Logto Admin Console endpoint (passed to Logto container) |
| `LOGTO_DB_USER` | `logto` | PostgreSQL username for Logto's database |
| `LOGTO_DB_PASSWORD` | `logto` | PostgreSQL password for Logto's database |
| `LOGTO_DB_NAME` | `logto` | PostgreSQL database name for Logto |
| `LOGTO_IMAGE_VERSION` | `latest` | Logto Docker image tag |
| `LOGTO_PORT` | `3001` | Host port for Logto OIDC endpoint (dev overlay) |
| `LOGTO_ADMIN_PORT` | `3002` | Host port for Logto Admin Console (dev overlay) |

## Production Setup

In production, Logto must be accessible to users' browsers via HTTPS. Configure your reverse proxy to route traffic to the `logto` container.

### Reverse proxy routing

Add routes for Logto alongside the hub services:

| Service | Container Port | Path |
|---------|---------------|------|
| Logto OIDC | 3001 | Dedicated hostname (e.g., `auth.meshcore.example.com`) or subpath |
| Logto Admin Console | 3002 | Separate hostname or restricted access (e.g., `auth-admin.meshcore.example.com`) |

### Production environment variables

```bash
# Browser-facing URLs (HTTPS)
LOGTO_ENDPOINT=https://auth.meshcore.example.com
LOGTO_ADMIN_ENDPOINT=https://auth-admin.meshcore.example.com

# Internal discovery (container-to-container, stays HTTP)
LOGTO_DISCOVERY_URL=http://logto:3001/oidc

# Callback URIs (HTTPS)
LOGTO_REDIRECT_URI=https://meshcore.example.com/auth/callback
LOGTO_POST_LOGOUT_REDIRECT_URI=https://meshcore.example.com/

# Session secret (set for persistent sessions across restarts)
SESSION_SECRET=<generate a strong random string>

# Secure database credentials
LOGTO_DB_USER=logto
LOGTO_DB_PASSWORD=<generate a strong password>
```

### Traefik

Traefik labels are included in `docker-compose.traefik.yml`. The Logto OIDC endpoint and Admin Console are exposed on dedicated subdomains:

| Service | Subdomain | Container Port |
|---------|-----------|---------------|
| OIDC endpoint | `auth.${TRAEFIK_DOMAIN}` | 3001 |
| Admin Console | `auth-admin.${TRAEFIK_DOMAIN}` | 3002 |

The wildcard TLS certificate (`*.${TRAEFIK_DOMAIN}`) from the web service covers these subdomains.

**DNS setup:** Add A/CNAME records for `auth.${TRAEFIK_DOMAIN}` and `auth-admin.${TRAEFIK_DOMAIN}` pointing to your Traefik host.

**Usage:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.traefik.yml --profile core --profile auth up -d
```

**Production environment variables:**

```bash
LOGTO_ENDPOINT=https://auth.${TRAEFIK_DOMAIN}
LOGTO_ADMIN_ENDPOINT=https://auth-admin.${TRAEFIK_DOMAIN}
LOGTO_REDIRECT_URI=https://${TRAEFIK_DOMAIN}/auth/callback
LOGTO_POST_LOGOUT_REDIRECT_URI=https://${TRAEFIK_DOMAIN}/
```

> **Note:** The Logto Admin Console (`auth-admin.${TRAEFIK_DOMAIN}`) is publicly accessible by default. Add Traefik middleware (e.g., IP whitelist, basic auth) to restrict access.

### Nginx Proxy Manager example

Create two proxy hosts:

| Hostname | Forward Port | Access List |
|----------|-------------|-------------|
| `auth.meshcore.example.com` | 3001 | None (public, needed for OIDC) |
| `auth-admin.meshcore.example.com` | 3002 | Admin only |

## Development

### Logto Admin Console credentials

Use these credentials for the Logto Admin Console during development:

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `2nPrAad4Kiq9xFoC` |

### Remote Access via SSH Tunnel

Logto requires a [secure context](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts) — either `localhost` or HTTPS. When Logto runs on a remote server, you can forward ports 3001 (OIDC) and 3002 (Admin Console) to your local machine via SSH:

```bash
ssh -L 3001:localhost:3001 -L 3002:localhost:3002 <user>@<host>
```

Replace `<user>@<host>` with your SSH credentials for the remote machine.

Once the tunnel is active, `http://localhost:3001` and `http://localhost:3002` on your machine route to the remote Logto service, satisfying the secure context requirement. You can then follow the Quick Start steps using `localhost` URLs as documented.

> **Tip:** Add `-N` to open the tunnel without starting a remote shell, and `-f` to run it in the background: `ssh -N -f -L 3001:localhost:3001 -L 3002:localhost:3002 <user>@<host>`

## Disabling Authentication

To disable Logto authentication:

1. Remove `--profile auth` from your docker compose command
2. Clear `LOGTO_APP_ID` and `LOGTO_APP_SECRET` in `.env`
3. Restart the web service: `docker compose restart web`

The admin interface will be hidden (it is only visible when `LOGTO_APP_ID` is set).
