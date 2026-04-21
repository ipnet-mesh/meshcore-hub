# Nginx Proxy Manager (NPM) Setup

This guide covers setting up MeshCore Hub behind Nginx Proxy Manager, including optional Logto authentication.

## Overview

When using Logto authentication (`--profile auth`), you need three proxy hosts:

1. **Web Dashboard**: the main site (public or with access list)
2. **Logto OIDC**: authentication endpoint (must be public for browser OIDC redirects)
3. **Logto Admin Console**: management interface (restrict with access list)

When not using Logto, only the web dashboard proxy host is needed.

## Proxy Host Configuration

All proxy hosts should forward to the web container:

| Setting                | Value                                        |
| ---------------------- | -------------------------------------------- |
| Scheme                 | `http`                                       |
| Forward Hostname/IP    | Your MeshCore Hub host                       |
| Forward Port           | `8080` (or your mapped web port)             |
| Websockets Support     | `ON`                                         |
| Block Common Exploits  | `ON`                                         |

**Important:**

- Do not host this app under a subpath (for example `/meshcore`); proxy it at `/`.

### Web Dashboard

| Hostname | Forward Port | Access List |
|----------|-------------|-------------|
| `meshcore.example.com` | 8080 | None (public) |

### Logto OIDC (required for authentication)

| Hostname | Forward Port | Access List |
|----------|-------------|-------------|
| `auth.meshcore.example.com` | 3001 | None (public — needed for OIDC redirects) |

### Logto Admin Console (required for authentication)

| Hostname | Forward Port | Access List |
|----------|-------------|-------------|
| `auth-admin.meshcore.example.com` | 3002 | Admin only (restrict with Access List) |

## Logto Environment Variables

Set these in your `.env` file to match your NPM hostnames:

```bash
LOGTO_ENDPOINT=https://auth.meshcore.example.com
LOGTO_ADMIN_ENDPOINT=https://auth-admin.meshcore.example.com
LOGTO_REDIRECT_URI=https://meshcore.example.com/auth/callback
LOGTO_POST_LOGOUT_REDIRECT_URI=https://meshcore.example.com/
LOGTO_APP_ID=your_app_id_here
LOGTO_APP_SECRET=your_app_secret_here
```

See [docs/auth.md](../auth.md) for the full setup guide.
