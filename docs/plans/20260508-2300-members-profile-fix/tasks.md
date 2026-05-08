# Tasks: Allow role-less OIDC users to save their own profile

## Source: [plan.md](plan.md)

---

### 1. Add `_AUTHENTICATED` sentinel constant and update block comment

**File:** `src/meshcore_hub/web/app.py` (~line 61-65)

Add `_AUTHENTICATED` sentinel after `_OPEN` definition. Update the block comment (lines 61-64) to document the new access level.

**Code:**

```python
# Per-endpoint, per-method role access mapping for the API proxy.
# Key: URL path prefix (after /api/), Value: {method -> allowed roles}.
# _OPEN = unconditional access (OIDC on or off, anonymous OK).
# _AUTHENTICATED = any logged-in user with a valid OIDC session (no specific role needed).
# Method not listed = denied. No prefix match = denied.
_OPEN: frozenset[str] = frozenset()
_AUTHENTICATED: frozenset[str] = frozenset({"__any_authenticated__"})
```

---

### 2. Update `_build_endpoint_access` docstring

**File:** `src/meshcore_hub/web/app.py` (~line 73-81)

Update docstring to document all three access levels.

**Code:**

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

---

### 3. Update `_build_endpoint_access` mapping entry

**File:** `src/meshcore_hub/web/app.py` (line 119)

Change `PUT` for `v1/user/profile` from `any_authenticated` to `_AUTHENTICATED`.

**Code:**

```python
        "v1/user/profile": {
            "GET": _OPEN,
            "PUT": _AUTHENTICATED,
        },
```

---

### 4. Update `check_api_access` signature, body, and docstring

**File:** `src/meshcore_hub/web/app.py` (~line 124-146)

Add `user_id` parameter, `_AUTHENTICATED` check branch, and update docstring.

**Code:**

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

---

### 5. Update `api_proxy` handler to extract and pass `user_id`

**File:** `src/meshcore_hub/web/app.py` (~line 585-602)

Extract `user_id` from OIDC session before calling `check_api_access`, and pass it as a keyword argument.

**Code:**

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

Leave the existing header injection at lines 620-629 untouched.

---

### 6. Add `NO_ROLES_USER` constant to web test conftest

**File:** `tests/test_web/conftest.py` (after `MEMBER_USER`, ~line 395)

**Code:**

```python
NO_ROLES_USER = {
    "sub": "noroles-1",
    "name": "No Roles User",
    "email": "noroles@example.com",
    "picture": None,
    "roles": [],
}
```

---

### 7. Add `client_with_oidc_no_roles_session` fixture to web test conftest

**File:** `tests/test_web/conftest.py` (after `client_with_oidc_member_session`, ~line 430)

**Code:**

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

---

### 8. Add `TestCheckApiAccess` unit tests

**File:** `tests/test_web/test_app.py`

Add a new test class with 7 tests exercising `check_api_access` directly:

- `test_open_allows_anonymous`
- `test_authenticated_requires_oidc_session`
- `test_authenticated_rejects_no_session`
- `test_authenticated_rejects_oidc_disabled`
- `test_authenticated_ignores_roles`
- `test_role_required_denies_roleless`
- `test_role_required_allows_matching_role`

Import `_OPEN`, `_AUTHENTICATED` from `meshcore_hub.web.app`.

---

### 9. Add `TestRolelessUserProfileUpdate` integration test

**File:** `tests/test_web/test_app.py`

Add a test class using `client_with_oidc_no_roles_session` fixture that:

1. Sets up a mock PUT response for `/api/v1/user/profile/noroles-1`
2. Sends `PUT /api/v1/user/profile/noroles-1` through the proxy
3. Asserts status 200 (not 403)

---

### 10. Add `test_update_profile_with_no_roles` to API tests

**File:** `tests/test_api/test_user_profiles.py`

Add to `TestUpdateProfile` class. Uses existing `NO_ROLES_HEADERS` (line 20-23). Verifies API-level profile update works with `X-User-Roles: ""`. This is a regression guard — it passes even without the proxy fix, confirming the API layer never adds a role gate for profile self-service.

---

### 11. Run tests and quality checks

```bash
source .venv/bin/activate
pytest tests/test_web/ tests/test_api/test_user_profiles.py -v
pre-commit run --all-files
```
