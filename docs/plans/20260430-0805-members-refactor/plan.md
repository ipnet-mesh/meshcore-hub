# Replace Members with UserProfile — Implementation Plan

**Date:** 2026-04-30
**Status:** Approved

## Overview

Remove the static `Member` model/schema/routes and replace the Members page with a UserProfile-backed page. UserProfiles are auto-created from OIDC authentication and linked to nodes via the `UserProfileNode` adoption table. The new page shows two groups — Operators and Members — based on persisted OIDC roles. The `member_id` tag system used for node→member associations is replaced with UserProfile adoption data throughout nodes, advertisements, and map pages.

## Decisions

1. **Roles stored on `UserProfile`** — A `roles` column (comma-separated string) is added to `user_profiles`, updated from `X-User-Roles` on each authenticated request. IdP role changes reflected on next profile access.
2. **Profile UUID in public URLs** — Public profile links use the profile `id` (UUID), not the OIDC `user_id` subject identifier, to avoid exposing IdP identifiers.
3. **Full Members removal** — Delete `Member` model, schemas, routes, admin page, seed import, CLI commands, tests. Drop `members` table via Alembic migration. No backward compatibility.
4. **`FEATURE_MEMBERS` kept** — The env var still controls nav visibility, now backed by UserProfile data.
5. **`/profile/:id` for public viewing** — Extend the existing profile route. Own profile (`/profile`) remains editable; public view (`/profile/:id`) is read-only (editable only for the owner).
6. **Shared `_get_or_create_profile` utility** — Deduplicated from `user_profiles.py` and `adoptions.py` into a single module.
7. **`member_id` tag system replaced with UserProfile adoptions** — The `member_id` tag on nodes (used for filtering and display in nodes, ads, and map pages) is replaced with UserProfile adoption data. Member filter dropdowns become "Adopted by user" filters.
8. **Separate public profile schema** — A `UserProfilePublic` schema omits `user_id` from public-facing API responses.
9. **Role names exposed in SPA config** — The server-side `OIDC_ROLE_OPERATOR` / `OIDC_ROLE_MEMBER` config values are exposed to the SPA via `window.__APP_CONFIG__.role_names` so the frontend can correctly group profiles by role.
10. **Prometheus metrics replaced** — `meshcore_members_total` replaced with `meshcore_user_profiles_total` and `meshcore_user_profiles_by_role`.

## Terminology

| Term | Meaning |
|---|---|
| Profile UUID | `user_profiles.id` — the UUID primary key, used in public URLs |
| `user_id` | OIDC subject identifier (`sub` claim) — internal, not exposed in public APIs |
| Operator | User with the `operator` role (from `OIDC_ROLE_OPERATOR` config) |
| Member | User with the `member` role (from `OIDC_ROLE_MEMBER` config) |
| Adoption | A `UserProfileNode` row linking a user to a node |
| `member_id` tag | Legacy node tag referencing a Member slug — **removed** in this plan |

## Current State

### Member Model (`members` table)

```
members
├── id            UUID PK
├── member_id     String(100) UNIQUE — human-readable slug (e.g., 'walshie86')
├── name          String(255)
├── callsign      String(20) nullable
├── role          String(100) nullable
├── description   Text nullable
├── contact       String(255) nullable
├── created_at    DateTime
└── updated_at    DateTime
```

Nodes linked indirectly via `member_id` tag on `NodeTag`.

### UserProfile Model (`user_profiles` table)

```
user_profiles
├── id            UUID PK
├── user_id       String(255) UNIQUE — OIDC subject
├── name          String(255) nullable
├── callsign      String(20) nullable
├── created_at    DateTime
└── updated_at    DateTime
```

**Missing:** `roles` column.

Nodes linked via `UserProfileNode` join table (adoptions).

### `member_id` Tag Usage (to be replaced)

The `member_id` tag on nodes is used for filtering and display across the codebase:

| Location | Usage |
|----------|-------|
| `api/routes/nodes.py:44` | `member_id` query filter param |
| `api/routes/advertisements.py:53` | Same `member_id` query filter |
| `web/app.py:658-740` | Map data endpoint fetches `/api/v1/members`, builds lookup, populates `owner` |
| `web/static/js/spa/pages/nodes.js` | Member filter dropdown, member name on node rows |
| `web/static/js/spa/pages/advertisements.js` | Same member filter and display |
| `web/static/js/spa/pages/map.js` | Member filter dropdown, filters by `node.member_id` |
| `seed/node_tags.yaml` | 18 entries with `member_id` tags |

### API Endpoints

| Endpoint | Current Auth | Notes |
|----------|-------------|-------|
| `GET /api/v1/members` | `RequireRead` | List all members — **to be removed** |
| `GET /api/v1/members/{id}` | `RequireRead` | Get member by UUID — **to be removed** |
| `POST /api/v1/members` | `RequireAdmin` | Create member — **to be removed** |
| `PUT /api/v1/members/{id}` | `RequireAdmin` | Update member — **to be removed** |
| `DELETE /api/v1/members/{id}` | `RequireAdmin` | Delete member — **to be removed** |
| `GET /api/v1/user/profile/{user_id}` | `RequireUserOwner` | Owner-only, auto-creates — **to be updated** |
| `PUT /api/v1/user/profile/{user_id}` | `RequireUserOwner` | Owner-only update — **to be updated** |
| `POST /api/v1/adoptions` | `RequireOperatorOrAdmin` | Adopt a node — unchanged |
| `DELETE /api/v1/adoptions/{pk}` | `RequireOperatorOrAdmin` | Release a node — unchanged |

### Frontend Routes

| Route | Page | Notes |
|-------|------|-------|
| `/members` | `members.js` | Public member listing — **to be rewritten** |
| `/admin/members` | `admin/members.js` | Admin CRUD — **to be removed** |
| `/profile` | `profile.js` | Own profile (editable) — **to be extended** |

---

## Implementation

### Phase 1: Database & Model Changes

#### 1.1 Add `roles` column to `UserProfile` model

**File:** `src/meshcore_hub/common/models/user_profile.py`

Add column:

```python
from sqlalchemy import String, Text

roles: Mapped[Optional[str]] = mapped_column(
    Text,
    nullable=True,
    default=None,
)
```

Add helper property:

```python
@property
def role_list(self) -> list[str]:
    if not self.roles:
        return []
    return [r.strip() for r in self.roles.split(",") if r.strip()]
```

#### 1.2 Alembic migration

```bash
source .venv/bin/activate
meshcore-hub db revision --autogenerate -m "add roles to user_profiles, drop members"
```

Edit the generated migration to:
- Add `roles` column (nullable text) to `user_profiles`
- Drop `members` table

```bash
meshcore-hub db upgrade
```

### Phase 2: Shared Utility Refactor

#### 2.1 Extract `_get_or_create_profile`

**File:** `src/meshcore_hub/api/profile_utils.py` (new)

Create a shared helper module. The helper:

1. Looks up `UserProfile` by `user_id`
2. If not found, creates one with `name` from `X-User-Name` header
3. **Updates `roles`** from `X-User-Roles` header on every call
4. Returns the profile

```python
def get_or_create_profile(
    session: DbSession,
    user_id: str,
    request: Request,
) -> UserProfile:
    query = select(UserProfile).where(UserProfile.user_id == user_id)
    profile = session.execute(query).scalar_one_or_none()
    if not profile:
        idp_name = request.headers.get(X_USER_NAME_HEADER) or None
        profile = UserProfile(user_id=user_id, name=idp_name)

    roles_header = request.headers.get(X_USER_ROLES_HEADER, "")
    profile.roles = roles_header or None

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
```

#### 2.2 Update consumers

**Files:** `api/routes/user_profiles.py`, `api/routes/adoptions.py`

- Remove local `_get_or_create_profile` from both files
- Import shared helper from `api/profile_utils.py`
- Update all call sites

### Phase 3: API Endpoint Changes

#### 3.1 New Pydantic schemas

**File:** `src/meshcore_hub/common/schemas/user_profiles.py`

```python
class UserProfileRead(BaseModel):
    id: str
    user_id: str
    name: Optional[str] = None
    callsign: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class UserProfilePublic(BaseModel):
    """Public-facing schema — omits user_id for privacy."""
    id: str
    name: Optional[str] = None
    callsign: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class UserProfileListItem(BaseModel):
    id: str
    name: Optional[str] = None
    callsign: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    node_count: int = 0

class UserProfileList(BaseModel):
    items: list[UserProfileListItem]
    total: int
    limit: int
    offset: int

class UserProfilePublicWithNodes(UserProfilePublic):
    """Public profile view with adopted nodes."""
    nodes: list[AdoptedNodeRead] = Field(default_factory=list)
```

Update `UserProfileWithNodes` to add `roles` field (inherits from `UserProfileRead`).

#### 3.2 New public list endpoint

**File:** `src/meshcore_hub/api/routes/user_profiles.py`

```
GET /api/v1/user/profiles
```

- **Auth:** `RequireRead` (open if no API keys configured)
- **Query params:** `limit` (default 100, max 500), `offset` (default 0)
- **Response:** `UserProfileList` with `items`, `total`, `limit`, `offset`
- Each item includes: `id`, `name`, `callsign`, `roles` (parsed list), `node_count`
- No `user_id` exposed in list response (privacy)
- Ordered by `name` ascending

**Route ordering:** This route MUST be registered before `GET /profile/{profile_id}` to avoid FastAPI matching "profiles" as a `{profile_id}` value.

```python
@router.get("/profiles", response_model=UserProfileList)
async def list_profiles(
    _: RequireRead,
    session: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> UserProfileList:
```

#### 3.3 Update detail endpoint — support profile UUID lookup

**File:** `src/meshcore_hub/api/routes/user_profiles.py`

Change `GET /api/v1/user/profile/{profile_id}` to:

- Accept profile UUID instead of `user_id`
- **Remove `_verify_owner` for GET** — anyone can view
- Auto-create only when the caller is the authenticated owner
- Return `UserProfilePublicWithNodes` (public schema, no `user_id`)
- For the owner's own request, still return `UserProfileWithNodes` (includes `user_id`)

Two lookup strategies:
1. If authenticated caller's `user_id` matches the profile's `user_id` → auto-create, return full profile
2. Otherwise → lookup by profile UUID, return public view (404 if not found)

Auth dependency becomes optional (allow unauthenticated access).

#### 3.4 Update PUT endpoint

**File:** `src/meshcore_hub/api/routes/user_profiles.py`

Change `PUT /api/v1/user/profile/{profile_id}` to:

- Accept profile UUID
- Keep owner + admin write restriction
- Lookup profile by UUID, verify `profile.user_id == caller_id` (or admin)

#### 3.5 Replace `member_id` filter in nodes/advertisements API routes

**File:** `src/meshcore_hub/api/routes/nodes.py`

- Remove `member_id` query parameter (line 44)
- Add optional `adopted_by` query parameter — filters nodes that are adopted by a specific user profile (by profile UUID)
- Implementation: join `UserProfileNode` and filter by `user_profile_id`

**File:** `src/meshcore_hub/api/routes/advertisements.py`

- Remove `member_id` query parameter (line 53-54)
- Add optional `adopted_by` query parameter — same approach as nodes

### Phase 4: Web App Updates

#### 4.1 Update endpoint access map

**File:** `src/meshcore_hub/web/app.py`

```python
# Remove:
"v1/members": {
    "GET": _OPEN,
    "POST": admin,
    "PUT": admin,
    "DELETE": admin,
},

# Add:
"v1/user/profiles": {
    "GET": _OPEN,
},
```

Update existing `v1/user/profile` entry to allow unauthenticated GET (remove role requirement for GET, keep for PUT).

#### 4.2 Update robots.txt / sitemap

**File:** `src/meshcore_hub/web/app.py`

- Keep `/members` in feature paths and sitemap (the page still exists, just backed by UserProfile data)

#### 4.3 Update map data endpoint

**File:** `src/meshcore_hub/web/app.py` (lines 658-740)

The `/map/data` endpoint currently:
1. Fetches all members from `/api/v1/members`
2. Builds a lookup by `member_id`
3. For each node, reads `member_id` tag and resolves to member info
4. Populates `owner` and `member_id` on each map node

Replace with:
1. Fetch all user profiles from `/api/v1/user/profiles`
2. Fetch all adoptions (or include adopted_by in node data from the nodes API)
3. For each node, resolve adoption to user profile
4. Populate `owner` on each map node (with `id`, `name`, `callsign` from profile)
5. Remove `member_id` field from map node objects
6. Remove `members_list` from map response (replace with `profiles` if needed for filter dropdown)

#### 4.4 Expose role names in SPA config

**File:** `src/meshcore_hub/web/app.py` (`_build_config_json`)

Add role names to the SPA config so the frontend can match profile roles to the configured operator/member/admin role values:

```python
config["role_names"] = {
    "operator": settings.oidc_role_operator,
    "member": settings.oidc_role_member,
    "admin": settings.oidc_role_admin,
}
```

### Phase 5: Remove Members Infrastructure

#### 5.1 Delete files

| File | Description |
|---|---|
| `src/meshcore_hub/common/models/member.py` | Member SQLAlchemy model |
| `src/meshcore_hub/common/schemas/members.py` | Member Pydantic schemas |
| `src/meshcore_hub/api/routes/members.py` | Member API routes |
| `src/meshcore_hub/collector/member_import.py` | Member YAML import |
| `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` | Admin members page |
| `seed/members.yaml` | Production member seed data |
| `example/seed/members.yaml` | Example member seed data |

#### 5.2 Update `__init__` exports

**File:** `src/meshcore_hub/common/models/__init__.py`

- Remove `Member` import and export

**File:** `src/meshcore_hub/common/schemas/__init__.py`

- Remove `MemberCreate`, `MemberUpdate`, `MemberRead`, `MemberList` imports and exports

**File:** `src/meshcore_hub/api/routes/__init__.py`

- Remove `members_router` import and `include_router` call

#### 5.3 Update `collector/cli.py`

- Remove `import_members_cmd` (`import-members` command, lines 539-613)
- Remove member import from `seed` command (lines 413-431 in `_run_seed_import`)
- Remove `--members` flag from `truncate` command (line 705)
- Remove `--all` member inclusion from `truncate` command (line 794)
- Remove `Member` import from `truncate` command (line 851)
- Remove member truncation logic (lines 867-870)

#### 5.4 Update `common/config.py`

- Remove `members_file` property (lines 184-189)

#### 5.5 Update `api/metrics.py`

- Remove `Member` import (line 17)
- Replace `meshcore_members_total` gauge (lines 273-280) with:

```python
user_profiles_total = Gauge(
    "meshcore_user_profiles_total",
    "Total number of user profiles",
    registry=registry,
)
count = session.execute(select(func.count(UserProfile.id))).scalar() or 0
user_profiles_total.set(count)

user_profiles_by_role = Gauge(
    "meshcore_user_profiles_by_role",
    "Number of user profiles by role",
    ["role"],
    registry=registry,
)
for row in session.execute(select(UserProfile.roles, func.count(UserProfile.id)).group_by(UserProfile.roles)):
    if row.roles:
        for role in row.roles.split(","):
            role = role.strip()
            if role:
                user_profiles_by_role.labels(role=role).set(
                    session.execute(
                        select(func.count(UserProfile.id)).where(UserProfile.roles.contains(role))
                    ).scalar() or 0
                )
```

#### 5.6 Update `web/templates/spa.html`

- Remove admin Members nav link from admin section (both mobile and desktop menus)

#### 5.7 Update admin index page

**File:** `src/meshcore_hub/web/static/js/spa/pages/admin/index.js`

- Remove members admin card/link from the admin dashboard (lines 51-59)

#### 5.8 Update i18n

**File:** `src/meshcore_hub/web/static/locales/en.json`

Remove:
- `members.*` section
- `admin_members.*` section
- `admin.members_description` entry

Keep (used by the new UserProfile-backed members page):
- `entities.members` / `entities.member` — still used for nav link and page title

Add:
```json
{
  "members_page": {
    "operators": "Operators",
    "members": "Members",
    "node_count": "{{count}} nodes",
    "empty_state": "No members yet",
    "empty_description": "Members will appear here once users log in and adopt nodes."
  },
  "user_profile": {
    "view_profile": "View Profile",
    "edit_profile": "Edit Profile",
    "role_operator": "Operator",
    "role_member": "Member"
  }
}
```

#### 5.9 Remove `member_id` tags from seed data

**File:** `seed/node_tags.yaml`

- Remove all `member_id:` key-value entries (18 occurrences)

#### 5.10 Update `docker-compose.yml`

- Update seed service comment from "Imports both node_tags.yaml and members.yaml if they exist" to "Imports node_tags.yaml if it exists" (line 360)

### Phase 6: Frontend — Replace member_id References

#### 6.1 Update nodes page

**File:** `src/meshcore_hub/web/static/js/spa/pages/nodes.js`

- Remove fetch of `/api/v1/members` (line 61)
- Remove `member_id` query param handling (line 15)
- Remove `showMembers` flag and member filter dropdown (lines 22, 73-81)
- Remove `memberIdTag` lookup and member name display (lines 93-96, 125-128, 148)
- Remove "Member" column header from desktop table (line 198)
- Optionally: add `adopted_by` filter if desired (or skip for now)

#### 6.2 Update advertisements page

**File:** `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`

- Same pattern as nodes: remove `/api/v1/members` fetch, `member_id` param, member filter dropdown, member display

#### 6.3 Update map page

**File:** `src/meshcore_hub/web/static/js/spa/pages/map.js`

- Remove member filter dropdown (lines 209-221)
- Remove `memberFilter` logic (line 279)
- Remove `node.member_id` filter comparison
- The map data endpoint will now provide `owner` from UserProfile adoptions instead of `member_id` tags
- Update owner display on map popups if applicable

### Phase 7: Frontend — Members Page & Profile Page

#### 7.1 Rewrite `members.js`

**File:** `src/meshcore_hub/web/static/js/spa/pages/members.js`

- Fetch from `GET /api/v1/user/profiles`
- Read `config.role_names` to determine which role values map to operator/member
- Split profiles into two groups:
  - **Operators** — where `roles` includes the operator role name, sorted alphabetically by `name`
  - **Members** — where `roles` includes the member role name (and not operator), sorted alphabetically by `name`
- Each tile shows: `name`, `callsign` badge, `node_count` ("N nodes")
- Tiles link to `/profile/${profile.id}`
- Section headers: "Operators" and "Members"
- Empty state: simple "No members yet" message
- Layout: same responsive grid (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`)

#### 7.2 Update `app.js` routes

**File:** `src/meshcore_hub/web/static/js/spa/app.js`

- Remove `adminMembers` lazy import and `/admin/members` route (lines 26, 96)
- Update `/profile` route to also handle `/profile/:id`:

```javascript
router.addRoute('/profile', pageHandler(pages.profile));
router.addRoute('/profile/:id', pageHandler(pages.profile));
```

#### 7.3 Update `profile.js`

**File:** `src/meshcore_hub/web/static/js/spa/pages/profile.js`

- If `params.id` is present → public view mode:
  - Fetch `GET /api/v1/user/profile/{id}`
  - Render read-only: name, callsign, role badges, adopted nodes list
  - If the viewer owns this profile, show "Edit Profile" link to `/profile`
- If no `params.id` → current behavior (own profile, editable)
- Role badges rendered from `profile.roles` list, displayed with labels from `config.role_names`

### Phase 8: Tests

#### 8.1 Delete test files

| File | Description |
|---|---|
| `tests/test_api/test_members.py` | Member API route tests |

#### 8.2 Delete test fixtures and helpers

| File | Fixture/Helper | Action |
|---|---|---|
| `tests/test_api/conftest.py` | `sample_member` (line 288) | Delete — creates `Member()` instance |
| `tests/test_api/conftest.py` | `sample_node_with_member_tag` (line 409) | Delete — creates `member_id` tag node |
| `tests/test_web/conftest.py` | `GET:/api/v1/members` mock response (line 154) | Delete |
| `tests/test_web/conftest.py` | `mock_http_client_with_members` (line 466) | Delete |
| `tests/test_web/conftest.py` | `web_app_with_members` (line 548) | Delete |
| `tests/test_web/conftest.py` | `client_with_members` (line 568) | Delete |
| `tests/test_web/conftest.py` | `"members": True` in features (line 20) | Keep — feature flag still used |

#### 8.3 Update test files — API tests

| File | Change |
|---|---|
| `tests/test_api/test_user_profiles.py` | Add: `GET /profiles` tests (list, pagination, roles, node_count). Add: public `GET /profile/{id}` by UUID. Add: role persistence tests. Update: existing tests for UUID-based lookup, public access. Verify `user_id` not in list response. |
| `tests/test_api/test_nodes.py` | Remove `test_filter_by_member_id` (line 171). Add or update for `adopted_by` filter if implemented. |
| `tests/test_api/test_advertisements.py` | Remove `test_filter_by_member_id` (line 217). Add or update for `adopted_by` filter if implemented. |
| `tests/test_api/test_metrics.py` | Remove `meshcore_members_total` assertion (line 59). Remove `test_members_total_reflects_database` (line 150). Add tests for `meshcore_user_profiles_total` and `meshcore_user_profiles_by_role`. |

#### 8.4 Update test files — Web tests

| File | Change |
|---|---|
| `tests/test_web/test_members.py` | **Delete** — tests the old member page |
| `tests/test_web/test_features.py` | Keep members feature flag tests (feature still exists). Update any tests that assert member-related content in sitemap/nav. |
| `tests/test_web/test_advertisements.py` | Remove `test_advertisements_with_member_filter` (line 49) and related assertions. |
| `tests/test_web/test_oidc.py` | Update `test_post_blocked_for_member` (line 196) — uses `POST /api/v1/members` which is being removed. Change to use a different write endpoint. |

#### 8.5 Update test files — Common tests

| File | Change |
|---|---|
| `tests/test_common/test_config.py` | Remove `test_members_file` (line 61) — property being deleted |
| `tests/test_common/test_i18n.py` | Remove `"members"` from required sections (line 110). Remove `"admin_members"` from required sections (line 114). Keep `entities.members` assertion if it remains in en.json. |

#### 8.6 Run commands

```bash
source .venv/bin/activate
pytest tests/test_api/test_user_profiles.py -v
pytest tests/test_api/ -v
pytest tests/test_web/ -v
pytest tests/test_common/ -v
pre-commit run --all-files
```

### Phase 9: Documentation

#### 9.1 Update files

| File | Changes |
|---|---|
| `SCHEMAS.md` | Remove Member schemas, add `roles` to UserProfile schemas, document new endpoints (`GET /profiles`, updated `GET /profile/{id}`), remove `member_id` query param docs |
| `docs/upgrading.md` | Breaking change: Member model/table removed, `member_id` tags no longer supported, seed files changed, Prometheus metric renamed |
| `docs/seeding.md` | Remove member seeding section, remove `member_id` tag from seed format examples |
| `AGENTS.md` | Update project structure (remove Member files), update env vars (remove member refs), update database conventions, remove `member_id` from standard node tags table, add `roles` to UserProfile model |
| `README.md` | Remove member-related references, update feature descriptions |

---

## File Change Summary

| # | File | Action | Phase |
|---|------|--------|-------|
| 1 | `common/models/user_profile.py` | Modify — add `roles` column | 1 |
| 2 | `alembic/versions/*.py` | Create — add roles, drop members | 1 |
| 3 | `api/profile_utils.py` | **Create** — shared `get_or_create_profile` | 2 |
| 4 | `api/routes/user_profiles.py` | Modify — shared util, new endpoints, public access, route ordering | 3 |
| 5 | `api/routes/adoptions.py` | Modify — shared util | 2 |
| 6 | `common/schemas/user_profiles.py` | Modify — add `roles`, `UserProfilePublic`, list schemas | 3 |
| 7 | `api/routes/nodes.py` | Modify — replace `member_id` filter with `adopted_by` | 3 |
| 8 | `api/routes/advertisements.py` | Modify — replace `member_id` filter with `adopted_by` | 3 |
| 9 | `web/app.py` | Modify — endpoint access map, sitemap, map data endpoint, SPA config role names | 4 |
| 10 | `common/models/member.py` | **Delete** | 5 |
| 11 | `common/schemas/members.py` | **Delete** | 5 |
| 12 | `api/routes/members.py` | **Delete** | 5 |
| 13 | `collector/member_import.py` | **Delete** | 5 |
| 14 | `web/static/js/spa/pages/admin/members.js` | **Delete** | 5 |
| 15 | `seed/members.yaml` | **Delete** | 5 |
| 16 | `example/seed/members.yaml` | **Delete** | 5 |
| 17 | `common/models/__init__.py` | Modify — remove Member export | 5 |
| 18 | `common/schemas/__init__.py` | Modify — remove member schemas | 5 |
| 19 | `api/routes/__init__.py` | Modify — remove members router | 5 |
| 20 | `collector/cli.py` | Modify — remove member CLI commands | 5 |
| 21 | `common/config.py` | Modify — remove `members_file` | 5 |
| 22 | `api/metrics.py` | Modify — replace members metric with profiles metric | 5 |
| 23 | `web/templates/spa.html` | Modify — remove admin members nav | 5 |
| 24 | `web/static/js/spa/pages/admin/index.js` | Modify — remove members card | 5 |
| 25 | `web/static/locales/en.json` | Modify — remove member keys, add new keys | 5 |
| 26 | `seed/node_tags.yaml` | Modify — remove `member_id` tags | 5 |
| 27 | `docker-compose.yml` | Modify — update seed service comment | 5 |
| 28 | `web/static/js/spa/pages/nodes.js` | Modify — remove member filter/display | 6 |
| 29 | `web/static/js/spa/pages/advertisements.js` | Modify — remove member filter/display | 6 |
| 30 | `web/static/js/spa/pages/map.js` | Modify — remove member filter, use adoption data | 6 |
| 31 | `web/static/js/spa/pages/members.js` | **Rewrite** — UserProfile-backed | 7 |
| 32 | `web/static/js/spa/app.js` | Modify — remove admin members, add profile/:id | 7 |
| 33 | `web/static/js/spa/pages/profile.js` | Modify — public view mode | 7 |
| 34 | `tests/test_api/test_members.py` | **Delete** | 8 |
| 35 | `tests/test_web/test_members.py` | **Delete** | 8 |
| 36 | `tests/test_api/conftest.py` | Modify — remove member fixtures | 8 |
| 37 | `tests/test_web/conftest.py` | Modify — remove member mock fixtures | 8 |
| 38 | `tests/test_api/test_user_profiles.py` | Modify — new endpoint tests | 8 |
| 39 | `tests/test_api/test_nodes.py` | Modify — remove member_id filter test | 8 |
| 40 | `tests/test_api/test_advertisements.py` | Modify — remove member_id filter test | 8 |
| 41 | `tests/test_api/test_metrics.py` | Modify — replace member metric tests | 8 |
| 42 | `tests/test_web/test_features.py` | Modify — update member feature tests | 8 |
| 43 | `tests/test_web/test_advertisements.py` | Modify — remove member filter test | 8 |
| 44 | `tests/test_web/test_oidc.py` | Modify — use different endpoint for POST test | 8 |
| 45 | `tests/test_common/test_config.py` | Modify — remove members_file test | 8 |
| 46 | `tests/test_common/test_i18n.py` | Modify — remove member section tests | 8 |
| 47 | `SCHEMAS.md` | Modify | 9 |
| 48 | `docs/upgrading.md` | Modify | 9 |
| 49 | `docs/seeding.md` | Modify | 9 |
| 50 | `AGENTS.md` | Modify | 9 |
| 51 | `README.md` | Modify | 9 |

---

## Execution Order

1. Phase 1: Database & model changes (model + migration)
2. Phase 2: Shared utility refactor
3. Phase 3: API endpoint changes (new endpoints, schema changes, replace member_id filters)
4. Phase 4: Web app updates (access map, map data, SPA config)
5. Phase 5: Remove Members infrastructure (delete files, update exports, metrics, CLI, seed data)
6. Phase 6: Frontend — replace member_id references (nodes, ads, map pages)
7. Phase 7: Frontend — members page rewrite & profile page extension
8. Phase 8: Tests
9. Phase 9: Documentation
10. `pre-commit run --all-files` + `pytest`
