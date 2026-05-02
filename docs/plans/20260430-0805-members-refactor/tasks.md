# Replace Members with UserProfile — Task Checklist

**Plan:** `docs/plans/20260430-0805-members-refactor/plan.md`
**Status:** Not Started

---

## Phase 1: Database & Model Changes

- [ ] **1.1** `src/meshcore_hub/common/models/user_profile.py` — Add `roles: Mapped[Optional[str]]` column (nullable `Text`) and `role_list` property that parses comma-separated string into `list[str]`
- [ ] **1.2** Generate Alembic migration — `meshcore-hub db revision --autogenerate -m "add roles to user_profiles, drop members"`, then edit to: add `roles` column to `user_profiles`, drop `members` table
- [ ] **1.3** Run `meshcore-hub db upgrade` and verify migration applies cleanly

## Phase 2: Shared Utility Refactor

- [ ] **2.1** Create `src/meshcore_hub/api/profile_utils.py` — Shared `get_or_create_profile()` helper: looks up by `user_id`, creates if missing (with name from `X-User-Name`), updates `roles` from `X-User-Roles` on every call
- [ ] **2.2** `src/meshcore_hub/api/routes/user_profiles.py` — Remove local `_get_or_create_profile`, import shared helper from `profile_utils.py`
- [ ] **2.3** `src/meshcore_hub/api/routes/adoptions.py` — Remove local `_get_or_create_profile`, import shared helper from `profile_utils.py`

## Phase 3: API Endpoint Changes

- [ ] **3.1** `src/meshcore_hub/common/schemas/user_profiles.py` — Add `roles` field to `UserProfileRead`, create `UserProfilePublic` (omits `user_id`), `UserProfileListItem` (with `node_count`), `UserProfileList`, and `UserProfilePublicWithNodes`; update `UserProfileWithNodes` to include `roles`
- [ ] **3.2** `src/meshcore_hub/api/routes/user_profiles.py` — Add `GET /profiles` endpoint (list all profiles, `RequireRead`, paginated, ordered by `name`, returns `UserProfileList` with `node_count`); register BEFORE `GET /profile/{profile_id}` to avoid route shadowing
- [ ] **3.3** `src/meshcore_hub/api/routes/user_profiles.py` — Update `GET /profile/{profile_id}` to accept profile UUID (not `user_id`), remove `_verify_owner` for GET, allow unauthenticated access, return `UserProfilePublicWithNodes` for public or `UserProfileWithNodes` for owner
- [ ] **3.4** `src/meshcore_hub/api/routes/user_profiles.py` — Update `PUT /profile/{profile_id}` to accept profile UUID, lookup by UUID, verify owner or admin
- [ ] **3.5** `src/meshcore_hub/api/routes/nodes.py` — Remove `member_id` query parameter (line 44), add optional `adopted_by` query parameter filtering by `UserProfileNode.user_profile_id`
- [ ] **3.6** `src/meshcore_hub/api/routes/advertisements.py` — Remove `member_id` query parameter (lines 53-54), add optional `adopted_by` query parameter

## Phase 4: Web App Updates

- [ ] **4.1** `src/meshcore_hub/web/app.py` — Update endpoint access map: remove `v1/members` entry, add `v1/user/profiles` with GET open; update `v1/user/profile` to allow unauthenticated GET
- [ ] **4.2** `src/meshcore_hub/web/app.py` — Update map data endpoint (lines 658-740): replace `/api/v1/members` fetch + `member_id` tag lookup with `/api/v1/user/profiles` + adoption resolution; populate `owner` from profile data; remove `member_id` field from map node objects; replace `members_list` with `profiles` if needed
- [ ] **4.3** `src/meshcore_hub/web/app.py` — In `_build_config_json()`: add `role_names` dict with `operator`, `member`, `admin` values from OIDC settings

## Phase 5: Remove Members Infrastructure

- [ ] **5.1** Delete `src/meshcore_hub/common/models/member.py`
- [ ] **5.2** Delete `src/meshcore_hub/common/schemas/members.py`
- [ ] **5.3** Delete `src/meshcore_hub/api/routes/members.py`
- [ ] **5.4** Delete `src/meshcore_hub/collector/member_import.py`
- [ ] **5.5** Delete `src/meshcore_hub/web/static/js/spa/pages/admin/members.js`
- [ ] **5.6** Delete `seed/members.yaml`
- [ ] **5.7** Delete `example/seed/members.yaml`
- [ ] **5.8** `src/meshcore_hub/common/models/__init__.py` — Remove `Member` import and export
- [ ] **5.9** `src/meshcore_hub/common/schemas/__init__.py` — Remove `MemberCreate`, `MemberUpdate`, `MemberRead`, `MemberList` imports and exports
- [ ] **5.10** `src/meshcore_hub/api/routes/__init__.py` — Remove `members_router` import and `include_router` call
- [ ] **5.11** `src/meshcore_hub/collector/cli.py` — Remove `import_members_cmd` (`import-members` command), remove member import from `seed` command, remove `--members` flag and member inclusion from `truncate` command, remove `Member` import and truncation logic
- [ ] **5.12** `src/meshcore_hub/common/config.py` — Remove `members_file` property (lines 184-189)
- [ ] **5.13** `src/meshcore_hub/api/metrics.py` — Remove `Member` import, replace `meshcore_members_total` gauge with `meshcore_user_profiles_total` and `meshcore_user_profiles_by_role`
- [ ] **5.14** `src/meshcore_hub/web/templates/spa.html` — Remove admin Members nav link from both mobile and desktop admin menus
- [ ] **5.15** `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` — Remove members admin card/link (lines 51-59)
- [ ] **5.16** `src/meshcore_hub/web/static/locales/en.json` — Remove `members.*` and `admin_members.*` sections; add `members_page.*` and `user_profile.*` keys; keep `entities.members` / `entities.member`
- [ ] **5.17** `seed/node_tags.yaml` — Remove all 18 `member_id:` key-value entries
- [ ] **5.18** `docker-compose.yml` — Update seed service comment to remove members.yaml reference

## Phase 6: Frontend — Replace member_id References

- [ ] **6.1** `src/meshcore_hub/web/static/js/spa/pages/nodes.js` — Remove `/api/v1/members` fetch, `member_id` query param, `showMembers` flag, member filter dropdown, member name display, "Member" column header
- [ ] **6.2** `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` — Remove same member-related code as nodes page: members fetch, filter dropdown, member display
- [ ] **6.3** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Remove member filter dropdown, `memberFilter` logic, `node.member_id` filter comparison; update owner display from adoption data

## Phase 7: Frontend — Members Page & Profile Page

- [ ] **7.1** `src/meshcore_hub/web/static/js/spa/pages/members.js` — Rewrite: fetch `/api/v1/user/profiles`, split into Operators/Members groups using `config.role_names`, render tiles with name/callsign/node_count, link to `/profile/${id}`, responsive grid layout
- [ ] **7.2** `src/meshcore_hub/web/static/js/spa/app.js` — Remove `adminMembers` lazy import and `/admin/members` route; add `/profile/:id` route
- [ ] **7.3** `src/meshcore_hub/web/static/js/spa/pages/profile.js` — Add public view mode: when `params.id` present, fetch profile by UUID, render read-only view with role badges and adopted nodes; show "Edit Profile" link for owner; no `params.id` = current editable behavior

## Phase 8: Tests

- [ ] **8.1** Delete `tests/test_api/test_members.py`
- [ ] **8.2** Delete `tests/test_web/test_members.py`
- [ ] **8.3** `tests/test_api/conftest.py` — Remove `sample_member` fixture (line 288) and `sample_node_with_member_tag` fixture (line 409)
- [ ] **8.4** `tests/test_web/conftest.py` — Remove `GET:/api/v1/members` mock response (line 154), `mock_http_client_with_members` (line 466), `web_app_with_members` (line 548), `client_with_members` (line 568)
- [ ] **8.5** `tests/test_api/test_user_profiles.py` — Add tests for `GET /profiles` (list, pagination, roles, node_count, `user_id` not exposed); add public `GET /profile/{id}` by UUID tests; add role persistence tests; update existing tests for UUID-based lookup
- [ ] **8.6** `tests/test_api/test_nodes.py` — Remove `test_filter_by_member_id` (line 171); add `adopted_by` filter tests if implemented
- [ ] **8.7** `tests/test_api/test_advertisements.py` — Remove `test_filter_by_member_id` (line 217); add `adopted_by` filter tests if implemented
- [ ] **8.8** `tests/test_api/test_metrics.py` — Remove `meshcore_members_total` assertion (line 59) and `test_members_total_reflects_database` (line 150); add tests for `meshcore_user_profiles_total` and `meshcore_user_profiles_by_role`
- [ ] **8.9** `tests/test_web/test_features.py` — Keep members feature flag tests; update assertions for member content in sitemap/nav
- [ ] **8.10** `tests/test_web/test_advertisements.py` — Remove `test_advertisements_with_member_filter` (line 49)
- [ ] **8.11** `tests/test_web/test_oidc.py` — Update `test_post_blocked_for_member` (line 196) to use a different write endpoint instead of `POST /api/v1/members`
- [ ] **8.12** `tests/test_common/test_config.py` — Remove `test_members_file` (line 61)
- [ ] **8.13** `tests/test_common/test_i18n.py` — Remove `"members"` and `"admin_members"` from required sections; keep `entities.members` assertion

## Phase 9: Documentation

- [ ] **9.1** `SCHEMAS.md` — Remove Member schemas; add `roles` to UserProfile schemas; document `GET /profiles` and updated `GET /profile/{id}`; remove `member_id` query param docs
- [ ] **9.2** `docs/upgrading.md` — Add breaking change section: Member model/table removed, `member_id` tags no longer supported, seed files changed, Prometheus metric renamed
- [ ] **9.3** `docs/seeding.md` — Remove member seeding section; remove `member_id` tag from seed format examples
- [ ] **9.4** `AGENTS.md` — Update project structure (remove Member files), update env vars, remove `member_id` from standard node tags table, add `roles` to UserProfile model example
- [ ] **9.5** `README.md` — Remove member-related references, update feature descriptions

## Phase 10: Verification

- [ ] **10.1** Run `pytest tests/test_api/ -v`
- [ ] **10.2** Run `pytest tests/test_web/ -v`
- [ ] **10.3** Run `pytest tests/test_common/ -v`
- [ ] **10.4** Run `pytest` (full suite)
- [ ] **10.5** Run `pre-commit run --all-files`

---

## File Change Summary

| # | File | Action | Phase(s) |
|---|------|--------|----------|
| 1 | `src/meshcore_hub/common/models/user_profile.py` | Modify | 1 |
| 2 | `alembic/versions/*.py` | Create | 1 |
| 3 | `src/meshcore_hub/api/profile_utils.py` | Create | 2 |
| 4 | `src/meshcore_hub/api/routes/user_profiles.py` | Modify | 2, 3 |
| 5 | `src/meshcore_hub/api/routes/adoptions.py` | Modify | 2 |
| 6 | `src/meshcore_hub/common/schemas/user_profiles.py` | Modify | 3 |
| 7 | `src/meshcore_hub/api/routes/nodes.py` | Modify | 3 |
| 8 | `src/meshcore_hub/api/routes/advertisements.py` | Modify | 3 |
| 9 | `src/meshcore_hub/web/app.py` | Modify | 4 |
| 10 | `src/meshcore_hub/common/models/member.py` | Delete | 5 |
| 11 | `src/meshcore_hub/common/schemas/members.py` | Delete | 5 |
| 12 | `src/meshcore_hub/api/routes/members.py` | Delete | 5 |
| 13 | `src/meshcore_hub/collector/member_import.py` | Delete | 5 |
| 14 | `src/meshcore_hub/web/static/js/spa/pages/admin/members.js` | Delete | 5 |
| 15 | `seed/members.yaml` | Delete | 5 |
| 16 | `example/seed/members.yaml` | Delete | 5 |
| 17 | `src/meshcore_hub/common/models/__init__.py` | Modify | 5 |
| 18 | `src/meshcore_hub/common/schemas/__init__.py` | Modify | 5 |
| 19 | `src/meshcore_hub/api/routes/__init__.py` | Modify | 5 |
| 20 | `src/meshcore_hub/collector/cli.py` | Modify | 5 |
| 21 | `src/meshcore_hub/common/config.py` | Modify | 5 |
| 22 | `src/meshcore_hub/api/metrics.py` | Modify | 5 |
| 23 | `src/meshcore_hub/web/templates/spa.html` | Modify | 5 |
| 24 | `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` | Modify | 5 |
| 25 | `src/meshcore_hub/web/static/locales/en.json` | Modify | 5 |
| 26 | `seed/node_tags.yaml` | Modify | 5 |
| 27 | `docker-compose.yml` | Modify | 5 |
| 28 | `src/meshcore_hub/web/static/js/spa/pages/nodes.js` | Modify | 6 |
| 29 | `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` | Modify | 6 |
| 30 | `src/meshcore_hub/web/static/js/spa/pages/map.js` | Modify | 6 |
| 31 | `src/meshcore_hub/web/static/js/spa/pages/members.js` | Rewrite | 7 |
| 32 | `src/meshcore_hub/web/static/js/spa/app.js` | Modify | 7 |
| 33 | `src/meshcore_hub/web/static/js/spa/pages/profile.js` | Modify | 7 |
| 34 | `tests/test_api/test_members.py` | Delete | 8 |
| 35 | `tests/test_web/test_members.py` | Delete | 8 |
| 36 | `tests/test_api/conftest.py` | Modify | 8 |
| 37 | `tests/test_web/conftest.py` | Modify | 8 |
| 38 | `tests/test_api/test_user_profiles.py` | Modify | 8 |
| 39 | `tests/test_api/test_nodes.py` | Modify | 8 |
| 40 | `tests/test_api/test_advertisements.py` | Modify | 8 |
| 41 | `tests/test_api/test_metrics.py` | Modify | 8 |
| 42 | `tests/test_web/test_features.py` | Modify | 8 |
| 43 | `tests/test_web/test_advertisements.py` | Modify | 8 |
| 44 | `tests/test_web/test_oidc.py` | Modify | 8 |
| 45 | `tests/test_common/test_config.py` | Modify | 8 |
| 46 | `tests/test_common/test_i18n.py` | Modify | 8 |
| 47 | `SCHEMAS.md` | Modify | 9 |
| 48 | `docs/upgrading.md` | Modify | 9 |
| 49 | `docs/seeding.md` | Modify | 9 |
| 50 | `AGENTS.md` | Modify | 9 |
| 51 | `README.md` | Modify | 9 |
