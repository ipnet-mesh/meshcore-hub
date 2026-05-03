# Inline Node Tag Editor — Replace Admin Tag Pages

**Date:** 2026-05-03
**Status:** Final

## Overview

Replace the dedicated `/admin/node-tags` page with an inline tag editor embedded directly in the Node detail page (`/nodes/:publicKey`). This eliminates the separate admin page round-trip and makes tag management contextual and immediate.

Simultaneously remove all `/admin/` routes, UI, and associated API endpoints that are no longer needed. Refactor the tag API authorization from `RequireAdmin` to `RequireOperatorOrAdmin` (OIDC role-based), with operators restricted to editing tags on their own adopted nodes only.

The current `RequireAdmin` dependency has a fallback: when no admin key is configured, it allows open access (`return token or ""`). This means tag writes are currently possible without any authentication in keyless deployments. The new `RequireOperatorOrAdmin` always requires OIDC authentication (via `X-User-Id` header injected by the web proxy). Tag writes now always require OIDC. Deployments without OIDC have read-only tags via the web UI and get 401 on direct API write access.

## Decisions

1. **Inline editor on node detail page** — Tags are edited in-place on the existing Tags card in `node-detail.js`. No navigation to a separate page. The editor is a compact, collapsible section below the existing read-only tags table.

2. **Permission model: admin vs operator** — Admins can edit tags on any node. Operators can only edit tags on nodes they have adopted. Both require OIDC authentication. The old `RequireAdmin` (API-key-based) auth is replaced by `RequireOperatorOrAdmin` with an ownership check.

3. **Delete confirmation overlay** — Tag deletion uses a DaisyUI `<dialog>` modal (same pattern as the existing admin page). This prevents accidental deletion on both desktop and mobile.

4. **Remove `/admin/` entirely** — The `/admin/` index page, `/admin/node-tags` page, route registrations, SPA modules, and the admin nav link in the user dropdown are all removed. The SPA catch-all's admin route protection is also removed.

5. **Remove move/copy-all/delete-all API endpoints** — The move-tag, copy-all-tags, and delete-all-tags API endpoints (`PUT .../move`, `POST .../copy-to/...`, `DELETE .../tags` bulk) are removed. These were only used by the admin page. The inline editor provides single-tag CRUD (create, read, update, delete) which is sufficient.

6. **Remove unused schemas** — `NodeTagMove` and `NodeTagsCopyResult` schemas are removed along with their API endpoints.

7. **Compact editor design** — The inline editor uses a compact grid layout: key input, value input, type select, and add button in a single row on desktop (4-column grid). On mobile it stacks to a single column. Edit/delete actions are inline icon buttons in the tags table rows (replacing the static read-only table). The editor section is always visible when the user has edit permission — no separate "edit mode" toggle.

8. **No flash-message redirects** — Unlike the admin page which used URL query params for flash messages and full page reloads, the inline editor uses in-place DOM updates with toast-style feedback (success/error alerts rendered inline).

9. **API proxy access control** — The web app's `check_api_access` endpoint mapping gets entries for tag write paths with `operator_admin` access, so the proxy layer also enforces permissions before requests reach the API.

10. **Fix `checkAuthResponse` to only redirect on 401** — Currently `api.js:33` redirects to `/auth/login` on both 401 and 403. Since 403 from the API means "forbidden" (user is authenticated but lacks permission — e.g., operator editing a non-adopted node), redirecting to login is wrong. Change the condition to only redirect on 401. This fixes the inline tag editor so 403 permission errors are displayed as inline error alerts instead of causing a confusing redirect.

11. **Add icon functions for edit/delete/add buttons** — `icons.js` currently has no pencil (edit), trash (delete), or plus (add) icons. Three new SVG icon functions are added: `iconPlus`, `iconEdit`, `iconTrash`. These follow the existing Heroicons-style SVG pattern used by all other icons in the file.

12. **Validate and coerce tag values by type** — Tag values are validated and coerced on both client and server. On the server, a `validate_and_coerce_tag_value()` function enforces type constraints: `number` values must parse as `float()`, `boolean` values must be one of `true`, `false`, `yes`, `no`, `1`, `0` (case-insensitive) and are normalized to `"true"`/`"false"`, `string` values pass through. Invalid values return `422`. The client mirrors the same rules, blocking submission with inline error messages. Validation only runs on write (create/update); existing data is not retroactively validated. Empty/None values skip validation.

## Terminology

| Term | Meaning |
|------|---------|
| Inline editor | Tag editing UI embedded in the node detail page |
| Admin | OIDC user with the `admin` role — can edit tags on any node |
| Operator | OIDC user with the `operator` role — can only edit tags on nodes they have adopted |
| Adopted node | A node with a record in `user_profile_nodes` linked to the operator's profile |
| Tag CRUD | Create, Read, Update, Delete operations on individual `NodeTag` records |

## Current State

### Admin Tag Page (to be removed)

| Layer | File | What it does |
|-------|------|-------------|
| SPA route | `app.js` L91–94 | Registers `/admin`, `/admin/`, `/admin/node-tags` routes (gated on `hasRole('admin')`) |
| SPA page — index | `pages/admin/index.js` | Admin landing page with card link to node-tags |
| SPA page — tags | `pages/admin/node-tags.js` | Full page tag editor with node selector, add/edit/move/copy-all/delete-all/delete modals |
| Nav dropdown | `components.js` L623–624 | "Admin" link in user dropdown (gated on `hasRole('admin')`) |
| Page titles | `app.js` L155–157 | Admin page title entries |
| Web server | `web/app.py` L1041–1057 | SPA catch-all admin route protection (redirect to login) |
| Tests | `tests/test_web/test_admin.py` | Tests for admin SPA shell serving |

### Tag API Endpoints

| Method | Path | Auth | Used by | Status |
|--------|------|------|---------|--------|
| GET | `/nodes/{pk}/tags` | `RequireRead` | Node detail, admin page | **Keep** |
| GET | `/nodes/{pk}/tags/{key}` | `RequireRead` | Not used in UI | **Remove** (unused) |
| POST | `/nodes/{pk}/tags` | `RequireAdmin` | Admin page add | **Keep, change auth** |
| PUT | `/nodes/{pk}/tags/{key}` | `RequireAdmin` | Admin page edit | **Keep, change auth** |
| PUT | `/nodes/{pk}/tags/{key}/move` | `RequireAdmin` | Admin page move | **Remove** |
| POST | `/nodes/{pk}/tags/copy-to/{dest}` | `RequireAdmin` | Admin page copy-all | **Remove** |
| DELETE | `/nodes/{pk}/tags/{key}` | `RequireAdmin` | Admin page delete | **Keep, change auth** |
| DELETE | `/nodes/{pk}/tags` | `RequireAdmin` | Admin page delete-all | **Remove** |

### Auth Dependencies (existing)

| Dependency | File | Returns | Used by |
|------------|------|---------|---------|
| `RequireRead` | `api/auth.py` L145 | Token or None | Read endpoints |
| `RequireAdmin` | `api/auth.py` L146 | Token string | Tag write endpoints (API key) |
| `RequireOperatorOrAdmin` | `api/auth.py` L253 | `(user_id, roles)` | Adoptions endpoints |
| `RequireOperator` | `api/auth.py` L252 | `(user_id, roles)` | Not used yet |

### Node Detail Page — Tags Section (current)

`node-detail.js` L107–133:

- Renders a read-only tags table (key, value, type columns)
- If user `hasRole('admin')`, shows a link to `/admin/node-tags?public_key=...`
- No inline editing capability

---

## Implementation

### Phase 1: Refactor Tag API Authorization

**File:** `src/meshcore_hub/api/routes/node_tags.py`

Replace `RequireAdmin` with `RequireOperatorOrAdmin` on write endpoints and add an ownership check for operators.

#### 1.1 Add ownership check helper

```python
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select

from meshcore_hub.api.auth import get_api_keys
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import Node, NodeTag, UserProfile, UserProfileNode


def _check_tag_access(
    session: DbSession,
    caller_info: tuple[str, list[str]],
    request: Request,
    node_id: str,
) -> None:
    """Raise 403 if operator tries to edit tags on a non-adopted node.

    Admins bypass the ownership check.
    """
    caller_id, roles = caller_info
    admin_role: str = getattr(request.app.state, "oidc_role_admin", "admin")
    if admin_role in roles:
        return

    # Operator must have adopted this node
    profile_query = select(UserProfile).where(UserProfile.user_id == caller_id)
    profile = session.execute(profile_query).scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit tags on nodes you have adopted",
        )

    adoption_query = select(UserProfileNode).where(
        (UserProfileNode.user_profile_id == profile.id)
        & (UserProfileNode.node_id == node_id)
    )
    adoption = session.execute(adoption_query).scalar_one_or_none()
    if not adoption:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit tags on nodes you have adopted",
        )
```

#### 1.2 Update `create_node_tag` (L64)

Change dependency from `_: RequireAdmin` to `caller_info: RequireOperatorOrAdmin`. Add `request: Request` parameter. After resolving the node, call `_check_tag_access(session, caller_info, request, node.id)`. Before creating the tag, call `validate_and_coerce_tag_value(tag.value, tag.value_type)` — if it raises `ValueError`, return `422` with the error detail. Use the returned (possibly coerced) value for the `NodeTag.value`.

#### 1.3 Update `update_node_tag` (L102)

Same auth changes as 1.2. Before applying updates, compute the effective `(value, value_type)` pair:
- `effective_value = tag.value if tag.value is not None else node_tag.value`
- `effective_type = tag.value_type if tag.value_type is not None else node_tag.value_type`
Call `validate_and_coerce_tag_value(effective_value, effective_type)`. If it raises `ValueError`, return `422`. Apply the (possibly coerced) value.

#### 1.4 Update `delete_node_tag` (L264)

Same change — replace `RequireAdmin` with `RequireOperatorOrAdmin`, add ownership check.

#### 1.5 Remove unused endpoints

Remove these endpoint functions entirely:
- `get_node_tag` (L37) — single-tag GET, never used in UI
- `move_node_tag` (L139) — move operation, only used by admin page
- `copy_all_tags` (L199) — bulk copy, only used by admin page
- `delete_all_node_tags` (L292) — bulk delete, only used by admin page

#### 1.6 Update imports

Remove unused imports: `NodeTagMove`, `NodeTagsCopyResult`. Add: `Request`, `UserProfile`, `UserProfileNode`, `status`, `HTTPException` (already imported). The existing `from fastapi import APIRouter, HTTPException` already has `HTTPException` — add `Request` to that line. Add `from sqlalchemy import select` if not already present (it is). Add `from meshcore_hub.common.schemas.nodes import validate_and_coerce_tag_value` (alongside the other schema imports).

### Phase 2: Remove Unused Schemas + Add Validation

**File:** `src/meshcore_hub/common/schemas/nodes.py`

Remove:
- `NodeTagMove` class (L41–49)
- `NodeTagsCopyResult` class (L52–59)

Keep: `NodeTagCreate`, `NodeTagUpdate`, `NodeTagRead`, and all others.

Add `validate_and_coerce_tag_value()` function:

```python
def validate_and_coerce_tag_value(value: str | None, value_type: str) -> str | None:
    """Validate and coerce a tag value based on its declared type.

    Args:
        value: The tag value string (may be None or empty).
        value_type: One of "string", "number", "boolean".

    Returns:
        The coerced value string, or None if input was None.

    Raises:
        ValueError: If the value does not conform to the declared type.
    """
    if value is None or value == "":
        return value

    if value_type == "number":
        try:
            float(value)
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid number value: '{value}'. Must be a valid number."
            )
        return value

    if value_type == "boolean":
        normalized = value.lower().strip()
        if normalized in ("true", "yes", "1"):
            return "true"
        elif normalized in ("false", "no", "0"):
            return "false"
        else:
            raise ValueError(
                f"Invalid boolean value: '{value}'. "
                "Expected: true, false, yes, no, 1, or 0."
            )

    return value  # string type — no validation
```

This function is called by the API route handlers on create and update. It validates non-empty values against their declared type and coerces boolean values to `"true"`/`"false"`.

### Phase 3: Update Web App API Proxy Access

**File:** `src/meshcore_hub/web/app.py`

#### 3.1 Add tag write endpoint to access mapping

In `_build_endpoint_access()` (L51), add entries for tag write paths:

```python
operator_admin = frozenset({role_admin, role_operator})
return {
    # ... existing entries ...
    "v1/nodes/": {
        "GET": _OPEN,
        "POST": admin,          # existing (node creation)
        "PUT": admin,           # existing
        "DELETE": admin,        # existing
    },
    # Add: tag read is open, tag writes require operator/admin
    # These use longer prefixes so they match before the bare "v1/nodes/" prefix
}
```

The proxy's `check_api_access` uses longest-prefix matching. Tag paths like `v1/nodes/{pk}/tags` need entries. Since the tag write endpoints use POST/PUT/DELETE on sub-paths of `v1/nodes/`, add:

```python
"v1/adoptions": {
    "POST": operator_admin,
    "DELETE": operator_admin,
},
# New: tag mutation endpoints
# Tag GET is already covered by "v1/nodes" GET: _OPEN
# Tag writes use these longer-prefix entries:
```

Actually, looking at the proxy structure, the tag API calls from the web frontend go through the API proxy. The proxy maps paths like `/api/v1/nodes/{pk}/tags` → `v1/nodes/{pk}/tags`. We need the proxy to allow POST/PUT/DELETE on tag paths for operator_admin.

The simplest approach: add a specific entry for tag writes:

```python
# Tag write endpoints — operators can edit tags on adopted nodes,
# admins can edit tags on any node. Ownership check happens in the API route.
"v1/nodes/": {  # matches /api/v1/nodes/{pk}/tags, etc. (longer prefix)
    "GET": _OPEN,
    "POST": operator_admin,
    "PUT": operator_admin,
    "DELETE": operator_admin,
},
```

Wait — the current entry for `"v1/nodes/"` already maps POST/PUT/DELETE to `admin`. We need to change it to `operator_admin` so operators can also mutate tags through the proxy. But this also allows operators to create/update/delete nodes themselves, which may not be desired.

The correct approach: split tag endpoints into their own prefix entries. Since `check_api_access` uses longest-prefix matching:

```python
"v1/nodes/": {
    "GET": _OPEN,
    "POST": admin,
    "PUT": admin,
    "DELETE": admin,
},
# Tag endpoints — longer prefix matches first
# /api/v1/nodes/{pk}/tags matches "v1/nodes/" but we need a more specific rule
# We can't easily prefix-match on "v1/nodes/{pk}/tags" since {pk} is dynamic.
```

Looking at `check_api_access` (L108–130), it matches `path.startswith(prefix)`. Since tag paths are always longer than `v1/nodes/`, and the function does longest-prefix matching, we can use a slightly different strategy:

The simplest correct solution: change the existing `"v1/nodes/"` entry's write methods from `admin` to `operator_admin`. The only write operations on `/api/v1/nodes/` paths are tag mutations (the node CRUD itself is only GET in practice). This is safe because:
1. Node creation/updates are not exposed through the web UI
2. Tag mutations already have their own ownership check in the API route
3. The proxy just gates at the role level; fine-grained ownership is checked in the route handler

```python
"v1/nodes/": {
    "GET": _OPEN,
    "POST": operator_admin,
    "PUT": operator_admin,
    "DELETE": operator_admin,
},
```

#### 3.2 Remove admin route protection from SPA catch-all

Remove the admin route protection block (L1041–1057):

```python
# Remove this entire block:
if path.startswith("admin") and (
    path == "admin" or path == "admin/" or path.startswith("admin/")
):
    ...
```

### Phase 4: Add Icon Functions for Tag Editor

**File:** `src/meshcore_hub/web/static/js/spa/icons.js`

Add three new SVG icon functions following the existing Heroicons-style pattern:

#### 4.1 iconPlus

```javascript
export function iconPlus(cls = 'h-5 w-5') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" /></svg>`;
}
```

#### 4.2 iconEdit

```javascript
export function iconEdit(cls = 'h-5 w-5') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>`;
}
```

#### 4.3 iconTrash

```javascript
export function iconTrash(cls = 'h-5 w-5') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>`;
}
```

### Phase 5: Fix API Client Auth Response Handler

**File:** `src/meshcore_hub/web/static/js/spa/api.js`

#### 5.1 Change `checkAuthResponse` to only redirect on 401

Change line 33 from:

```javascript
if (config.oidc_enabled && (response.status === 401 || response.status === 403)) {
```

to:

```javascript
if (config.oidc_enabled && response.status === 401) {
```

This is necessary because 403 from the API means "permission denied" (user is authenticated but lacks permission for that specific resource — e.g., operator editing a non-adopted node). Redirecting to login is wrong in this case. The inline tag editor catches 403 errors and displays them as inline error alerts.

403 responses from the API proxy (role-based access denial) are also caught before reaching `checkApiAccess` — the proxy returns 404/405 for denied endpoints, not 403. So 403s that reach the SPA are always permission-level errors, not auth failures.

Switching tag writes from `RequireAdmin` to `RequireOperatorOrAdmin` introduces the possibility of 403 responses for ownership failures. Without this fix, operators who try to edit tags on non-adopted nodes would be redirected to `/auth/login` instead of seeing a clear inline error message.

### Phase 6: Build Inline Tag Editor in Node Detail Page

**File:** `src/meshcore_hub/web/static/js/spa/pages/node-detail.js`

#### 6.1 Add tag editor imports

Add `apiPost, apiPut, apiDelete` to the import from `../api.js`. Add `iconPlus, iconEdit, iconTrash` from `../icons.js`.

#### 6.2 Replace read-only tags section with inline editor

Replace the current tags card (L207–213) with a tag editor component that:

1. **Renders a tags table** — same as current but with edit/delete action buttons per row (only when user has permission)
2. **Renders an add-tag form** — compact inline form below the table
3. **Renders a delete confirmation modal** — DaisyUI `<dialog>` for delete confirmation
4. **Renders an edit modal** — DaisyUI `<dialog>` for editing tag key/value/type

Permission check: `canEditTags = hasRole('admin') || (hasRole('operator') && node.adopted_by?.user_id === config.user?.sub)`

When `canEditTags` is false, render the current read-only table (no edit/delete buttons, no add form).

#### 6.3 Delete confirmation modal

```javascript
function renderDeleteTagModal() {
    return html`
<dialog id="tagDeleteModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.delete_entity', { entity: t('entities.tag') })}</h3>
        <p class="py-4" id="tag-delete-msg"></p>
        <div class="alert alert-error mb-4">
            <span>${t('common.cannot_be_undone')}</span>
        </div>
        <div class="modal-action">
            <button type="button" class="btn" id="tagDeleteCancel">${t('common.cancel')}</button>
            <button type="button" class="btn btn-error" id="tagDeleteConfirm">${t('common.delete')}</button>
        </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>`;
}
```

#### 6.4 Edit modal

```javascript
function renderEditTagModal() {
    return html`
<dialog id="tagEditModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.edit_entity', { entity: t('entities.tag') })}</h3>
        <form id="tag-edit-form" class="py-4">
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('common.key')}</span></label>
                <input type="text" id="tagEditKey" class="input input-bordered" disabled>
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('common.value')}</span></label>
                <input type="text" id="tagEditValue" class="input input-bordered">
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('common.type')}</span></label>
                <select id="tagEditType" class="select select-bordered w-full">
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                </select>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="tagEditCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-primary">${t('common.save_changes')}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>`;
}
```

#### 6.5 Client-side validation

Add a `validateTagValue(value, type)` helper:

```javascript
function validateTagValue(value, type) {
    if (!value || !type) return null;
    if (type === 'number' && isNaN(Number(value))) {
        return t('common.validation_invalid_number');
    }
    if (type === 'boolean') {
        const normalized = value.toLowerCase().trim();
        if (!['true', 'false', 'yes', 'no', '1', '0'].includes(normalized)) {
            return t('common.validation_invalid_boolean');
        }
    }
    return null;
}
```

Both the add form and edit form call this before submitting. If validation fails, display the error message in an inline `<label>` element below the value input (using DaisyUI's `<label class="label"><span class="label-text-alt text-error">...</span></label>` pattern) and prevent submission.

#### 6.6 Tags card rendering

Replace the current tags card with an editable version. On desktop, the add form is a single row: key input, value input, type select, add button. On mobile it stacks. Each tag row shows inline edit/delete buttons. Value inputs have a `<label>` element below them for validation error display.

```javascript
const canEditTags = config.oidc_enabled && config.user && (
    hasRole('admin') || (hasRole('operator') && node.adopted_by?.user_id === config.user.sub)
);
```

The tags table gets two additional columns when `canEditTags`: an edit button and a delete button per row. The add form appears below the table. The delete modal and edit modal are appended after the card.

#### 6.7 Event handlers

Wire up:
- **Add form submit** — validate with `validateTagValue`, POST to `/api/v1/nodes/{pk}/tags`, refresh node data from API, re-render tags section
- **Edit button click** — populate edit modal with current tag data, show modal
- **Edit form submit** — validate with `validateTagValue`, PUT to `/api/v1/nodes/{pk}/tags/{key}`, refresh, re-render
- **Delete button click** — populate delete confirmation message, show modal
- **Delete confirm click** — DELETE to `/api/v1/nodes/{pk}/tags/{key}`, refresh, re-render
- **Cancel buttons** — close modals

All API calls use `apiPost`, `apiPut`, `apiDelete` from `api.js`. On success, refresh the node data and re-render the tags section. On error, show an inline error alert. Server-side 422 validation errors are displayed in the same validation error label.

#### 6.8 Remove admin tag link

Remove the `adminTagsHtml` block (L129–133) that links to `/admin/node-tags`.

### Phase 7: Remove Admin UI

#### 7.1 Remove admin SPA page modules

Delete:
- `src/meshcore_hub/web/static/js/spa/pages/admin/index.js`
- `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`
- `src/meshcore_hub/web/static/js/spa/pages/admin/` directory

#### 7.2 Remove admin route registrations from app.js

**File:** `src/meshcore_hub/web/static/js/spa/app.js`

Remove:
- `adminIndex` and `adminNodeTags` from `pages` object (L24–25)
- Admin route registration block (L90–95)
- Admin page title entries (L155–157)

#### 7.3 Remove admin nav link from user dropdown

**File:** `src/meshcore_hub/web/static/js/spa/components.js`

Remove the `adminItem` variable and its usage (L623–624, L647).

### Phase 8: Update Tests

#### 8.1 Delete admin web test file

Delete `tests/test_web/test_admin.py` — it tests admin SPA shell serving routes which are removed.

#### 8.2 Create OIDC test fixtures for tag write tests

**File:** `tests/test_api/test_nodes.py` (or `tests/conftest.py`)

The existing `TestNodeTags` class uses `client_no_auth` which relies on `require_admin`'s open-access fallback (no admin key configured → all access allowed). After switching to `RequireOperatorOrAdmin`, tag write endpoints always require `X-User-Id` + `X-User-Roles` headers.

Add new fixtures:
- `oidc_operator_headers` — sets `X-User-Id: operator-123` and `X-User-Roles: operator`
- `oidc_admin_headers` — sets `X-User-Id: admin-456` and `X-User-Roles: admin`
- `oidc_member_headers` — sets `X-User-Id: member-789` and `X-User-Roles: member`
- A fixture that creates a `UserProfile` + `UserProfileNode` adoption record for the operator user on a given node

#### 8.3 Rewrite `test_tag_crud_requires_admin` → `test_tag_crud_requires_operator_or_admin`

Test three auth scenarios:
1. No X-User-Id header → 401
2. X-User-Roles: member → 403
3. X-User-Roles: operator/operator → admin role present → 201 (for admin), 403 (for operator on non-adopted node)

#### 8.4 Update `test_create_node_tag`

Change from `client_no_auth` to using `oidc_admin_headers`. Assert 201 with correct tag data.

#### 8.5 Remove `test_get_node_tag`

This endpoint (`GET /nodes/{pk}/tags/{key}`) is being removed. Delete this test.

#### 8.6 Update `test_update_node_tag`

Change to use `oidc_admin_headers` or `oidc_operator_headers` with adoption. Assert 200.

#### 8.7 Update `test_delete_node_tag`

Change to use `oidc_admin_headers` or `oidc_operator_headers` with adoption. Assert 204. Verify deletion via list endpoint (not single-get, which is removed).

#### 8.8 Add `test_operator_can_edit_adopted_node_tags`

Create adoption record linking operator's profile to the node. Use `oidc_operator_headers`. Verify POST → 201, PUT → 200, DELETE → 204.

#### 8.9 Add `test_operator_cannot_edit_non_adopted_node_tags`

No adoption record for the node. Use `oidc_operator_headers`. Assert POST/PUT/DELETE → 403 with detail "You can only edit tags on nodes you have adopted".

#### 8.10 Add `test_admin_can_edit_any_node_tags`

No adoption record. Use `oidc_admin_headers`. Assert POST → 201 (admin bypasses ownership check).

#### 8.11 Remove `TestMoveNodeTag` class

The move endpoint is removed. Delete all tests in this class (L336–462).

#### 8.12 Remove `test_copy_all_tags` test

If present as a separate test class/method, delete it. The copy-all endpoint is removed.

#### 8.13 Remove `test_delete_all_node_tags` test

If present as a separate test class/method, delete it. The bulk-delete endpoint is removed.

#### 8.14 Add `TestTagValidation` class — unit tests for `validate_and_coerce_tag_value`

Test the validation function directly (no HTTP needed):

- `test_string_passes_through` — any value, type "string" → returned unchanged
- `test_none_returns_none` — value None → returns None
- `test_empty_string_passes` — value "" → returns "" (no validation)
- `test_number_valid_integer` — "42", type "number" → "42"
- `test_number_valid_float` — "3.14", type "number" → "3.14"
- `test_number_valid_negative` — "-7", type "number" → "-7"
- `test_number_invalid` — "abc", type "number" → raises `ValueError`
- `test_boolean_true_variants` — "true", "True", "yes", "1" → all coerce to "true"
- `test_boolean_false_variants` — "false", "False", "no", "0" → all coerce to "false"
- `test_boolean_invalid` — "maybe", type "boolean" → raises `ValueError`
- `test_boolean_whitespace` — " true " → coerces to "true" (stripped)

#### 8.15 Add `TestTagValidationAPI` — integration tests for 422 responses

Using `oidc_admin_headers`:

- `test_create_tag_invalid_number` — POST with value "abc", type "number" → 422
- `test_create_tag_invalid_boolean` — POST with value "maybe", type "boolean" → 422
- `test_create_tag_valid_number` — POST with value "42", type "number" → 201, value stored as "42"
- `test_create_tag_coerces_boolean` — POST with value "yes", type "boolean" → 201, value stored as "true"
- `test_update_tag_validates_new_value_against_existing_type` — Create tag with type "number", then PUT with value "not-a-number" → 422
- `test_update_tag_validates_existing_value_against_new_type` — Create tag with value "hello", then PUT changing type to "number" → 422
- `test_update_tag_validates_new_value_against_new_type` — PUT with value "yes" and type "boolean" → 200, value stored as "true"

### Phase 9: Update i18n

**File:** `src/meshcore_hub/web/static/locales/en.json`

#### 9.1 Remove unused admin i18n keys

Remove the `admin` section (L194–200) — keys `access_denied`, `admin_not_enabled`, `admin_enable_hint`, `welcome`, `tags_description`.

Remove the `admin_node_tags` section (L241–257) — keys `select_node`, `select_node_placeholder`, `load_tags`, `move_warning`, `copy_all`, `copy_all_info`, `delete_all`, `delete_all_warning`, `destination_node`, `tag_key`, `for_this_node`, `empty_state_hint`, `select_a_node`, `select_a_node_description`, `copied_entities`.

Remove `"admin": "Admin"` from the `entities` section (L15) — this key is only used by the admin nav link and admin page titles, both of which are being removed.

#### 9.2 Add validation i18n keys

Add to the `common` section:

```json
"validation_invalid_number": "Value must be a valid number",
"validation_invalid_boolean": "Value must be true, false, yes, no, 1, or 0"
```

These are used by the client-side `validateTagValue` function for inline error display beneath the value input.

#### 9.3 Existing tag editor keys (no changes needed)

The inline editor reuses existing `common.*` and `entities.*` keys for all other UI text:
- Modal titles: `common.edit_entity`, `common.delete_entity` with `entities.tag`
- Form labels: `common.key`, `common.value`, `common.type`
- Buttons: `common.add`, `common.save_changes`, `common.cancel`, `common.delete`
- Alerts: `common.cannot_be_undone`
- Empty state: `common.no_entity_defined` with `entities.tags`
- Success/error: `common.entity_added_success`, `common.entity_updated_success`, `common.entity_deleted_success`

**File:** `docs/i18n.md`

Remove:
- The `admin` section (§16)
- The `admin_members` section (§18, first entry — dead documentation, doesn't exist in en.json)
- The `admin_node_tags` section (§18, second entry)
- The `entities.admin` entry from the entities table (§1)

Update section numbering after removals.

### Phase 10: Update Project Documentation

**File:** `AGENTS.md`

- Remove references to `/admin/` routes in "Project Structure" table
- Remove references to `pages/admin/` directory
- Update "Adding a New SPA Page" section if it references admin pages
- Update testing instructions to remove admin test references

**File:** `docs/upgrading.md`

Add upgrade note:
- `/admin/` routes removed — tag editing is now inline on the node detail page. Navigating to old `/admin/*` URLs will show the SPA 404 page.
- Tag API endpoints changed: `RequireAdmin` → `RequireOperatorOrAdmin` with ownership check. Tag writes now always require OIDC authentication. Deployments without OIDC have read-only tags.
- Removed API endpoints: `GET /nodes/{pk}/tags/{key}`, `PUT .../move`, `POST .../copy-to/...`, `DELETE .../tags` (bulk)
- Operators can now edit tags on their adopted nodes. Previously only admins could write tags.
- Removed schemas: `NodeTagMove`, `NodeTagsCopyResult`
- The admin API key (`API_ADMIN_KEY`) no longer grants tag write access. Tag writes require OIDC authentication with `admin` or `operator` roles.

---

## File Change Summary

| # | File | Action | Phase(s) | Description |
|---|------|--------|----------|-------------|
| 1 | `src/meshcore_hub/api/routes/node_tags.py` | Modify | 1 | Replace `RequireAdmin` with `RequireOperatorOrAdmin` + ownership check; remove move/copy/bulk-delete/single-get endpoints |
| 2 | `src/meshcore_hub/common/schemas/nodes.py` | Modify | 2 | Remove `NodeTagMove` and `NodeTagsCopyResult` schemas |
| 3 | `src/meshcore_hub/web/app.py` | Modify | 3 | Change `v1/nodes/` write methods from `admin` to `operator_admin`; remove admin SPA route protection |
| 4 | `src/meshcore_hub/web/static/js/spa/icons.js` | Modify | 4 | Add `iconPlus`, `iconEdit`, `iconTrash` functions |
| 5 | `src/meshcore_hub/web/static/js/spa/api.js` | Modify | 5 | Change `checkAuthResponse` to redirect only on 401 |
| 6 | `src/meshcore_hub/web/static/js/spa/pages/node-detail.js` | Modify | 6 | Replace read-only tags card with inline editor (add/edit/delete with modals) |
| 7 | `src/meshcore_hub/web/static/js/spa/pages/admin/index.js` | Delete | 7 | Remove admin index page |
| 8 | `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` | Delete | 7 | Remove admin tag editor page |
| 9 | `src/meshcore_hub/web/static/js/spa/app.js` | Modify | 7 | Remove admin route registrations and page imports |
| 10 | `src/meshcore_hub/web/static/js/spa/components.js` | Modify | 7 | Remove admin nav link from user dropdown; clean up unused `iconSettings` import |
| 11 | `tests/test_web/test_admin.py` | Delete | 8 | Remove admin web tests |
| 12 | `tests/test_api/test_nodes.py` | Modify | 8 | Rewrite tag tests for OIDC role-based auth; remove move/copy/bulk-delete tests; add operator ownership tests |
| 13 | `src/meshcore_hub/web/static/locales/en.json` | Modify | 9 | Remove `admin` and `admin_node_tags` sections |
| 14 | `docs/i18n.md` | Modify | 9 | Remove admin/admin_node_tags sections |
| 15 | `AGENTS.md` | Modify | 10 | Remove admin references |
| 16 | `docs/upgrading.md` | Modify | 10 | Add upgrade notes |

---

## Execution Order

1. **Phase 1:** Refactor tag API authorization (`node_tags.py`)
2. **Phase 2:** Remove unused schemas (`nodes.py`)
3. **Phase 3:** Update web app API proxy access and remove admin route protection (`web/app.py`)
4. **Phase 4:** Add icon functions (`icons.js`)
5. **Phase 5:** Fix API client auth response handler (`api.js`)
6. **Phase 6:** Build inline tag editor in node detail page (`node-detail.js`)
7. **Phase 7:** Remove admin UI (delete admin pages, remove routes/nav)
8. **Phase 8:** Update tests (`test_nodes.py`, delete `test_admin.py`)
9. **Phase 9:** Update i18n (`en.json`, `docs/i18n.md`)
10. **Phase 10:** Update project documentation (`AGENTS.md`, `docs/upgrading.md`)

Phases 1–3 are backend changes. Phases 4–5 are frontend infrastructure. Phase 6 is the new frontend feature. Phase 7 is cleanup. Phases 8–10 are tests and docs.

---

## Migration Notes

### API Breaking Changes

**Removed endpoints:**

| Method | Path | Replacement |
|--------|------|-------------|
| `GET` | `/nodes/{pk}/tags/{key}` | Use `GET /nodes/{pk}` and filter tags client-side |
| `PUT` | `/nodes/{pk}/tags/{key}/move` | No replacement (delete + recreate) |
| `POST` | `/nodes/{pk}/tags/copy-to/{dest}` | No replacement (create tags individually) |
| `DELETE` | `/nodes/{pk}/tags` | No replacement (delete tags individually) |

**Authorization change:**

Tag write endpoints (`POST`, `PUT`, `DELETE` on `/nodes/{pk}/tags`) change from `RequireAdmin` to `RequireOperatorOrAdmin` (OIDC role-based, always requires `X-User-Id` header). The API proxy also gates these endpoints at the `operator_admin` level.

**Important:** The previous `RequireAdmin` dependency had a fallback: when no admin key was configured, it allowed open access. The new `RequireOperatorOrAdmin` always requires OIDC authentication — there is no open-access fallback. This means:
- Deployments without OIDC (`OIDC_ENABLED=false`) can no longer write tags via any path (neither web UI nor direct API) — tags are read-only
- Deployments with OIDC enabled must have users with `admin` or `operator` roles to write tags
- The admin API key is used by the web proxy layer for inter-service authentication and does not grant end-user tag write access

Operators are additionally restricted to editing tags on nodes they have adopted. This is enforced in the route handler by checking `user_profile_nodes` for an adoption record.

**Removed schemas:**

- `NodeTagMove` — was used by the move endpoint
- `NodeTagsCopyResult` — was used by the copy-all endpoint

### No Database Changes

No Alembic migration needed. No table schema changes. Only code and route changes.

### OIDC-Disabled Deployments

When `OIDC_ENABLED=false`:
- No users are authenticated → no one has operator/admin role → `canEditTags` is always `false`
- The inline editor is hidden, tags remain read-only in the web UI
- Tag write API endpoints always require OIDC authentication via `X-User-Id` header → 401 on direct API access
- This is a deliberate design: tag management requires OIDC authentication. Deployments that need programmatic tag writes should configure OIDC or use a direct database approach.

---

## Out of Scope (Deferred)

| Item | Reason |
|------|--------|
| Inline tag editing on the nodes list page | Only node detail gets the editor; list page remains read-only |
| Bulk tag operations in inline editor | Admin page had move/copy-all/delete-all; inline editor is per-tag only |
| Tag history/audit log | No audit trail requirement in this change |
