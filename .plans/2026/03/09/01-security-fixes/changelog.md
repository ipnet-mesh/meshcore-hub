## TASK-001: Remove legacy HTML dashboard endpoint
**Status:** completed
### Files Modified
- `src/meshcore_hub/api/routes/dashboard.py`
- `tests/test_api/test_dashboard.py`
### Notes
Removed the `dashboard()` route handler and its `@router.get("")` decorator. Removed `HTMLResponse` and `Request` imports no longer used. Updated existing tests to verify the HTML endpoint returns 404/405. All JSON sub-routes (`/stats`, `/activity`, `/message-activity`, `/node-count`) remain intact.
---

## TASK-002: Replace API key comparisons with constant-time comparison
**Status:** completed
### Files Modified
- `src/meshcore_hub/api/auth.py`
- `src/meshcore_hub/api/metrics.py`
### Notes
Added `import hmac` to both files. Replaced `==` comparisons with `hmac.compare_digest()` in `require_read`, `require_admin`, and `verify_basic_auth`. Added truthiness guards for `read_key`/`admin_key` in `require_read` since either can be `None` and `hmac.compare_digest()` raises `TypeError` on `None`.
---

## TASK-003: Add WEB_TRUSTED_PROXY_HOSTS configuration setting
**Status:** completed
### Files Modified
- `src/meshcore_hub/common/config.py`
### Notes
Added `web_trusted_proxy_hosts: str = Field(default="*", ...)` to `WebSettings` class. Automatically configurable via `WEB_TRUSTED_PROXY_HOSTS` env var through Pydantic Settings.
---

## TASK-004: Integrate trusted proxy hosts into web app middleware and add startup warning
**Status:** completed
### Files Modified
- `src/meshcore_hub/web/app.py`
### Notes
Replaced hardcoded `trusted_hosts="*"` in `ProxyHeadersMiddleware` with configured value. If value is `"*"`, passes string directly; otherwise splits on commas. Added startup warning when `WEB_ADMIN_ENABLED=true` and `WEB_TRUSTED_PROXY_HOSTS="*"`. `_is_authenticated_proxy_request` unchanged.
---

## TASK-005: Escape config JSON in template script block to prevent XSS breakout
**Status:** completed
### Files Modified
- `src/meshcore_hub/web/app.py`
### Notes
Added `.replace("</", "<\\/")` to `_build_config_json` return value. Prevents `</script>` breakout in the Jinja2 template's `<script>` block. `<\/` is valid JSON per spec and parsed correctly by `JSON.parse()`.
---

## TASK-006: Fix stored XSS in admin node-tags page
**Status:** completed
### Files Modified
- `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`
### Notes
Added `escapeHtml` to imports. Escaped `nodeName` with `escapeHtml()` in copy-all and delete-all confirmation dialogs (2 `unsafeHTML()` calls). Escaped `activeTagKey` with `escapeHtml()` in single tag delete confirmation (`innerHTML` assignment). Translation template `<strong>` tags preserved.
---

## TASK-007: Fix stored XSS in admin members page
**Status:** completed
### Files Modified
- `src/meshcore_hub/web/static/js/spa/pages/admin/members.js`
### Notes
Added `escapeHtml` to imports. Escaped `memberName` with `escapeHtml()` before passing to `t()` in delete confirmation dialog. `innerHTML` retained for `<strong>` tag rendering from translation template.
---

## TASK-008: Write tests for legacy dashboard endpoint removal
**Status:** completed
### Files Modified
- `tests/test_api/test_dashboard.py`
### Notes
Added 5 new tests: 1 for trailing-slash 404/405 verification, 4 for authenticated JSON sub-route responses. Total 20 dashboard tests passing.
---

## TASK-009: Write tests for constant-time API key comparison
**Status:** completed
### Files Modified
- `tests/test_api/test_auth.py`
### Notes
Restructured from 10 tests (2 classes) to 22 tests (4 classes): `TestReadAuthentication` (9), `TestAdminAuthentication` (4), `TestMetricsAuthentication` (7), `TestHealthEndpoint` (2). Added coverage for multi-endpoint read/admin key acceptance, missing auth header rejection, and metrics credential validation.
---

## TASK-010: Write tests for trusted proxy hosts configuration and startup warning
**Status:** completed
### Files Modified
- `tests/test_common/test_config.py`
- `tests/test_web/test_app.py`
### Notes
Added 3 config tests (default value, specific IP, comma-separated list) and 5 web app tests (warning logged with wildcard+admin, no warning with specific hosts, no warning with admin disabled, comma list parsing, wildcard passed as string).
---

## TASK-011: Write tests for config JSON script block escaping
**Status:** completed
### Files Created
- `tests/test_web/test_app.py`
### Notes
Added 5 tests in `TestConfigJsonXssEscaping` class: rendered HTML escaping, normal values unaffected, escaped JSON parseable, direct `_build_config_json` escaping, direct no-escaping-needed.
---

## TASK-012: Update documentation for WEB_TRUSTED_PROXY_HOSTS setting
**Status:** completed
### Files Modified
- `README.md`
- `AGENTS.md`
- `PLAN.md`
### Notes
Added `WEB_TRUSTED_PROXY_HOSTS` to environment variables sections in all three docs. Documented default value (`*`), production recommendation, and startup warning behavior.
---
