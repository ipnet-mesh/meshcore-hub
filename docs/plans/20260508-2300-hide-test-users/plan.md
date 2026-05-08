# Plan: Hide Users with "test" OIDC Role

**Date:** 2025-05-08
**Status:** Draft

## Problem

Users with a `test` OIDC role should be completely hidden from the Members page and excluded from all member/operator counts across the UI. This applies regardless of whether the user also holds `member` or `operator` roles. Currently, there is no mechanism to filter out test users — they appear alongside real members and operators.

## Current Behavior

### How Roles Work

- OIDC roles are stored as a **comma-separated string** in `user_profiles.roles` (e.g., `"member,test"`, `"operator,member,test"`)
- Roles are synced from the IdP on every authenticated request via the `X-User-Roles` header
- Role names are configurable via env vars (`OIDC_ROLE_ADMIN`, `OIDC_ROLE_OPERATOR`, `OIDC_ROLE_MEMBER`) but default to `"admin"`, `"operator"`, `"member"`

### Where Member/Operator Data is Displayed

There are **three surfaces** that show user data or counts:

1. **Homepage stats panel** (`home.js` → `renderMembersPanel()`) — shows `total_operators` and `total_members` from the `/api/v1/dashboard/stats` endpoint
2. **Members page** (`members.js`) — fetches all profiles from `/api/v1/user/profiles`, then client-side filters into "Operators" and "Members" groups
3. **Dashboard stats API** (`dashboard.py` → `get_stats()`) — counts profiles where `roles.contains("operator")` and `roles.contains("member")` independently

### Existing Discrepancy (pre-existing bug)

The server-side counts (`dashboard.py`) count a user with both `operator` and `member` in **both** totals. The client-side Members page excludes operators from the "Members" group. This means homepage totals can be higher than what the Members page shows. This plan does not fix that bug but should not make it worse.

## Approach

Add a configurable "test role" that, when present on a user profile, excludes that user from all public-facing member displays and counts. The filtering should happen at the **API level** so both the homepage stats and the Members page list are consistent.

### New Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_ROLE_TEST` | IdP role name that marks a user as a test user | `test` |

This follows the existing pattern of `OIDC_ROLE_ADMIN`, `OIDC_ROLE_OPERATOR`, `OIDC_ROLE_MEMBER`.

### Scope of Changes

#### 1. Configuration (`common/config.py`)

- Add `oidc_role_test: str = Field(default="test", ...)` to `WebSettings`
- Add `test_role` to the `role_names` dict in `_build_config_json()` (in `web/app.py`) so the frontend knows which role marks test users
- Update `AGENTS.md` and `.env.example` with the new env var

#### 2. Dashboard Stats API (`api/routes/dashboard.py`)

**File:** `src/meshcore_hub/api/routes/dashboard.py` (~lines 209-246)

Read `test_role` from config using the existing `get_web_settings()` pattern (already imported at line 209). Guard against empty string to prevent accidental universal exclusion.

Add a `test_role` variable alongside `operator_role` and `member_role`:

```python
test_role = web_settings.oidc_role_test
```

Modify the `total_operators` and `total_members` queries to **exclude** profiles whose `roles` column contains the test role string. Only apply the filter when `test_role` is non-empty:

```python
# Current:
total_operators = ... .where(UserProfile.roles.contains(operator_role))

# New:
total_operators = (select(func.count()).select_from(UserProfile)
    .where(UserProfile.roles.contains(operator_role)))
if test_role:
    total_operators = total_operators.where(~UserProfile.roles.contains(test_role))
```

Same pattern for `total_members`. This ensures the homepage stats panel shows correct counts.

> **Note on `contains()`**: Since `roles` is a comma-separated string (e.g., `"operator,member,test"`), `contains("test")` will correctly match. A false positive could theoretically occur if a role name is a substring of another (e.g., `"test"` matching `"contest"`), but this is the same approach already used for operator/member counts and is acceptable given role names are short, well-known strings.
>
> **Guard condition**: If `OIDC_ROLE_TEST` is set to an empty string, the filter is skipped entirely (no profiles excluded). This allows disabling the feature without removing the config variable.

#### 3. User Profiles List API (`api/routes/user_profiles.py`)

**File:** `src/meshcore_hub/api/routes/user_profiles.py`

The `GET /api/v1/user/profiles` endpoint returns all profiles. Add an optional query parameter or internal filter to exclude test users from the response. Two options:

- **Option A (recommended):** Add a `?exclude_test=true` query parameter (default `true`) that filters out profiles with the test role. This keeps the API general-purpose while defaulting to the desired behavior.
- **Option B:** Always exclude test users from the list endpoint. Simpler but less flexible.

**Chosen: Option A** — default to excluding test users but allow explicit opt-out.

Get the `test_role` string from config using the same `get_web_settings()` pattern as `dashboard.py`. Apply the filter only when both `exclude_test=true` and `test_role` is non-empty (guard against empty string matching all rows).

Implementation:

```python
from meshcore_hub.common.config import get_web_settings

@router.get("", response_model=UserProfileList)
async def list_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_read)],
    exclude_test: bool = Query(default=True),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> UserProfileList:
    web_settings = get_web_settings()
    test_role = web_settings.oidc_role_test

    count_query = select(func.count(UserProfile.id))
    if exclude_test and test_role:
        count_query = count_query.where(~UserProfile.roles.contains(test_role))
    total = session.execute(count_query).scalar() or 0

    query = (
        select(UserProfile)
        .options(
            selectinload(UserProfile.node_associations).selectinload(
                UserProfileNode.node
            )
        )
        .order_by(UserProfile.name)
        .offset(offset)
        .limit(limit)
    )
    if exclude_test and test_role:
        query = query.where(~UserProfile.roles.contains(test_role))
    # ... rest unchanged ...
```

The `total` in the paginated response must also exclude test users when `exclude_test=true`.

#### 4. Members Page Frontend (`web/static/js/spa/pages/members.js`)

**File:** `src/meshcore_hub/web/static/js/spa/pages/members.js`

The Members page already fetches profiles and does client-side filtering into operator/member groups. After the API change (step 3), test users will already be excluded from the API response by default.

However, as a **defense-in-depth** measure, also filter client-side using the `role_names.test` from the frontend config:

```javascript
const testRole = config.role_names.test;
const realProfiles = profiles.filter(p => !p.roles || !p.roles.includes(testRole));
```

This ensures test users are never displayed even if the API defaults change.

Update the Members page total stats (the "X Operators, Y Members" summary) to use the already-filtered lists.

#### 5. Homepage Frontend (`web/static/js/spa/pages/home.js`)

**File:** `src/meshcore_hub/web/static/js/spa/pages/home.js` (~lines 169-194)

The homepage stats panel (`renderMembersPanel()`) reads `total_operators` and `total_members` from the dashboard stats API. After step 2, these counts will already exclude test users. **No frontend changes needed** for the homepage.

#### 6. Profile Page (`web/static/js/spa/pages/profile.js`)

No changes needed — individual profile pages should still be accessible via direct URL. Test users are only hidden from aggregate views (lists and counts), not from their own profile page.

#### 7. Frontend Config (`web/app.py`)

**File:** `src/meshcore_hub/web/app.py` (`_build_config_json()`)

Add `test` to the `role_names` dict:

```python
role_names = {
    "admin": app.state.oidc_role_admin,
    "operator": app.state.oidc_role_operator,
    "member": app.state.oidc_role_member,
    "test": app.state.oidc_role_test,  # NEW
}
```

#### 8. App State Initialization (`web/app.py`)

Ensure `oidc_role_test` is stored in `app.state` alongside the existing role settings, so it's available to route handlers and the config builder.

### Files Changed (Summary)

| File | Change |
|------|--------|
| `src/meshcore_hub/common/config.py` | Add `oidc_role_test` setting |
| `src/meshcore_hub/api/routes/dashboard.py` | Exclude test users from operator/member count queries |
| `src/meshcore_hub/api/routes/user_profiles.py` | Add `exclude_test` query param, filter test users from list |
| `src/meshcore_hub/web/app.py` | Add `test` to `role_names` config; store `oidc_role_test` in app state |
| `src/meshcore_hub/web/static/js/spa/pages/members.js` | Client-side defense-in-depth filter for test role |
| `AGENTS.md` | Document `OIDC_ROLE_TEST` env var |
| `.env.example` | Add `OIDC_ROLE_TEST` entry |

### Tests to Add/Update

| Test File | Change |
|-----------|--------|
| `tests/test_api/test_dashboard.py` | Add test: users with test role excluded from counts |
| `tests/test_api/test_user_profiles.py` | Add test: `exclude_test=true` filters test users from list; verify `total` count is correct |
| `tests/test_web/` | Verify frontend config includes `role_names.test` |

### Edge Cases

- **User with `operator,test` roles**: Should be excluded from both the Operators section and the operator count
- **User with `member,test` roles**: Should be excluded from both the Members section and the member count
- **User with `operator,member,test` roles**: Should be excluded from everything
- **Test user accessing their own profile**: Should still work — they can view and edit their own profile
- **Test user adopting nodes**: Should still work — adoption is a separate concern from display
- **`OIDC_ROLE_TEST` not configured**: Defaults to `"test"`, matching the common convention
- **No users have the test role**: Behavior is identical to current — no regressions

### Out of Scope

- Fixing the pre-existing discrepancy between server-side and client-side member counts (operators counted in both server-side totals)
- Hiding test users from the admin API or database — they should still exist and be manageable
- Revoking test user permissions or access — they should still be able to log in and use the dashboard
- Migration: No schema changes needed — the `roles` column already stores arbitrary comma-separated role strings

## Implementation Order

1. Add `oidc_role_test` to `WebSettings` in `config.py`
2. Wire `oidc_role_test` into `app.state` and `_build_config_json()` in `web/app.py`
3. Update dashboard stats queries in `api/routes/dashboard.py`
4. Add `exclude_test` filter to `GET /api/v1/user/profiles` in `api/routes/user_profiles.py`
5. Update Members page client-side filter in `members.js`
6. Add/update tests
7. Update documentation (`AGENTS.md`, `.env.example`)
8. Run `pre-commit run --all-files` and `pytest`
