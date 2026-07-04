# Fix Illegal `X-User-Name` Header Value on New-User Registration

**Date:** 2026-07-04
**Status:** Proposed
**Slug:** fix-illegal-user-name-header

## Summary

When an OIDC identity provider returns a `name` claim containing leading or
trailing whitespace (e.g. `"Matt "`) at registration time, every authenticated
proxied API request begins to fail with `502 API proxy error` and the log line
`API proxy error: Illegal header value b'Matt '`. The dirty value flows
unmodified from the IdP token, into the Starlette session, and is injected
verbatim as the `X-User-Name` request header by the web proxy layer; `httpx`
then rejects it under RFC 7230 (which forbids leading/trailing OWS and embedded
control characters in header field values).

This plan normalizes the display name at ingress and adds a defensive guard at
the header-construction boundary so the proxy can never emit an illegal header
value regardless of where the data originated. The fix is safe because
`X-User-Name` is purely informational: its sole consumer seeds the non-unique
`UserProfile.name` display column on first profile creation, and identity /
authorization are keyed on `X-User-Id` (the OIDC `sub`) and `X-User-Roles`
respectively.

## Background & Motivation

### Reported incident

A new user signed up via the IdP, then attempted to update their profile name.
The profile update (and in fact **all** subsequent authenticated API calls)
returned `502`, and the collector log recorded:

```
meshcore_hub.web.app - ERROR - API proxy error: Illegal header value b'Matt '
```

### Root cause (verified by code trace)

1. The IdP returned a `name` claim with a trailing space at registration.
2. `strip_userinfo()` in `src/meshcore_hub/web/oidc.py:58` copies the claim
   verbatim into the session dict — no sanitization.
3. On every authenticated API call the web proxy injects the session name as a
   request header at `src/meshcore_hub/web/app.py:751`:
   `headers["X-User-Name"] = user["name"]`.
4. `httpx.AsyncClient.request(...)` enforces RFC 7230 and rejects the value,
   raising an exception that is swallowed by the generic handler at
   `src/meshcore_hub/web/app.py:793`, returning `502 {"detail": "API proxy error"}`.
5. The same dirty value is injected at the auth-callback bootstrap
   (`src/meshcore_hub/web/app.py:1128`), so the user's `UserProfile` is never
   seeded on first login either.

### Safety analysis — `X-User-Name` is informational only

A full sweep of every `request.headers.get(...)` call in `src/` confirms the
**only** reader of `X-User-Name` is
`src/meshcore_hub/api/profile_utils.py:38` inside `get_or_create_profile()`:

```python
query = select(UserProfile).where(UserProfile.user_id == user_id)  # lookup by sub
profile = session.execute(query).scalar_one_or_none()
if not profile:
    idp_name = request.headers.get(X_USER_NAME_HEADER) or None     # ONLY read
    profile = UserProfile(user_id=user_id, name=idp_name)           # seeds display name
```

Concretely:

- The header is read **only** on the `if not profile:` branch — first-time
  profile creation.
- It is assigned to `UserProfile.name`, a non-unique display column
  (`src/meshcore_hub/common/models/user_profile.py:40`, no `unique=True`).
- It is **never** a lookup key, identity check, or authorization input.
  Identity = `X-User-Id` (`src/meshcore_hub/api/auth.py:183`);
  authorization = `X-User-Roles` (`auth.py:210,237`,
  `channel_visibility.py:18`).

Therefore normalizing (stripping) the value cannot affect identity, auth, or
uniqueness, and two users whose display names differ only by whitespace
collapsing to the same string is correct display-normalization behavior, not a
clash.

### Relevant history

The `X-User-Name` plumbing was introduced by the OIDC support plan
(`20260428-1300-oidc-oauth-support`) and the consumer helper by the members
refactor (`20260430-0805-members-refactor`). Neither sanitized the IdP-supplied
name; this plan closes that gap.

## Goals

- Eliminate the `Illegal header value` 502 for any user whose IdP `name` claim
  contains leading/trailing whitespace or embedded RFC-illegal control
  characters (CR/LF/NUL).
- Keep session-stored display names and seeded `UserProfile.name` values clean
  at the ingress point.
- Guarantee the web proxy can never construct an illegal header value,
  regardless of future data sources (defense in depth).
- Add regression coverage so the bug cannot silently return.
- Trim user-supplied names at the profile-update endpoint to prevent whitespace
  from being saved through the editor.

## Non-Goals

- **Backfill of existing dirty rows.** Profiles already seeded with whitespace
  names will continue to display with whitespace until the user edits them. A
  one-time data migration is not in scope (see Open Questions).
- **Changing the IdP.** The IdP may legitimately emit trailing spaces; the hub
  must tolerate this.
- **Renaming or repurposing** the `X-User-Name` header contract.

## Requirements

### Functional Requirements

- FR-1: A user whose IdP `name` contains leading/trailing whitespace (e.g.
  `"Matt "`) must be able to complete login, profile bootstrap, and any
  authenticated API call without receiving a `502`.
- FR-2: The session-stored `name` and any newly seeded `UserProfile.name` must
  have leading/trailing whitespace removed.
- FR-3: The forwarded `X-User-Name` header must be a valid RFC 7230 field value
  (no leading/trailing OWS, no embedded CR/LF/NUL).
- FR-4: Existing authentication, authorization, identity, and uniqueness
  semantics must be unchanged (no new collisions, no altered access control).

### Technical Requirements

- TR-1: Normalize in `strip_userinfo()` (`src/meshcore_hub/web/oidc.py`) so the
  session dict never carries leading/trailing whitespace on `name`.
- TR-2: Add a private helper in `src/meshcore_hub/web/app.py`, e.g.
  `_sanitize_header_value(value: str) -> str`, that strips leading/trailing
  whitespace and removes all RFC 7230-forbidden CTL characters
  (`0x00-0x1F` excluding HTAB/SP, plus DEL `0x7F`). Apply it at both
  header-injection sites (`app.py:751` and `app.py:1128`).
- TR-3: Preserve `None`/empty semantics — an empty/whitespace-only name must
  result in the `X-User-Name` header being omitted (existing
  `if user.get("name")` guard retained).
- TR-4: No new dependencies. No DB schema change. No migration.
- TR-5: Tests added under `tests/test_web/` (and an OIDC unit test) following
  existing fixture/mock patterns; full suite plus `pre-commit run --all-files`
  must pass.

## Implementation Plan

### Phase 1: Ingress normalization

- Edit `strip_userinfo()` in `src/meshcore_hub/web/oidc.py`: after resolving
  `name` from the `name` / `preferred_username` / `username` / `nickname`
  fallback chain, apply `name = name.strip() if isinstance(name, str) else name`.
- Rationale: fixes the reported case at its source; session data and the
  resulting seeded `UserProfile.name` are clean from the first login.

### Phase 1b: Profile-update input trimming

- Edit the `update_profile()` endpoint in `src/meshcore_hub/api/routes/user_profiles.py`
  (the `PUT` handler around line 227): if the request body includes a `name`
  field with a `str` value, apply `.strip()` before assigning it to the model.
- Rationale: prevents users from accidentally or deliberately saving
  whitespace-padded display names via the profile editor. Completes the
  defense-in-depth coverage with minimal effort.

### Phase 2: Header-boundary guard (defense in depth)

- Add a module-level helper in `src/meshcore_hub/web/app.py`:
  ```python
  _ILLEGAL_HEADER_CHARS = "".join(
      chr(c) for c in range(0x00, 0x20) if chr(c) not in "\t "
  ) + "\x7f"

  def _sanitize_header_value(value: str) -> str:
      # RFC 7230 § 3.2.6: field-value must not contain CTL (0x00-0x1F
      # excluding HTAB 0x09 and SP 0x20, plus DEL 0x7F), and must not
      # have leading/trailing OWS.
      stripped = value.strip()
      if stripped != value:
          logger.debug("Stripped whitespace from header value %r -> %r", value, stripped)
      if any(c in _ILLEGAL_HEADER_CHARS for c in stripped):
          clean = "".join(c for c in stripped if c not in _ILLEGAL_HEADER_CHARS)
          logger.debug("Dropped control chars from header value %r -> %r", stripped, clean)
          return clean
      return stripped
  ```
- Apply at `app.py:751` (API proxy): replace
  `headers["X-User-Name"] = user["name"]` with:
  ```python
  sanitized = _sanitize_header_value(user["name"])
  if sanitized:
      headers["X-User-Name"] = sanitized
  ```
- Apply at `app.py:1128` (auth-callback bootstrap): replace
  `profile_headers["X-User-Name"] = session_user["name"]` with:
  ```python
  sanitized = _sanitize_header_value(session_user["name"])
  if sanitized:
      profile_headers["X-User-Name"] = sanitized
  ```
- Nested guard (`if sanitized:`) prevents emitting an empty header value when
  the input is whitespace-only (edge case where the `user.get("name")` outer
  guard is truthy for a whitespace-only string).
- Debug-level logs surface malformed IdP data when `_sanitize_header_value`
  actually alters a value, without spamming production logs.
- Rationale: even if a future code path or an IdP quirk reintroduces dirty data
  into the session or elsewhere, the proxy cannot emit an illegal header.

### Phase 3: Tests

- **Proxy regression** (`tests/test_web/`): with `session["user"]["name"]` set to
  `"Matt "`, assert a proxied API request returns a non-502 status and that the
  forwarded request was sent with `X-User-Name == "Matt"`. Mock
  `request.app.state.http_client` consistent with `tests/test_web/test_app.py`.
- **Bootstrap regression**: with a session name of `"Matt "`, assert the
  auth-callback bootstrap request (`GET /api/v1/user/profile/me` from
  `app.py:1128`) is forwarded with `X-User-Name == "Matt"`. Mock
  `request.app.state.http_client` and verify the `.get()` call headers.
- **Control char edge cases**: test names containing embedded `DEL` (`\x7f`),
  internal `CR`/`LF`/`NUL`, and tab (which should be preserved as RFC-allowed).
  Trailing `"\r\n"` is forwarded cleanly with control characters dropped.
- **Whitespace-only name guard**: with `session["user"]["name"] = "   "`,
  assert `X-User-Name` header is omitted from the forwarded request (inner
  guard prevents empty-string header value).
- **`strip_userinfo` unit test**: `strip_userinfo({"name": "Matt ", "sub": "x"},
  roles_claim)` returns `{"name": "Matt", ...}`; also cover the
  `preferred_username` and `username` fallbacks being trimmed, `None`
  passthrough for missing names, and leading+trailing whitespace both stripped.
- **Helper unit test**: `_sanitize_header_value("Matt \r\n") == "Matt"`;
  `_sanitize_header_value("Ma\x7ftt") == "Matt"`; tab preserved;
  `_sanitize_header_value("   ") == ""`.
- **Profile-update trim** (`tests/test_api/test_user_profiles.py`):
  `PUT /user/profile/{id}` with body `{"name": "  Matt  "}` results in
  the profile's `name` field being stored as `"Matt"` (no leading/trailing
  whitespace).

### Phase 4: Verification

- Run targeted suites, then the full suite, then pre-commit:
  ```bash
  source .venv/bin/activate
  pytest --no-cov tests/test_web/ tests/test_api/test_user_profiles.py
  pytest -nauto --no-cov
  pre-commit run --all-files
  ```
- Manual smoke (optional, in the compose stack): register a test IdP user whose
  `name` claim carries trailing whitespace and confirm login + profile update
  succeed without a 502.

## Open Questions

1. **~~Profile-update trimming.~~** Resolved: included in scope (Phase 1b).
   `PUT /user/profile/{id}` will `.strip()` the user-supplied `name`.
2. **Backfill existing dirty rows.** Should a one-time Alembic/maintenance step
   trim whitespace from already-seeded `UserProfile.name` values, or leave them
   for users to self-correct via the profile editor? Default: **out of scope**.

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-07-04

### Resolutions

- **RFC 7230 completeness** — `_sanitize_header_value` character filter
  expanded from `\r\n\x00` to the full set of RFC-forbidden CTL chars
  (`0x00-0x1F` excluding HTAB/SP, plus DEL `0x7F`). Tab is preserved (RFC
  allows it).
- **Whitespace-only name edge case** — Both injection sites now have a nested
  `if sanitized:` guard after sanitization, so a whitespace-only name
  resolving to `""` correctly omits the header rather than emitting an empty
  string value.
- **Observability** — `_sanitize_header_value` emits debug-level logs when it
  strips whitespace or drops control characters. Non-altering calls are silent.
- **Bootstrap path test coverage** — Phase 3 tests now explicitly cover both
  injection sites (`app.py:751` API proxy and `app.py:1128` auth-callback
  bootstrap), plus control char edge cases and whitespace-only guard behavior.

### Remaining Action Items

- Decide on Open Question 2 (backfill) — does not gate this fix.

## References

- `docs/plans/20260428-1300-oidc-oauth-support/plan.md` — introduced
  `strip_userinfo()` and the `X-User-*` proxy header contract.
- `docs/plans/20260430-0805-members-refactor/plan.md` — introduced
  `get_or_create_profile()`, the sole consumer of `X-User-Name`.
- `docs/plans/20260428-1251-remove-header-auth/plan.md` — broader header-auth
  context.
- Key source sites:
  - `src/meshcore_hub/web/oidc.py:58` (`strip_userinfo`)
  - `src/meshcore_hub/web/app.py:751`, `:1128` (header injection)
  - `src/meshcore_hub/web/app.py:793` (generic 502 handler)
  - `src/meshcore_hub/api/profile_utils.py:38` (sole `X-User-Name` reader)
  - `src/meshcore_hub/common/models/user_profile.py:40` (non-unique `name`)
  - `src/meshcore_hub/api/auth.py:17` (`X_USER_NAME_HEADER` constant)
