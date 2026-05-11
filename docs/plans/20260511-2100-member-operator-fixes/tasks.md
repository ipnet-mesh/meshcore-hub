# Tasks: Members Count Fix & Operator-Only Filters

## Implementation

- [ ] **T1: Add i18n keys** (`src/meshcore_hub/web/static/locales/en.json`, `nl.json`, `docs/i18n.md`)
  - Add to `en.json` under `common`: `"all_operators": "All Operators"`, `"filter_operator_label": "Operator"`
  - Add to `nl.json` under `common`: `"all_operators": "Alle Operators"`, `"filter_operator_label": "Operator"`
  - Document both keys in `docs/i18n.md` following existing format

- [ ] **T2: Fix Members page count badge** (`src/meshcore_hub/web/static/js/spa/pages/members.js`)
  - Line 100: Change `profiles.length` to `operators.length + members.length` in the count badge

- [ ] **T3: Filter to operators in Nodes page** (`src/meshcore_hub/web/static/js/spa/pages/nodes.js`)
  - After fetching profiles (~line 64), filter to operators only:
    ```javascript
    const operatorRole = config.role_names?.operator || 'operator';
    const profiles = config.oidc_enabled
        ? (results[1]?.items || []).filter(p => p.roles && p.roles.includes(operatorRole))
        : [];
    ```
  - Update filter dropdown (~lines 149-166): change `filter_member_label` → `filter_operator_label`, `all_members` → `all_operators`

- [ ] **T4: Filter to operators in Advertisements page** (`src/meshcore_hub/web/static/js/spa/pages/advertisements.js`)
  - After fetching profiles (~line 72), filter to operators only:
    ```javascript
    const operatorRole = config.role_names?.operator || 'operator';
    const profiles = config.oidc_enabled
        ? (results[2]?.items || []).filter(p => p.roles && p.roles.includes(operatorRole))
        : [];
    ```
  - Update filter dropdown (~lines 199-216): change `filter_member_label` → `filter_operator_label`, `all_members` → `all_operators`

- [ ] **T5: Add `roles` to map data profiles** (`src/meshcore_hub/web/app.py`)
  - In `/map/data` endpoint (~lines 723-727), add `"roles": profile.get("roles", [])` to the `profiles_by_id` dict

- [ ] **T6: Filter to operators in Map page** (`src/meshcore_hub/web/static/js/spa/pages/map.js`)
  - After receiving profiles from `/map/data`, filter to operators:
    ```javascript
    const operatorRole = config.role_names?.operator || 'operator';
    const operatorProfiles = profiles.filter(p => p.roles && p.roles.includes(operatorRole));
    ```
  - Use `operatorProfiles` in the dropdown instead of `profiles`
  - Update dropdown (~lines 220-232): change `filter_member_label` → `filter_operator_label`, `all_members` → `all_operators`

## Tests

- [ ] **T7: Add i18n tests** (`tests/test_common/test_i18n.py`)
  - Test `common.all_operators` key exists and resolves correctly
  - Test `common.filter_operator_label` key exists and resolves correctly

- [ ] **T8: Run quality checks**
  - `pre-commit run --all-files`
  - `pytest tests/test_common/ tests/test_web/`
