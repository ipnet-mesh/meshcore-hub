# Nginx Proxy Manager (NPM) Admin Setup

This guide covers setting up MeshCore Hub behind Nginx Proxy Manager with admin authentication.

## Overview

Use two hostnames so the public map/site stays open while admin stays protected:

1. **Public host**: no Access List (normal users).
2. **Admin host**: Access List enabled (operators only).

Both proxy hosts should forward to the same web container:

| Setting                | Value                                        |
| ---------------------- | -------------------------------------------- |
| Scheme                 | `http`                                       |
| Forward Hostname/IP    | Your MeshCore Hub host                       |
| Forward Port           | `18080` (or your mapped web port)            |
| Websockets Support     | `ON`                                         |
| Block Common Exploits  | `ON`                                         |

**Important:**

- Do not host this app under a subpath (for example `/meshcore`); proxy it at `/`.
- `WEB_ADMIN_ENABLED` must be `true`.

## Advanced Configuration

In NPM, for the **admin host**, paste this in the `Advanced` field:

```nginx
# Forward authenticated identity for MeshCore Hub admin checks
proxy_set_header Authorization $http_authorization;
proxy_set_header X-Forwarded-User $remote_user;
proxy_set_header X-Auth-Request-User $remote_user;
proxy_set_header X-Forwarded-Email "";
proxy_set_header X-Forwarded-Groups "";
```

Then attach your NPM Access List (Basic auth users) to that admin host.

## Verifying Auth Forwarding

```bash
curl -s -u 'admin:password' "https://admin.example.com/config.js?t=$(date +%s)" \
  | grep -o '"is_authenticated":[^,]*'
```

Expected:

```text
"is_authenticated": true
```

If it still shows `false`, check:

1. You are using the admin hostname, not the public hostname.
2. The Access List is attached to that admin host.
3. The `Advanced` block above is present exactly.
4. `WEB_ADMIN_ENABLED=true` is loaded in the running web container.
