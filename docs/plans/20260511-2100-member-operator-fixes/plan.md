# Plan: Members Count Fix & Operator-Only Filters

**Date:** 2026-05-11
**Status:** Draft

## Problem

Two related issues with member/operator display in the UI:

1. **Members page count mismatch** — The badge in the upper-right corner of the Members page shows a higher count than the total of operators and members actually listed. Profiles that have neither the `operator` nor `member` role (e.g., admins with only the `admin` role, or users with no roles at all) are counted in the badge but not displayed in any group.

2. **Filter dropdowns show all members instead of operators only** — The "Member" filter on Nodes, Advertisements, and Map pages lists all non-test profiles. Since only operators can adopt nodes, this filter should only show operators and the label should read "Operator" not "Member".

## Root Cause Analysis

### Issue 1: Members Page Count

In `members.js`:

- Line 74: Fetches profiles from `/api/v1/user/profiles` (excludes test users by default)
- Line 77: Client-side defense-in-depth filter removes remaining test-role profiles
- Line 100: Badge shows `profiles.length` — **all** non-test profiles
- Lines 92-95: Only `operators` (have operator role) and `members` (have member role but NOT operator) are rendered as groups

A profile with `roles = ["admin"]` or `roles = []` passes the test filter, is counted in the badge, but is invisible on the page — it appears in neither the Operators nor Members group.

### Issue 2: Filter Dropdowns

In `nodes.js` (line 60), `advertisements.js` (line 67), and `map.js` (line 121/126):

- All fetch `/api/v1/user/profiles` with `limit: 500`
- All render every profile in the dropdown using label `filter_member_label` ("Member") and all-option `all_members` ("All Members")
- The `adopted_by` parameter filters nodes by the adopting profile's UUID — only operators can adopt nodes, so showing non-operators in the dropdown is misleading (selecting a non-operator who hasn't adopted any nodes returns zero results)

## Approach

### Fix 1: Members Page Count — Only Count Displayed Profiles

**File:** `src/meshcore_hub/web/static/js/spa/pages/members.js`

Change the badge to show the sum of operators + members actually displayed, not the total of all profiles:

```javascript
// Before (line 100):
${t('common.count_entity', { count: profiles.length, entity: t('entities.members').toLowerCase() })}

// After:
${t('common.count_entity', { count: operators.length + members.length, entity: t('entities.members').toLowerCase() })}
```

This makes the count reflect exactly what is rendered on the page. The `operators` and `members` variables are already computed at lines 92-95, before the `litRender` call at line 97. No structural change needed — only the expression on line 100 changes.

**Change:** Replace `profiles.length` with `operators.length + members.length` on line 100.

### Fix 2: Operator-Only Filter Dropdowns

For all three pages (Nodes, Advertisements, Map), filter the profiles list to only show operators and update labels.

#### 2a. Add i18n Keys

**Files:** `src/meshcore_hub/web/static/locales/en.json`, `nl.json`, `docs/i18n.md`

Add new keys under `common`:

```json
"all_operators": "All Operators",
"filter_operator_label": "Operator"
```

These replace the usage of `all_members` and `filter_member_label` in the filter dropdowns.

Dutch translations:
```json
"all_operators": "Alle Operators",
"filter_operator_label": "Operator"
```

Update `docs/i18n.md` with the new keys following the existing format.

#### 2b. Nodes Page

**File:** `src/meshcore_hub/web/static/js/spa/pages/nodes.js`

After fetching profiles (line 64), filter to operators only:

```javascript
const operatorRole = config.role_names?.operator || 'operator';
const profiles = config.oidc_enabled
    ? (results[1]?.items || []).filter(p => p.roles && p.roles.includes(operatorRole))
    : [];
```

Update the filter dropdown (lines 149-166):
- Change label from `t('common.filter_member_label')` to `t('common.filter_operator_label')`
- Change all-option from `t('common.all_members')` to `t('common.all_operators')`

#### 2c. Advertisements Page

**File:** `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`

Same pattern as Nodes. After fetching profiles (line 72), filter to operators:

```javascript
const operatorRole = config.role_names?.operator || 'operator';
const profiles = config.oidc_enabled
    ? (results[2]?.items || []).filter(p => p.roles && p.roles.includes(operatorRole))
    : [];
```

Update the filter dropdown (lines 199-216) with the same label changes.

#### 2d. Map Page

**File:** `src/meshcore_hub/web/static/js/spa/pages/map.js`

The map page gets profiles from `/map/data` (server-side fetch). Two options:

**Option A (recommended): Client-side filtering** — Filter `profiles` after receiving from `/map/data`:

```javascript
const operatorRole = config.role_names?.operator || 'operator';
const operatorProfiles = profiles.filter(p => p.roles && p.roles.includes(operatorRole));
```

Then use `operatorProfiles` in the dropdown instead of `profiles`. Update the dropdown label (line 222) and all-option (line 224).

**Option B: Server-side filtering** — Add a `?operators_only=true` parameter to `/map/data`. More robust but requires changes to the web app route handler.

Chosen: **Option A** — consistent with the other pages, simpler, and the profiles data is already available in the frontend with role information.

> **Note:** The `/map/data` endpoint currently fetches profiles without explicit `exclude_test=false`, so test users are already excluded by the API default. No server-side change needed for test exclusion. However, the profiles returned by `/map/data` only include `id`, `name`, and `callsign` (lines 723-727 of `web/app.py`) — they do NOT include `roles`. This means client-side filtering by role is **not possible** on the map page without a server-side change.

**Updated approach for Map page:** Modify the `/map/data` endpoint in `web/app.py` to include `roles` in the profile data, OR filter server-side to only return operator profiles. The simpler fix is to include `roles` in the profile dict:

```python
# web/app.py line 723-727, add roles:
profiles_by_id[profile["id"]] = {
    "id": profile.get("id"),
    "name": profile.get("name"),
    "callsign": profile.get("callsign"),
    "roles": profile.get("roles", []),  # ADD
}
```

Then the frontend can filter by role just like the other pages.

### Summary of Changes

| File | Change |
|------|--------|
| `src/meshcore_hub/web/static/js/spa/pages/members.js` | Badge counts `operators.length + members.length` instead of `profiles.length` |
| `src/meshcore_hub/web/static/js/spa/pages/nodes.js` | Filter profiles to operators; update dropdown labels |
| `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` | Filter profiles to operators; update dropdown labels |
| `src/meshcore_hub/web/static/js/spa/pages/map.js` | Filter profiles to operators; update dropdown labels |
| `src/meshcore_hub/web/app.py` | Include `roles` in profiles dict returned by `/map/data` |
| `src/meshcore_hub/web/static/locales/en.json` | Add `all_operators` and `filter_operator_label` keys |
| `src/meshcore_hub/web/static/locales/nl.json` | Add Dutch translations for new keys |
| `docs/i18n.md` | Document new `all_operators` and `filter_operator_label` keys |

### Tests to Update

| Test File | Change |
|-----------|--------|
| `tests/test_common/test_i18n.py` | Add tests for new `all_operators` and `filter_operator_label` keys |
| `tests/test_web/` | Verify map data includes roles in profiles; verify operator filtering |

### Edge Cases

- **No operators exist** — Filter dropdown should not appear (same as current "no profiles" guard)
- **User has both operator and admin roles** — Should appear in the operator dropdown (has operator role)
- **User has member role only** — Should NOT appear in the operator filter dropdown
- **Map page profile filtering** — Must work even though map profiles have minimal data (just id/name/callsign/roles)

### Out of Scope

- API-level operator filtering (e.g., `?role=operator` parameter on `/api/v1/user/profiles`) — client-side filtering is sufficient
- Refactoring the filter dropdown into a shared component
- Changes to the Members page grouping logic (admin-only users still won't appear in either group)

## Implementation Order

1. Add `all_operators` and `filter_operator_label` to `en.json`, `nl.json`, and `docs/i18n.md`
2. Fix Members page count badge (`members.js`)
3. Filter to operators in Nodes page (`nodes.js`) and update labels
4. Filter to operators in Advertisements page (`advertisements.js`) and update labels
5. Add `roles` to map data profiles (`web/app.py`)
6. Filter to operators in Map page (`map.js`) and update labels
7. Update i18n tests
8. Run `pre-commit run --all-files` and `pytest`
