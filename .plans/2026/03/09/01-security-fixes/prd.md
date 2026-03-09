# Product Requirements Document

> Source: `.plans/2026/03/09/01-security-fixes/prompt.md`

## Project Overview

This project addresses CRITICAL and HIGH severity vulnerabilities identified in a security audit of MeshCore Hub. The fixes span stored XSS in server-rendered and client-side code, timing attacks on authentication, proxy header forgery, and a legacy endpoint with missing authentication. All changes must be backward-compatible and preserve existing API contracts.

## Goals

- Eliminate all CRITICAL and HIGH severity security vulnerabilities found in the audit
- Harden API key comparison against timing side-channel attacks
- Prevent XSS vectors in both Jinja2 templates and client-side JavaScript
- Add configurable proxy trust to defend against header forgery while maintaining backward compatibility
- Remove the redundant legacy HTML dashboard endpoint that lacks authentication

## Functional Requirements

### REQ-001: Remove legacy HTML dashboard endpoint

**Description:** Remove the `GET /api/v1/dashboard/` route handler that renders a standalone HTML page with unescaped database content (stored XSS) and no authentication. The JSON sub-routes (`/stats`, `/activity`, `/message-activity`, `/node-count`) must remain intact and unchanged.

**Acceptance Criteria:**

- [ ] The `dashboard()` route handler in `api/routes/dashboard.py` is removed
- [ ] The `HTMLResponse` import is removed (if no longer used)
- [ ] `GET /api/v1/dashboard/` returns 404 or Method Not Allowed
- [ ] `GET /api/v1/dashboard/stats` continues to return valid JSON with authentication
- [ ] `GET /api/v1/dashboard/activity` continues to return valid JSON with authentication
- [ ] `GET /api/v1/dashboard/message-activity` continues to return valid JSON with authentication
- [ ] `GET /api/v1/dashboard/node-count` continues to return valid JSON with authentication
- [ ] Existing API tests for JSON sub-routes still pass

### REQ-002: Use constant-time comparison for API key validation

**Description:** Replace all Python `==` comparisons of API keys and credentials with `hmac.compare_digest()` to prevent timing side-channel attacks that could leak key material.

**Acceptance Criteria:**

- [ ] All API key comparisons in `api/auth.py` use `hmac.compare_digest()` instead of `==`
- [ ] All credential comparisons in `api/metrics.py` use `hmac.compare_digest()` instead of `==`
- [ ] `hmac` is imported in all files where secret comparison occurs
- [ ] The authentication behavior is unchanged — valid keys are accepted, invalid keys are rejected
- [ ] Tests confirm authentication still works correctly with valid and invalid keys

### REQ-003: Add configurable trusted proxy hosts for admin authentication

**Description:** Add a `WEB_TRUSTED_PROXY_HOSTS` configuration setting that controls which hosts are trusted for proxy authentication headers (`X-Forwarded-User`, `X-Auth-Request-User`, `Authorization: Basic`). The setting defaults to `*` for backward compatibility. A startup warning is emitted when admin is enabled with the wildcard default. The `Authorization: Basic` header check must be preserved for Nginx Proxy Manager compatibility.

**Acceptance Criteria:**

- [ ] A `WEB_TRUSTED_PROXY_HOSTS` setting is added to the configuration (Pydantic Settings)
- [ ] The setting defaults to `*` (backward compatible)
- [ ] `ProxyHeadersMiddleware` uses the configured `trusted_hosts` value instead of hardcoded `*`
- [ ] A warning is logged at startup when `WEB_ADMIN_ENABLED=true` and `WEB_TRUSTED_PROXY_HOSTS` is `*`
- [ ] The warning message recommends restricting trusted hosts to the operator's proxy IP
- [ ] The `_is_authenticated_proxy_request` function continues to accept `X-Forwarded-User`, `X-Auth-Request-User`, and `Authorization: Basic` headers
- [ ] OAuth2 proxy setups continue to function correctly
- [ ] Setting `WEB_TRUSTED_PROXY_HOSTS` to a specific IP restricts proxy header trust to that IP

### REQ-004: Escape config JSON in template script block

**Description:** Prevent XSS via `</script>` breakout in the `config_json|safe` template injection by escaping `</` sequences in the serialized JSON string before passing it to the Jinja2 template.

**Acceptance Criteria:**

- [ ] `config_json` is escaped by replacing `</` with `<\\/` before template rendering (in `web/app.py`)
- [ ] The `|safe` filter continues to be used (the escaping happens in Python, not Jinja2)
- [ ] A config value containing `</script><script>alert(1)</script>` does not execute JavaScript
- [ ] The SPA application correctly parses the escaped config JSON on the client side
- [ ] Normal config values (without special characters) render unchanged

### REQ-005: Fix stored XSS in admin page JavaScript

**Description:** Sanitize API-sourced data (node names, tag keys, member names) before rendering in admin pages. Replace `unsafeHTML()` and direct `innerHTML` assignment with safe alternatives — either `escapeHtml()` (already available in `components.js`) or lit-html safe templating (`${value}` interpolation without `unsafeHTML`).

**Acceptance Criteria:**

- [ ] Node names in `admin/node-tags.js` are escaped or safely templated before HTML rendering
- [ ] Tag keys in `admin/node-tags.js` are escaped or safely templated before HTML rendering
- [ ] Member names in `admin/members.js` are escaped or safely templated before HTML rendering
- [ ] All `unsafeHTML()` calls on API-sourced data in the identified files are replaced with safe alternatives
- [ ] All direct `innerHTML` assignments of API-sourced data in the identified files are replaced with safe alternatives
- [ ] A node name containing `<img src=x onerror=alert(1)>` renders as text, not as an HTML element
- [ ] A member name containing `<script>alert(1)</script>` renders as text, not as executable script
- [ ] Normal names (without special characters) continue to display correctly

## Non-Functional Requirements

### REQ-006: Backward compatibility

**Category:** Reliability

**Description:** All security fixes must maintain backward compatibility with existing deployments. No breaking changes to API contracts, configuration defaults, or deployment workflows.

**Acceptance Criteria:**

- [ ] All existing API endpoints (except the removed HTML dashboard) return the same response format
- [ ] Default configuration values preserve existing behavior without requiring operator action
- [ ] Docker Compose deployments continue to function without configuration changes
- [ ] All existing tests pass after the security fixes are applied

### REQ-007: No regression in authentication flows

**Category:** Security

**Description:** The security hardening must not introduce authentication regressions. Valid credentials must continue to be accepted, and invalid credentials must continue to be rejected, across all authentication methods.

**Acceptance Criteria:**

- [ ] API read key authentication accepts valid keys and rejects invalid keys
- [ ] API admin key authentication accepts valid keys and rejects invalid keys
- [ ] Metrics endpoint authentication (if configured) accepts valid credentials and rejects invalid ones
- [ ] Proxy header authentication continues to work with OAuth2 proxy setups
- [ ] Basic auth header forwarding from Nginx Proxy Manager continues to work

## Technical Constraints and Assumptions

### Constraints

- Python 3.13+ (specified by project `.python-version`)
- Must use `hmac.compare_digest()` from the Python standard library for constant-time comparison
- The `Authorization: Basic` header check in `_is_authenticated_proxy_request` must not be removed or modified to validate credentials server-side — credential validation is the proxy's responsibility
- Changes must not alter existing API response schemas or status codes (except removing the HTML dashboard endpoint)

### Assumptions

- The `escapeHtml()` utility in `components.js` correctly escapes `<`, `>`, `&`, `"`, and `'` characters
- The SPA client-side JavaScript can parse JSON containing escaped `<\/` sequences (standard behavior per JSON spec)
- Operators using proxy authentication have a reverse proxy (e.g., Nginx, Traefik, NPM) in front of MeshCore Hub

## Scope

### In Scope

- Removing the legacy HTML dashboard route handler (C1 + H2)
- Replacing `==` with `hmac.compare_digest()` for all secret comparisons (H1)
- Adding `WEB_TRUSTED_PROXY_HOSTS` configuration and startup warning (H3)
- Escaping `</` in config JSON template injection (H4)
- Fixing `unsafeHTML()`/`innerHTML` XSS in admin JavaScript pages (H5)
- Updating tests to cover the security fixes
- Updating documentation for the new `WEB_TRUSTED_PROXY_HOSTS` setting

### Out of Scope

- MEDIUM severity findings (CORS, error detail leakage, rate limiting, security headers, CSRF, CDN SRI, markdown sanitization, input validation, channel key exposure)
- LOW severity findings (auth warnings, version disclosure, unbounded fields, credential logging, SecretStr, port exposure, cache safety, image pinning)
- INFO findings (OpenAPI docs, proxy IP logging, alertmanager comments, DOM XSS in error handler, locale path)
- Adding rate limiting infrastructure
- Adding Content-Security-Policy or other security headers
- Dependency version pinning or lockfile generation
- Server-side credential validation for Basic auth (proxy responsibility)

## Suggested Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Secret comparison | `hmac.compare_digest()` (stdlib) | Specified by prompt; constant-time comparison prevents timing attacks |
| Template escaping | Python `str.replace()` | Minimal approach to escape `</` in JSON before Jinja2 rendering |
| Client-side escaping | `escapeHtml()` from `components.js` | Already available in the codebase; standard HTML entity escaping |
| Configuration | Pydantic Settings | Specified by project stack; used for `WEB_TRUSTED_PROXY_HOSTS` |
| Testing | pytest, pytest-asyncio | Specified by project stack |
