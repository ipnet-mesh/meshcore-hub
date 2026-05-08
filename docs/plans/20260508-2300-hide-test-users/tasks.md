# Tasks: Hide Users with "test" OIDC Role

## Implementation

- [ ] **T1: Add `oidc_role_test` to `WebSettings`** (`src/meshcore_hub/common/config.py`)
  - Add `oidc_role_test: str = Field(default="test", description="IdP role name for test users")` to `WebSettings`
  - Follow existing pattern of `oidc_role_admin`, `oidc_role_operator`, `oidc_role_member`

- [ ] **T2: Wire `oidc_role_test` into `app.state`** (`src/meshcore_hub/web/app.py`)
  - Add `app.state.oidc_role_test = settings.oidc_role_test` in both OIDC-enabled branch (~line 418-420) and OIDC-disabled branch (~line 423-425)
  - Add `"test": app.state.oidc_role_test` to `role_names` dict in `_build_config_json()` (~line 241)

- [ ] **T3: Exclude test users from dashboard stats** (`src/meshcore_hub/api/routes/dashboard.py`)
  - In `get_stats()`, read `test_role = get_web_settings().oidc_role_test` alongside existing `operator_role`/`member_role`
  - Add `~UserProfile.roles.contains(test_role)` filter to `total_operators` and `total_members` count queries
  - Guard: only apply filter when `test_role` is non-empty (`if test_role:`)

- [ ] **T4: Add `exclude_test` filter to profiles list endpoint** (`src/meshcore_hub/api/routes/user_profiles.py`)
  - Add `exclude_test: bool = Query(default=True)` parameter to `list_profiles()`
  - Import `get_web_settings` from config
  - Read `test_role = get_web_settings().oidc_role_test`
  - Filter both count query and data query: `if exclude_test and test_role: query = query.where(~UserProfile.roles.contains(test_role))`

- [ ] **T5: Client-side defense-in-depth filter in Members page** (`src/meshcore_hub/web/static/js/spa/pages/members.js`)
  - Import `config` from `../app.js` (or access via existing pattern)
  - Filter out profiles where `p.roles` includes `config.role_names.test`
  - Use filtered list for rendering and total badge

## Tests

- [ ] **T6: Dashboard stats tests** (`tests/test_api/test_dashboard.py`)
  - Test: users with test role excluded from `total_operators` and `total_members`
  - Test: users without test role still counted normally
  - Test: empty `oidc_role_test` does not filter any users

- [ ] **T7: User profiles list tests** (`tests/test_api/test_user_profiles.py`)
  - Test: `exclude_test=true` (default) filters test users from list
  - Test: `exclude_test=false` includes test users
  - Test: `total` count in paginated response excludes test users
  - Test: empty `oidc_role_test` does not filter

- [ ] **T8: Frontend config test** (`tests/test_web/`)
  - Test: `/api/v1/web/config` response includes `role_names.test`

## Documentation & Quality

- [ ] **T9: Update documentation** (`AGENTS.md`, `.env.example`)
  - Add `OIDC_ROLE_TEST` to environment variables table in `AGENTS.md`
  - Add `OIDC_ROLE_TEST` entry to `.env.example`

- [ ] **T10: Run quality checks**
  - `pre-commit run --all-files`
  - `pytest tests/test_api/test_dashboard.py tests/test_api/test_user_profiles.py`
