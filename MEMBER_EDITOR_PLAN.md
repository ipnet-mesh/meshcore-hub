# Member Editor Implementation Plan

## Overview

Create a Member Editor admin interface at `/a/members` following the proven pattern established by the Tag Editor. All backend API infrastructure already exists; this is purely a web UI implementation.

## Current State

### ✅ Already Implemented

| Component | Status | Location |
|-----------|--------|----------|
| Member Model | ✅ Complete | `common/models/member.py` |
| API Schemas | ✅ Complete | `common/schemas/members.py` |
| API CRUD Endpoints | ✅ Complete | `api/routes/members.py` |
| YAML Import | ✅ Complete | `collector/member_import.py` |
| Public Members Page | ✅ Complete | `web/routes/members.py` |
| Admin Foundation | ✅ Complete | `web/routes/admin.py` |

### ❌ Missing - To Be Implemented

1. Admin web routes for Member CRUD at `/a/members`
2. Admin template `admin/members.html`
3. Navigation card in admin index

## Architecture Reference

The Member Editor will follow the **exact same pattern** as the Tag Editor:

```
User visits /a/members
    ↓
Displays members table with actions
    ↓
User clicks: Create | Edit | Delete
    ↓
Modal opens with form
    ↓
Form submits via POST to /a/members/{action}
    ↓
Backend calls API endpoint
    ↓
Redirects back to /a/members with flash message
```

## Implementation Tasks

### Task 1: Add Admin Web Routes

**File:** `src/meshcore_hub/web/routes/admin.py`

Add the following routes following the Tag Editor pattern:

#### 1.1 Main Members Page (GET)
```python
@router.get("/members", response_class=HTMLResponse)
async def admin_members(
    request: Request,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
) -> HTMLResponse
```

**Responsibilities:**
- Check admin enabled via `_check_admin_enabled(request)`
- Get auth context via `_get_auth_context(request)`
- Fetch all members from `/api/v1/members?limit=1000`
- Sort members by name
- Render `admin/members.html` template

#### 1.2 Create Member (POST)
```python
@router.post("/members", response_class=RedirectResponse)
async def admin_create_member(
    request: Request,
    name: str = Form(...),
    member_id: str = Form(...),
    callsign: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    contact: Optional[str] = Form(None)
) -> RedirectResponse
```

**Responsibilities:**
- Check admin enabled and require auth
- POST to `/api/v1/members` with form data
- Handle success (201) → redirect with success message
- Handle errors (409 duplicate, 400 validation) → redirect with error
- Use `_build_redirect_url()` helper

#### 1.3 Update Member (POST)
```python
@router.post("/members/update", response_class=RedirectResponse)
async def admin_update_member(
    request: Request,
    id: str = Form(...),
    name: Optional[str] = Form(None),
    member_id: Optional[str] = Form(None),
    callsign: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    contact: Optional[str] = Form(None)
) -> RedirectResponse
```

**Responsibilities:**
- Check admin enabled and require auth
- Build update payload (only non-None fields)
- PUT to `/api/v1/members/{id}` with update data
- Handle success (200) → redirect with success message
- Handle errors (404, 409, 400) → redirect with error

#### 1.4 Delete Member (POST)
```python
@router.post("/members/delete", response_class=RedirectResponse)
async def admin_delete_member(
    request: Request,
    id: str = Form(...)
) -> RedirectResponse
```

**Responsibilities:**
- Check admin enabled and require auth
- DELETE to `/api/v1/members/{id}`
- Handle success (204) → redirect with success message
- Handle errors (404) → redirect with error

### Task 2: Create Admin Template

**File:** `src/meshcore_hub/web/templates/admin/members.html`

Structure based on `admin/node_tags.html`:

#### 2.1 Page Layout
```html
{% extends "base.html" %}

{% block title %}Members - Admin{% endblock %}

{% block breadcrumb %}
<div class="text-sm breadcrumbs">
    <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/a/">Admin</a></li>
        <li>Members</li>
    </ul>
</div>
{% endblock %}

{% block content %}
<!-- Flash messages -->
<!-- Members table -->
<!-- Add member form -->
<!-- Modals (Edit, Delete) -->
{% endblock %}
```

#### 2.2 Flash Messages Section
```html
{% if message %}
<div class="alert alert-success">{{ message }}</div>
{% endif %}

{% if error %}
<div class="alert alert-error">{{ error }}</div>
{% endif %}
```

#### 2.3 Members Table Card
```html
<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title">Network Members</h2>

        <table class="table table-zebra">
            <thead>
                <tr>
                    <th>Member ID</th>
                    <th>Name</th>
                    <th>Callsign</th>
                    <th>Role</th>
                    <th>Contact</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
            {% for member in members %}
                <tr data-member-id="{{ member.id }}"
                    data-member-name="{{ member.name }}"
                    data-member-member-id="{{ member.member_id }}"
                    data-member-callsign="{{ member.callsign or '' }}"
                    data-member-role="{{ member.role or '' }}"
                    data-member-description="{{ member.description or '' }}"
                    data-member-contact="{{ member.contact or '' }}">
                    <td><code>{{ member.member_id }}</code></td>
                    <td>{{ member.name }}</td>
                    <td>
                        {% if member.callsign %}
                        <span class="badge badge-primary">{{ member.callsign }}</span>
                        {% endif %}
                    </td>
                    <td>{{ member.role or '-' }}</td>
                    <td>{{ member.contact or '-' }}</td>
                    <td>
                        <button class="btn btn-sm btn-ghost btn-edit">Edit</button>
                        <button class="btn btn-sm btn-error btn-delete">Delete</button>
                    </td>
                </tr>
            {% else %}
                <tr>
                    <td colspan="6" class="text-center text-gray-500">
                        No members configured yet
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
```

#### 2.4 Add Member Form Card
```html
<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title">Add New Member</h2>

        <form method="post" action="/a/members">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Member ID *</span>
                    </label>
                    <input type="text" name="member_id" required
                           placeholder="walshie86" class="input input-bordered">
                    <label class="label">
                        <span class="label-text-alt">Unique identifier (letters, numbers, underscore)</span>
                    </label>
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Name *</span>
                    </label>
                    <input type="text" name="name" required
                           placeholder="John Smith" class="input input-bordered">
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Callsign</span>
                    </label>
                    <input type="text" name="callsign"
                           placeholder="VK4ABC" class="input input-bordered">
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Role</span>
                    </label>
                    <input type="text" name="role"
                           placeholder="Network Coordinator" class="input input-bordered">
                </div>

                <div class="form-control md:col-span-2">
                    <label class="label">
                        <span class="label-text">Contact</span>
                    </label>
                    <input type="text" name="contact"
                           placeholder="john@example.com" class="input input-bordered">
                </div>

                <div class="form-control md:col-span-2">
                    <label class="label">
                        <span class="label-text">Description</span>
                    </label>
                    <textarea name="description" rows="3"
                              placeholder="Brief description..."
                              class="textarea textarea-bordered"></textarea>
                </div>
            </div>

            <div class="form-control mt-4">
                <button type="submit" class="btn btn-primary">Add Member</button>
            </div>
        </form>
    </div>
</div>
```

#### 2.5 Edit Modal
```html
<dialog id="editModal" class="modal">
    <div class="modal-box w-11/12 max-w-2xl">
        <h3 class="font-bold text-lg">Edit Member</h3>

        <form method="post" action="/a/members/update">
            <input type="hidden" name="id" id="edit_id">

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Member ID *</span>
                    </label>
                    <input type="text" name="member_id" id="edit_member_id"
                           required class="input input-bordered">
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Name *</span>
                    </label>
                    <input type="text" name="name" id="edit_name"
                           required class="input input-bordered">
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Callsign</span>
                    </label>
                    <input type="text" name="callsign" id="edit_callsign"
                           class="input input-bordered">
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Role</span>
                    </label>
                    <input type="text" name="role" id="edit_role"
                           class="input input-bordered">
                </div>

                <div class="form-control md:col-span-2">
                    <label class="label">
                        <span class="label-text">Contact</span>
                    </label>
                    <input type="text" name="contact" id="edit_contact"
                           class="input input-bordered">
                </div>

                <div class="form-control md:col-span-2">
                    <label class="label">
                        <span class="label-text">Description</span>
                    </label>
                    <textarea name="description" id="edit_description"
                              rows="3" class="textarea textarea-bordered"></textarea>
                </div>
            </div>

            <div class="modal-action">
                <button type="button" class="btn" onclick="editModal.close()">Cancel</button>
                <button type="submit" class="btn btn-primary">Save Changes</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop">
        <button>close</button>
    </form>
</dialog>
```

#### 2.6 Delete Modal
```html
<dialog id="deleteModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Delete Member</h3>
        <p class="py-4">
            Are you sure you want to delete member <strong id="delete_member_name"></strong>?
            This action cannot be undone.
        </p>

        <form method="post" action="/a/members/delete">
            <input type="hidden" name="id" id="delete_id">

            <div class="modal-action">
                <button type="button" class="btn" onclick="deleteModal.close()">Cancel</button>
                <button type="submit" class="btn btn-error">Delete</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop">
        <button>close</button>
    </form>
</dialog>
```

#### 2.7 JavaScript Event Handlers
```html
<script>
// Edit button handler
document.querySelectorAll('.btn-edit').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var row = this.closest('tr');
        document.getElementById('edit_id').value = row.dataset.memberId;
        document.getElementById('edit_member_id').value = row.dataset.memberMemberId;
        document.getElementById('edit_name').value = row.dataset.memberName;
        document.getElementById('edit_callsign').value = row.dataset.memberCallsign;
        document.getElementById('edit_role').value = row.dataset.memberRole;
        document.getElementById('edit_description').value = row.dataset.memberDescription;
        document.getElementById('edit_contact').value = row.dataset.memberContact;
        editModal.showModal();
    });
});

// Delete button handler
document.querySelectorAll('.btn-delete').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var row = this.closest('tr');
        document.getElementById('delete_id').value = row.dataset.memberId;
        document.getElementById('delete_member_name').textContent = row.dataset.memberName;
        deleteModal.showModal();
    });
});
</script>
```

### Task 3: Update Admin Index

**File:** `src/meshcore_hub/web/templates/admin/index.html`

Add a new navigation card for the Member Editor after the existing Node Tags card:

```html
<a href="/a/members" class="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
    <div class="card-body">
        <h2 class="card-title">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
            Members
        </h2>
        <p>Manage network members and operators</p>
        <div class="card-actions justify-end">
            <button class="btn btn-primary btn-sm">Manage</button>
        </div>
    </div>
</a>
```

## Field Descriptions

### Member Model Fields

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `member_id` | string | Yes | Unique identifier for member | `walshie86` |
| `name` | string | Yes | Full display name | `John Smith` |
| `callsign` | string | No | Amateur radio callsign | `VK4ABC` |
| `role` | string | No | Member's role in network | `Network Coordinator` |
| `description` | text | No | Longer description of member | `Manages Brisbane nodes` |
| `contact` | string | No | Contact information | `john@example.com` |

### Validation Rules

- `member_id`: 1-50 chars, alphanumeric + underscore only
- `name`: 1-255 chars
- `callsign`: Max 20 chars
- `role`: Max 100 chars
- `contact`: Max 255 chars
- `description`: No limit (TEXT field)

## Testing Checklist

### Manual Testing

- [ ] Access `/a/members` - displays empty state
- [ ] Create new member with all fields
- [ ] Create new member with only required fields
- [ ] Edit member - update single field
- [ ] Edit member - update all fields
- [ ] Delete member - confirm deletion
- [ ] Delete member - cancel deletion
- [ ] Try duplicate member_id - shows error
- [ ] Try empty required fields - shows validation error
- [ ] Verify flash messages appear on success/error
- [ ] Check mobile responsive layout
- [ ] Verify authentication required for POST actions
- [ ] Verify admin disabled shows 404

### API Integration Testing

- [ ] Create via web → verify in API GET
- [ ] Update via web → verify in API GET
- [ ] Delete via web → verify 404 in API GET
- [ ] Check timestamps update correctly

### UI/UX Testing

- [ ] Table sorts properly
- [ ] Modals open/close correctly
- [ ] Form validation works
- [ ] Error messages are clear
- [ ] Success messages are clear
- [ ] Layout works on mobile
- [ ] Layout works on tablet
- [ ] Layout works on desktop

## Acceptance Criteria

✅ The Member Editor is complete when:

1. **Create**: Admin can create new members via form
2. **Read**: Admin can view all members in a table
3. **Update**: Admin can edit member fields via modal
4. **Delete**: Admin can delete members with confirmation
5. **Navigation**: Admin index has working Members card
6. **Authentication**: All state-changing operations require auth
7. **Validation**: Form validation matches API schemas
8. **Error Handling**: Clear error messages for failures
9. **Success Feedback**: Flash messages confirm successful actions
10. **Mobile Responsive**: Works on all screen sizes

## Future Enhancements (Out of Scope)

- Bulk import members from web UI
- Export members to YAML
- Link member to multiple nodes
- Member activity history
- Search/filter members
- Pagination for large member lists

## Implementation Order

1. ✅ Review existing code (Tag Editor + Member API)
2. ⬜ Add admin web routes to `admin.py`
3. ⬜ Create `admin/members.html` template
4. ⬜ Update admin index navigation
5. ⬜ Test CRUD operations
6. ⬜ Test error cases
7. ⬜ Test responsive layout
8. ⬜ Commit and push changes

## Estimated Complexity

- **Routes**: Simple (follow existing pattern)
- **Template**: Medium (adapt from node_tags.html)
- **Testing**: Medium (comprehensive testing required)

**Total Effort**: ~2-3 hours of focused development

## Related Documentation

- Tag Editor Reference: `src/meshcore_hub/web/routes/admin.py` (lines for node_tags routes)
- Tag Editor Template: `src/meshcore_hub/web/templates/admin/node_tags.html`
- Member API: `src/meshcore_hub/api/routes/members.py`
- Member Schemas: `src/meshcore_hub/common/schemas/members.py`
- Member Model: `src/meshcore_hub/common/models/member.py`
