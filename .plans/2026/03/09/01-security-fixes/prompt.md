# Phase: 01-security-fixes

## Overview

Address CRITICAL and HIGH severity vulnerabilities identified in the MeshCore Hub security audit across API and Web components. These findings represent exploitable vulnerabilities including XSS, timing attacks, authentication bypasses, and insecure defaults.

## Goals

- Eliminate all CRITICAL and HIGH severity security vulnerabilities
- Harden authentication mechanisms against timing attacks and header forgery
- Prevent XSS vectors in both server-rendered HTML and client-side JavaScript
- Secure default MQTT configuration against unauthenticated access

## Requirements

### C1 + H2 — Remove legacy HTML dashboard endpoint
- **File:** `src/meshcore_hub/api/routes/dashboard.py:367-536`
- The `GET /api/v1/dashboard/` endpoint is a standalone HTML page with two CRITICAL/HIGH issues: stored XSS (unescaped DB content in f-string HTML) and missing authentication
- The SPA web dashboard provides a full-featured replacement, making this endpoint redundant
- **Fix:** Remove the `dashboard()` route handler and its `HTMLResponse` import. Keep all JSON sub-routes (`/stats`, `/activity`, `/message-activity`, `/node-count`) intact.

### H1 — Fix timing attack on API key comparison
- **Files:** `api/auth.py:82,127` | `api/metrics.py:57`
- All secret comparisons use Python `==`, which is not constant-time
- **Fix:** Replace with `hmac.compare_digest()` for all key/credential comparisons

### H3 — Harden admin auth against proxy header forgery
- **File:** `web/app.py:73-86,239`
- Admin access trusts `X-Forwarded-User`, `X-Auth-Request-User`, or `Authorization: Basic` header
- `ProxyHeadersMiddleware(trusted_hosts="*")` accepts forged headers from any client
- The `Authorization: Basic` check must be preserved — it is required by the Nginx Proxy Manager (NPM) Access List setup documented in README.md (NPM validates credentials and forwards the header)
- **Fix:** Add a `WEB_TRUSTED_PROXY_HOSTS` config setting (default `*` for backward compatibility). Pass it to `ProxyHeadersMiddleware(trusted_hosts=...)`. Add a startup warning when `WEB_ADMIN_ENABLED=true` and `trusted_hosts` is still `*`, recommending operators restrict it to their proxy IP. Do NOT remove the Basic auth header check or validate credentials server-side — that is the proxy's responsibility.

### H4 — Fix XSS via config_json|safe script block breakout
- **File:** `web/templates/spa.html:188` | `web/app.py:157-183`
- Operator config values injected into `<script>` block with `|safe` — a value containing `</script>` breaks out and executes arbitrary JS
- **Fix:** Escape `</` sequences in the JSON string: `config_json = json.dumps(config).replace("</", "<\\/")`

### H5 — Fix stored XSS via unsafeHTML/innerHTML with API-sourced data
- **Files:** `web/static/js/spa/pages/admin/node-tags.js:243,272,454` | `admin/members.js:309`
- Node names, tag keys, and member names from the API are interpolated into HTML via `unsafeHTML()` and direct `innerHTML` assignment
- **Fix:** Use `escapeHtml()` (already in `components.js`) on API data before HTML interpolation, or replace with lit-html safe templating


## Constraints

- Must not break existing functionality or API contracts
- Changes to docker-compose.yml and mosquitto.conf must remain backward-compatible (use env var defaults)
- The `_is_authenticated_proxy_request` function must continue to work with OAuth2 proxy setups — only add defense-in-depth, don't remove proxy header support entirely

## Out of Scope

- MEDIUM severity findings (CORS config, error detail leakage, rate limiting, security headers, CSRF, CDN SRI, markdown sanitization, input validation, channel key exposure)
- LOW severity findings (auth warnings, version disclosure, unbounded fields, credential logging, SecretStr, port exposure, cache safety, image pinning)
- INFO findings (OpenAPI docs, proxy IP logging, alertmanager comments, DOM XSS in error handler, locale path)
- Adding rate limiting infrastructure
- Adding Content-Security-Policy or other security headers
- Dependency version pinning or lockfile generation

## References

- Security audit performed in this conversation (2026-03-09)
- OWASP Top 10: XSS (A7:2017), Broken Authentication (A2:2017)
- Python `hmac.compare_digest` documentation
- FastAPI security best practices
