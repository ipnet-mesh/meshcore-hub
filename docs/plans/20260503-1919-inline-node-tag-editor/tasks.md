# Tasks — Inline Node Tag Editor

## Phase 1: Refactor Tag API Authorization

- [ ] **1.1** Add `_check_tag_access` helper to `src/meshcore_hub/api/routes/node_tags.py`
  - Accepts `(session, caller_info, request, node_id)`
  - Returns `None` if admin role present
  - Queries `UserProfile` by `caller_id`, then `UserProfileNode` for adoption record
  - Raises 403 "You can only edit tags on nodes you have adopted" if no adoption found

- [ ] **1.2** Update `create_node_tag` — replace `RequireAdmin` with `RequireOperatorOrAdmin`, add `request: Request`, call `_check_tag_access` after node lookup, call `validate_and_coerce_tag_value` before creating tag (422 on failure)

- [ ] **1.3** Update `update_node_tag` — same auth changes as 1.2. Compute effective `(value, value_type)`, call `validate_and_coerce_tag_value` before applying updates (422 on failure)

- [ ] **1.4** Update `delete_node_tag` — replace `RequireAdmin` with `RequireOperatorOrAdmin`, add ownership check

- [ ] **1.5** Remove unused endpoints: `get_node_tag`, `move_node_tag`, `copy_all_tags`, `delete_all_node_tags`

- [ ] **1.6** Update imports: remove `NodeTagMove`, `NodeTagsCopyResult`, `RequireAdmin`; add `RequireOperatorOrAdmin`, `Request`, `UserProfile`, `UserProfileNode`, `status` from fastapi; add `validate_and_coerce_tag_value` from schemas

## Phase 2: Remove Unused Schemas + Add Validation

- [ ] **2.1** Remove `NodeTagMove` class from `src/meshcore_hub/common/schemas/nodes.py`

- [ ] **2.2** Remove `NodeTagsCopyResult` class from `src/meshcore_hub/common/schemas/nodes.py`

- [ ] **2.3** Add `validate_and_coerce_tag_value(value, value_type)` to `src/meshcore_hub/common/schemas/nodes.py`
  - `value is None or ""` → return as-is (skip validation)
  - `type == "number"` → validate with `float()`, raise `ValueError` on failure, return original string
  - `type == "boolean"` → accept true/false/yes/no/1/0 (case-insensitive), coerce to "true"/"false", raise `ValueError` on failure
  - `type == "string"` → pass through unchanged

## Phase 3: Update Web App API Proxy Access

- [ ] **3.1** In `_build_endpoint_access()` in `src/meshcore_hub/web/app.py`, change `"v1/nodes/"` write methods from `admin` to `operator_admin`

- [ ] **3.2** Remove admin route protection block from `spa_catchall` (L1041–1057)

## Phase 4: Add Icon Functions

- [ ] **4.1** Add `iconPlus` to `src/meshcore_hub/web/static/js/spa/icons.js`

- [ ] **4.2** Add `iconEdit` to `src/meshcore_hub/web/static/js/spa/icons.js`

- [ ] **4.3** Add `iconTrash` to `src/meshcore_hub/web/static/js/spa/icons.js`

## Phase 5: Fix API Client Auth Response Handler

- [ ] **5.1** In `src/meshcore_hub/web/static/js/spa/api.js`, change `checkAuthResponse` condition from `response.status === 401 || response.status === 403` to `response.status === 401`

## Phase 6: Build Inline Tag Editor

- [ ] **6.1** Update imports in `src/meshcore_hub/web/static/js/spa/pages/node-detail.js`: add `apiPut` from api.js, add `iconPlus`, `iconEdit`, `iconTrash` from icons.js

- [ ] **6.2** Add `renderDeleteTagModal` function — DaisyUI `<dialog>` with confirmation message, cannot-be-undone alert, cancel/delete buttons

- [ ] **6.3** Add `renderEditTagModal` function — DaisyUI `<dialog>` with key (disabled), value, type fields, validation error label, cancel/save buttons

- [ ] **6.4** Add `validateTagValue(value, type)` helper:
  - `type === 'number'` → `isNaN(Number(value))` check
  - `type === 'boolean'` → check against true/false/yes/no/1/0
  - Returns error message string or `null`

- [ ] **6.5** Replace tags card (L207–213) with editable version:
  - Compute `canEditTags` from roles and adoption status
  - When editable: add action columns (edit/delete icons) to table rows, add inline add-tag form with validation error label below table
  - When read-only: render current table unchanged
  - Append delete and edit modals after card

- [ ] **6.6** Wire up event handlers:
  - Add form submit → validate, POST, refresh, re-render
  - Edit button → populate modal, show
  - Edit submit → validate, PUT, refresh, re-render
  - Delete button → populate modal, show
  - Delete confirm → DELETE, refresh, re-render
  - Cancel buttons → close modals

- [ ] **6.7** Remove `adminTagsHtml` block (L129–133)

## Phase 7: Remove Admin UI

- [ ] **7.1** Delete `src/meshcore_hub/web/static/js/spa/pages/admin/index.js`

- [ ] **7.2** Delete `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`

- [ ] **7.3** Delete `src/meshcore_hub/web/static/js/spa/pages/admin/` directory

- [ ] **7.4** Remove `adminIndex` and `adminNodeTags` from `pages` object in `src/meshcore_hub/web/static/js/spa/app.js`

- [ ] **7.5** Remove admin route registration block from `app.js`

- [ ] **7.6** Remove admin page title entries from `updatePageTitle` in `app.js`

- [ ] **7.7** Remove `adminItem` variable and its usage from `src/meshcore_hub/web/static/js/spa/components.js` (L623–624, L647)

- [ ] **7.8** Remove unused `iconSettings` import from `components.js` (L11)

## Phase 8: Update Tests

- [ ] **8.1** Delete `tests/test_web/test_admin.py`

- [ ] **8.2** Add OIDC test fixtures to `tests/test_api/conftest.py` or `tests/test_api/test_nodes.py`:
  - `oidc_operator_headers` — `X-User-Id: operator-123`, `X-User-Roles: operator`
  - `oidc_admin_headers` — `X-User-Id: admin-456`, `X-User-Roles: admin`
  - `oidc_member_headers` — `X-User-Id: member-789`, `X-User-Roles: member`
  - Fixtures creating `UserProfile` + `UserProfileNode` for operator adoption

- [ ] **8.3** Rewrite `test_tag_crud_requires_admin` → `test_tag_crud_requires_operator_or_admin`: no headers → 401, member headers → 403

- [ ] **8.4** Update `test_create_node_tag` to use `oidc_admin_headers`

- [ ] **8.5** Remove `test_get_node_tag`

- [ ] **8.6** Update `test_update_node_tag` to use `oidc_admin_headers` with adoption

- [ ] **8.7** Update `test_delete_node_tag` to verify deletion via list endpoint (not single-get)

- [ ] **8.8** Add `test_operator_can_edit_adopted_node_tags` — POST/PUT/DELETE → success

- [ ] **8.9** Add `test_operator_cannot_edit_non_adopted_node_tags` — POST/PUT/DELETE → 403

- [ ] **8.10** Add `test_admin_can_edit_any_node_tags` — no adoption, POST → 201

- [ ] **8.11** Remove `TestMoveNodeTag` class

- [ ] **8.12** Remove `test_copy_all_tags` test (if present)

- [ ] **8.13** Remove `test_delete_all_node_tags` test (if present)

- [ ] **8.14** Add `TestTagValidation` — unit tests for `validate_and_coerce_tag_value`:
  - string pass-through, None/empty handling
  - number: valid int/float/negative, invalid string → ValueError
  - boolean: true/false/yes/no/1/0 → "true"/"false", whitespace trimming, invalid → ValueError

- [ ] **8.15** Add `TestTagValidationAPI` — integration tests for 422 responses:
  - create with invalid number/boolean → 422
  - create with valid number → 201, value stored as-is
  - create with boolean "yes" → 201, value coerced to "true"
  - update: validate new value against existing type
  - update: validate existing value against new type
  - update: validate new value against new type with coercion

## Phase 9: Update i18n

- [ ] **9.1** Remove `admin` section from `src/meshcore_hub/web/static/locales/en.json`

- [ ] **9.2** Remove `admin_node_tags` section from `en.json`

- [ ] **9.3** Remove `"admin": "Admin"` from `entities` section in `en.json`

- [ ] **9.4** Add `validation_invalid_number` and `validation_invalid_boolean` keys to `common` section in `en.json`

- [ ] **9.5** Remove `admin` section, `admin_members` section, `admin_node_tags` section, and `entities.admin` entry from `docs/i18n.md`; add validation keys; renumber sections

## Phase 10: Update Project Documentation

- [ ] **10.1** Update `AGENTS.md` — remove `/admin/` route references, `pages/admin/` directory, admin test references

- [ ] **10.2** Update `docs/upgrading.md` — add upgrade notes for auth change, removed endpoints, OIDC requirement, tag value validation/coercion

## Verification

- [ ] Run `pytest tests/test_api/test_nodes.py -v`

- [ ] Run `pytest tests/test_web/ -v`

- [ ] Run `pytest tests/test_common/test_i18n.py -v`

- [ ] Run `pre-commit run --all-files`
