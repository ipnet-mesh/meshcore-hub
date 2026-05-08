# Plan: Allow role-less OIDC users to save their own profile

## Problem

When a user logs in via OIDC but has **no roles** assigned (not admin, operator, or member), they can:

- View their profile page (`GET /api/v1/user/profile/me`) — works fine
- See the edit form — renders correctly

But when they try to **save** their profile (`PUT /api/v1/user/profile/{id}`), they get:

```
API error: 403 - {"detail":"Access denied","code":"AUTH_REQUIRED"}
```

## Root Cause

The 403 originates from the **web proxy access control** in `web/app.py`, not the API itself.

The endpoint access mapping at `web/app.py:117-120`:

```python
"v1/user/profile": {
    "GET": _OPEN,
    "PUT": any_authenticated,  # <-- requires at least one of: admin, operator, member
},
```

Where `any_authenticated = frozenset({role_admin, role_operator, role_member})` (line 83).

The `check_api_access` function at line 124-146 evaluates:

```python
return bool(user_roles & required)  # empty frozenset & any_authenticated = empty = False
```

A user with no roles has `user_roles = frozenset()`, so the intersection with `any_authenticated` is empty → **403 denied at the proxy**, the request never reaches the API.

The API route itself (`api/routes/user_profiles.py:182-217`) already enforces owner-only access via `RequireUserOwner` (validates API key + `X-User-Id` header + `profile.user_id == caller_id`). This is sufficient to prevent users from modifying others' profiles.

## Fix Strategy

Introduce a new `_AUTHENTICATED` sentinel (distinct from `_OPEN`) that means "any logged-in user, regardless of roles." This is semantically different from `_OPEN` (which allows anonymous access) and `any_authenticated` (which requires a specific role).

**Design note:** `_AUTHENTICATED` uses `frozenset({"__any_authenticated__"})` rather than a bare `object()` singleton to keep the mapping type uniform (`dict[str, frozenset[str]]`). The `__any_authenticated__` string is an internal sentinel value — no real-world role name will collide with it.

### Changes

### 1. `src/meshcore_hub/web/app.py` — Access control mapping

**a. Add `_AUTHENTICATED` sentinel constant and update comment** (after `_OPEN` definition, ~line 61-65):

Current:
```python
# Per-endpoint, per-method role access mapping for the API proxy.
# Key: URL path prefix (after /api/), Value: {method -> allowed roles}.
# _OPEN = unconditional access (OIDC on or off, anonymous OK).
# Method not listed = denied. No prefix match = denied.
_OPEN: frozenset[str] = frozenset()
```

New:
```python
# Per-endpoint, per-method role access mapping for the API proxy.
# Key: URL path prefix (after /api/), Value: {method -> allowed roles}.
# _OPEN = unconditional access (OIDC on or off, anonymous OK).
# _AUTHENTICATED = any logged-in user with a valid OIDC session (no specific role needed).
# Method not listed = denied. No prefix match = denied.
_OPEN: frozenset[str] = frozenset()
_AUTHENTICATED: frozenset[str] = frozenset({"__any_authenticated__"})
```

**b. Update `_build_endpoint_access` docstring** (~line 75-81):

Update the docstring to mention `_AUTHENTICATED` alongside `_OPEN`:

```python
    """Build the per-endpoint access mapping using configured role names.

    Uses three access levels:
      - _OPEN: unconditional access, anonymous OK.
      - _AUTHENTICATED: any logged-in OIDC user (regardless of roles).
      - Specific roles: requires OIDC with one of the listed roles.

    Args:
        role_admin: The IdP role name that grants admin access.
        role_operator: The IdP role name that grants operator access.
        role_member: The IdP role name that grants member access.

    Returns:
        Endpoint access mapping dict.
    """
```

**c. Update `check_api_access` function signature, body, and docstring** (~line 124-146):

Add `user_id` parameter and `_AUTHENTICATED` check. Update docstring to document the new access level.

```python
def check_api_access(
    path: str,
    method: str,
    oidc_enabled: bool,
    user_roles: frozenset[str],
    user_id: str | None = None,
    mapping: dict[str, dict[str, frozenset[str]]] | None = None,
) -> bool:
    """Check if user has required access for the given API path + method.

    Three access levels defined by the mapping value:
      - _OPEN (empty frozenset): unconditional access, anonymous OK.
      - _AUTHENTICATED (sentinel frozenset): any logged-in OIDC user.
      - Specific roles: requires OIDC enabled + user has at least one matching role.

    Longest prefix wins. Method must be explicitly listed.
    """
    if mapping is None:
        return False
    for prefix in sorted(mapping, key=len, reverse=True):
        if path.startswith(prefix):
            required = mapping[prefix].get(method)
            if required is None:
                return False
            if not required:
                return True                        # _OPEN
            if required is _AUTHENTICATED:         # any logged-in user
                return oidc_enabled and bool(user_id)
            if not oidc_enabled:
                return False
            return bool(user_roles & required)
    return False
```

Note: `user_id` defaults to `None` for backward compatibility — `check_api_access` is also called outside the proxy handler (no caller uses it currently, but the default keeps the signature safe).

**d. Update the `_build_endpoint_access` mapping entry** (~line 117-120):

```python
"v1/user/profile": {
    "GET": _OPEN,
    "PUT": _AUTHENTICATED,   # was: any_authenticated
},
```

**e. Update the `api_proxy` handler** (~line 585-602):

Extract `user_id` from the OIDC session and pass it to `check_api_access`. Note: this adds a second `get_session_user` call at the beginning of the handler (the existing `get_session_roles` call on line 591 also calls `get_session_user` internally). The duplicate is a single dict lookup — negligible overhead, avoids duplicating `get_session_roles` role-parsing logic.

```python
async def api_proxy(request: Request, path: str) -> Response:
    """Proxy API requests to the backend API server."""
    oidc_enabled = getattr(request.app.state, "oidc_enabled", False)
    user_roles: frozenset[str] = frozenset()
    user_id: str | None = None
    if oidc_enabled:
        user = get_session_user(request)
        user_id = user.get("sub") if user else None
        roles_claim = getattr(request.app.state, "oidc_roles_claim", "roles")
        user_roles = frozenset(get_session_roles(request, roles_claim))
    if not check_api_access(
        path,
        request.method,
        oidc_enabled,
        user_roles,
        user_id=user_id,
        mapping=request.app.state.endpoint_access,
    ):
        return JSONResponse(
            {"detail": "Access denied", "code": "AUTH_REQUIRED"},
            status_code=403,
        )
```

The existing header injection at lines 620-629 (which also calls `get_session_user` and injects `X-User-Id`) is untouched — it runs after the access check and provides the API-level identity.

### 2. Tests

### `tests/test_web/test_app.py` — Proxy access control tests

**a. Add `TestCheckApiAccess` class** — unit tests for the `check_api_access` function directly:

- `test_open_allows_anonymous` — `_OPEN` allows access without OIDC
- `test_authenticated_requires_oidc_session` — `_AUTHENTICATED` requires `oidc_enabled=True` and a `user_id`
- `test_authenticated_rejects_no_session` — `_AUTHENTICATED` rejects when `user_id=None` (no session)
- `test_authenticated_rejects_oidc_disabled` — `_AUTHENTICATED` rejects when `oidc_enabled=False` (even with a `user_id`)
- `test_authenticated_ignores_roles` — `_AUTHENTICATED` allows users with empty roles (any valid session passes)
- `test_role_required_denies_roleless` — role-specific mapping still denies users with no roles
- `test_role_required_allows_matching_role` — role-specific mapping allows users with a matching role

**b. Add `NO_ROLES_USER` constant and `client_with_oidc_no_roles_session` fixture** in `tests/test_web/conftest.py`:

```python
NO_ROLES_USER = {
    "sub": "noroles-1",
    "name": "No Roles User",
    "email": "noroles@example.com",
    "picture": None,
    "roles": [],
}
```

Fixture:
```python
@pytest.fixture
def client_with_oidc_no_roles_session(
    web_app_with_oidc: Any, mock_http_client: MockHttpClient
) -> Generator[TestClient, None, None]:
    """Create a test client with OIDC enabled and a session with NO roles."""
    web_app_with_oidc.state.http_client = mock_http_client
    with (
        patch("meshcore_hub.web.app.get_session_user", return_value=NO_ROLES_USER),
        patch("meshcore_hub.web.oidc.get_session_user", return_value=NO_ROLES_USER),
    ):
        yield TestClient(web_app_with_oidc, raise_server_exceptions=True)
```

**c. Add `TestRolelessUserProfileUpdate` class** — integration test for the proxy flow:

Verifies that a user with no OIDC roles can PUT their own profile through the proxy and get a 200 response (not 403). Uses the `client_with_oidc_no_roles_session` fixture.

### `tests/test_api/test_user_profiles.py` — Role-less user update test

`NO_ROLES_HEADERS` already exists at line 20-23. Add a test in `TestUpdateProfile`:

- `test_update_profile_with_no_roles` — verifies that a user with `X-User-Roles: ""` can still update their own profile via the API. **Note:** this test would pass even without the fix because `RequireUserOwner` (the API-level dependency for `PUT /profile/{id}`) checks only the API key and `X-User-Id` header — it does NOT check roles. The test serves as a regression guard ensuring the API layer never introduces a role gate for profile self-service.

### 3. No documentation changes needed

The AGENTS.md already describes the auth architecture accurately. The `OIDC_SCOPES` and role variables are for privilege escalation (adoptions, tag editing), not basic profile self-service. The fix doesn't change any env vars or user-facing configuration.

## Scope

- **In scope**: Fix the web proxy to allow any authenticated OIDC user to PUT their own profile
- **Out of scope**: Changing any other endpoint permissions (adoptions, tags remain operator/admin-only)

## Files to Modify

| File | Change |
|------|--------|
| `src/meshcore_hub/web/app.py` | Add `_AUTHENTICATED` sentinel, update comments/docstrings, update `check_api_access`, update mapping, extract `user_id` in `api_proxy` |
| `tests/test_web/conftest.py` | Add `NO_ROLES_USER` constant and `client_with_oidc_no_roles_session` fixture |
| `tests/test_web/test_app.py` | Add `TestCheckApiAccess` class and `TestRolelessUserProfileUpdate` class |
| `tests/test_api/test_user_profiles.py` | Add `test_update_profile_with_no_roles` |

## Risk Assessment

- **Low risk**: The fix only loosens the web proxy gate. The API route already enforces owner-only access (`RequireUserOwner` + `profile.user_id != caller_id` check). A role-less user cannot modify anyone else's profile.
- **No regression for other endpoints**: Adoptions and tags still use `operator_admin` / `any_authenticated` — unaffected by the new `_AUTHENTICATED` sentinel.
- **No direct API access risk**: Direct API calls (bypassing the proxy) still require a valid API key via `RequireUserOwner`.
- **Sentinel collision risk**: Negligible. The `__any_authenticated__` string is an internal sentinel stored in a frozenset; no real-world IdP role name will match it.
