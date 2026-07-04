# Tasks: Fix Illegal `X-User-Name` Header Value on New-User Registration

> Generated from `plan.md` on 2026-07-04

## Phase 1: Ingress Normalization

- [x] Strip whitespace from IdP name claim in `strip_userinfo()`
  - [x] In `src/meshcore_hub/web/oidc.py`, after the name fallback chain
        (`name` / `preferred_username` / `username` / `nickname`), add
        `name = name.strip() if isinstance(name, str) else name`
  - [x] Verify `None` passthrough when no name claim exists

## Phase 1b: Profile-Update Input Trimming

- [x] Strip whitespace from user-supplied name in `update_profile()`
  - [x] In `src/meshcore_hub/api/routes/user_profiles.py`, locate the
        `PUT` handler body around line 227
  - [x] Where the request body `name` is assigned to the profile model,
        apply `.strip()` before assignment (guard with `isinstance(name, str)`)

## Phase 2: Header-Boundary Guard

- [x] Add `_ILLEGAL_HEADER_CHARS` constant and `_sanitize_header_value()` helper
  - [x] Add to `src/meshcore_hub/web/app.py` (module level, near the top
        after imports and before the first endpoint / middleware definition):
        ```python
        _ILLEGAL_HEADER_CHARS = "".join(
            chr(c) for c in range(0x00, 0x20) if chr(c) not in "\t "
        ) + "\x7f"

        def _sanitize_header_value(value: str) -> str:
            stripped = value.strip()
            if stripped != value:
                logger.debug("Stripped whitespace from header value %r -> %r", value, stripped)
            if any(c in _ILLEGAL_HEADER_CHARS for c in stripped):
                clean = "".join(c for c in stripped if c not in _ILLEGAL_HEADER_CHARS)
                logger.debug("Dropped control chars from header value %r -> %r", stripped, clean)
                return clean
            return stripped
        ```
  - [x] Verify `logger` is already available in scope (used throughout `app.py`)

- [x] Apply sanitizer at API proxy injection site (`app.py:751`)
  - [x] Replace `headers["X-User-Name"] = user["name"]` with:
        ```python
        sanitized = _sanitize_header_value(user["name"])
        if sanitized:
            headers["X-User-Name"] = sanitized
        ```
  - [x] Keep the existing outer `if user.get("name"):` guard unchanged

- [x] Apply sanitizer at auth-callback bootstrap injection site (`app.py:1128`)
  - [x] Replace `profile_headers["X-User-Name"] = session_user["name"]` with:
        ```python
        sanitized = _sanitize_header_value(session_user["name"])
        if sanitized:
            profile_headers["X-User-Name"] = sanitized
        ```
  - [x] Keep the existing outer `if session_user.get("name"):` guard unchanged

## Phase 3: Tests

- [x] Add `strip_userinfo` unit tests
  - [x] In `tests/test_web/test_oidc.py` (or create if absent): test that
        `strip_userinfo({"name": "Matt ", "sub": "x"}, roles_claim)` returns
        `"Matt"` for name
  - [x] Test `preferred_username` fallback with leading/trailing whitespace
  - [x] Test `username` fallback with whitespace
  - [x] Test `None` passthrough when no name-like claim exists
  - [x] Test leading+trailing whitespace both stripped
  - [x] Follow existing test patterns (pytest fixtures, mocks)

- [x] Add `_sanitize_header_value` unit tests
  - [x] In `tests/test_web/test_app.py`: test helper directly (import from
        `src.meshcore_hub.web.app`)
  - [x] `_sanitize_header_value("Matt \r\n") == "Matt"` (trailing CR/LF stripped)
  - [x] `_sanitize_header_value("Ma\x7ftt") == "Matt"` (DEL stripped)
  - [x] Tab character `"\t"` preserved (RFC-allowed)
  - [x] `_sanitize_header_value("   ") == ""` (whitespace-only yields empty string)
  - [x] `_sanitize_header_value("\x00foo\x00") == "foo"` (NUL stripped)
  - [x] `_sanitize_header_value("clean") == "clean"` (no-op passthrough)

- [x] Add proxy regression test (trailing whitespace name)
  - [x] In `tests/test_web/test_app.py`: set `session["user"]["name"] = "Matt "`
  - [x] Mock `request.app.state.http_client` following existing patterns
  - [x] Assert proxied request returns non-502 status
  - [x] Assert forwarded request has `X-User-Name == "Matt"`

- [x] Add bootstrap regression test
  - [x] With session name `"Matt "`, assert the auth-callback bootstrap
        `GET /api/v1/user/profile/me` (from `app.py:1128`) is forwarded with
        `X-User-Name == "Matt"`
  - [x] Mock `request.app.state.http_client` and verify `.get()` call headers

- [x] Add whitespace-only name guard test
  - [x] With `session["user"]["name"] = "   "`, assert `X-User-Name` header is
        **omitted** from the forwarded request (inner `if sanitized:` guard)

- [x] Add control char edge case tests
  - [x] Name containing embedded DEL (`\x7f`) → forwarded cleanly
  - [x] Name with internal CR/LF/NUL → forwarded with chars dropped
  - [x] Name with tab (`\t`) → tab preserved in forwarded header

- [x] Add profile-update trim test
  - [x] In `tests/test_api/test_user_profiles.py`: make a `PUT` request to
        `/user/profile/{id}` with body `{"name": "  Matt  "}`
  - [x] Assert the profile's `name` is stored as `"Matt"` (no leading/trailing
        whitespace)

## Verification

- [x] Run targeted test suites
  - [x] `pytest --no-cov tests/test_web/ tests/test_api/test_user_profiles.py`
  - [x] All tests pass (0 failures)

- [x] Run full test suite
  - [x] `pytest -nauto --no-cov`
  - [x] All tests pass (0 failures)

- [x] Run pre-commit checks
  - [x] `pre-commit run --all-files`
  - [x] All hooks pass (0 failures)

- [ ] (Optional) Manual smoke test in compose stack
  - [ ] Register a test IdP user whose `name` claim carries trailing whitespace
  - [ ] Confirm login completes without 502
  - [ ] Confirm profile update succeeds without 502
