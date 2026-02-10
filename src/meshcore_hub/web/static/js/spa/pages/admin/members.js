import { apiGet, apiPost, apiPut, apiDelete } from '../../api.js';
import {
    html, litRender, nothing,
    getConfig, errorAlert, successAlert,
} from '../../components.js';
import { iconLock } from '../../icons.js';

export async function render(container, params, router) {
    try {
        const config = getConfig();

        if (!config.admin_enabled) {
            litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    ${iconLock('h-16 w-16 opacity-30 mb-4')}
    <h1 class="text-3xl font-bold mb-2">Access Denied</h1>
    <p class="opacity-70">The admin interface is not enabled.</p>
    <a href="/" class="btn btn-primary mt-6">Go Home</a>
</div>`, container);
            return;
        }

        const flashMessage = (params.query && params.query.message) || '';
        const flashError = (params.query && params.query.error) || '';

        const data = await apiGet('/api/v1/members', { limit: 100 });
        const members = data.items || [];

        const flashHtml = html`${flashMessage ? successAlert(flashMessage) : nothing}${flashError ? errorAlert(flashError) : nothing}`;

        const tableHtml = members.length > 0
            ? html`
            <div class="overflow-x-auto">
                <table class="table table-zebra">
                    <thead>
                        <tr>
                            <th>Member ID</th>
                            <th>Name</th>
                            <th>Callsign</th>
                            <th>Contact</th>
                            <th class="w-32">Actions</th>
                        </tr>
                    </thead>
                    <tbody>${members.map(m => html`
                        <tr data-member-id=${m.id}
                            data-member-name=${m.name}
                            data-member-member-id=${m.member_id}
                            data-member-callsign=${m.callsign || ''}
                            data-member-description=${m.description || ''}
                            data-member-contact=${m.contact || ''}>
                            <td class="font-mono font-semibold">${m.member_id}</td>
                            <td>${m.name}</td>
                            <td>
                                ${m.callsign
                                    ? html`<span class="badge badge-primary">${m.callsign}</span>`
                                    : html`<span class="text-base-content/40">-</span>`}
                            </td>
                            <td class="max-w-xs truncate" title=${m.contact || ''}>${m.contact || '-'}</td>
                            <td>
                                <div class="flex gap-1">
                                    <button class="btn btn-ghost btn-xs btn-edit">Edit</button>
                                    <button class="btn btn-ghost btn-xs text-error btn-delete">Delete</button>
                                </div>
                            </td>
                        </tr>`)}</tbody>
                </table>
            </div>`
            : html`
            <div class="text-center py-8 text-base-content/60">
                <p>No members configured yet.</p>
                <p class="text-sm mt-2">Click "Add Member" to create the first member.</p>
            </div>`;

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <div>
        <h1 class="text-3xl font-bold">Members</h1>
        <div class="text-sm breadcrumbs">
            <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/a/">Admin</a></li>
                <li>Members</li>
            </ul>
        </div>
    </div>
    <a href="/oauth2/sign_out" target="_blank" class="btn btn-outline btn-sm">Sign Out</a>
</div>

${flashHtml}

<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <div class="flex justify-between items-center">
            <h2 class="card-title">Network Members (${members.length})</h2>
            <button id="btn-add-member" class="btn btn-primary btn-sm">Add Member</button>
        </div>
        ${tableHtml}
    </div>
</div>

<dialog id="addModal" class="modal">
    <div class="modal-box w-11/12 max-w-2xl">
        <h3 class="font-bold text-lg">Add New Member</h3>
        <form id="add-member-form" class="py-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Member ID <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="member_id" class="input input-bordered"
                           placeholder="walshie86" required maxlength="50"
                           pattern="[a-zA-Z0-9_]+"
                           title="Letters, numbers, and underscores only">
                    <label class="label">
                        <span class="label-text-alt">Unique identifier (letters, numbers, underscore)</span>
                    </label>
                </div>
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Name <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="name" class="input input-bordered"
                           placeholder="John Smith" required maxlength="255">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">Callsign</span></label>
                    <input type="text" name="callsign" class="input input-bordered"
                           placeholder="VK4ABC" maxlength="20">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">Contact</span></label>
                    <input type="text" name="contact" class="input input-bordered"
                           placeholder="john@example.com or phone number" maxlength="255">
                </div>
                <div class="form-control md:col-span-2">
                    <label class="label"><span class="label-text">Description</span></label>
                    <textarea name="description" rows="3" class="textarea textarea-bordered"
                              placeholder="Brief description of member's role and responsibilities..."></textarea>
                </div>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="addCancel">Cancel</button>
                <button type="submit" class="btn btn-primary">Add Member</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>

<dialog id="editModal" class="modal">
    <div class="modal-box w-11/12 max-w-2xl">
        <h3 class="font-bold text-lg">Edit Member</h3>
        <form id="edit-member-form" class="py-4">
            <input type="hidden" name="id" id="edit_id">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Member ID <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="member_id" id="edit_member_id" class="input input-bordered"
                           required maxlength="50" pattern="[a-zA-Z0-9_]+"
                           title="Letters, numbers, and underscores only">
                </div>
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Name <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="name" id="edit_name" class="input input-bordered"
                           required maxlength="255">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">Callsign</span></label>
                    <input type="text" name="callsign" id="edit_callsign" class="input input-bordered"
                           maxlength="20">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">Contact</span></label>
                    <input type="text" name="contact" id="edit_contact" class="input input-bordered"
                           maxlength="255">
                </div>
                <div class="form-control md:col-span-2">
                    <label class="label"><span class="label-text">Description</span></label>
                    <textarea name="description" id="edit_description" rows="3"
                              class="textarea textarea-bordered"></textarea>
                </div>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="editCancel">Cancel</button>
                <button type="submit" class="btn btn-primary">Save Changes</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>

<dialog id="deleteModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Delete Member</h3>
        <div class="py-4">
            <p class="py-4">Are you sure you want to delete member <strong id="delete_member_name"></strong>?</p>
            <div class="alert alert-error mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>This action cannot be undone.</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="deleteCancel">Cancel</button>
                <button type="button" class="btn btn-error" id="deleteConfirm">Delete</button>
            </div>
        </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>`, container);

        let activeDeleteId = '';

        // Add Member
        container.querySelector('#btn-add-member').addEventListener('click', () => {
            const form = container.querySelector('#add-member-form');
            form.reset();
            container.querySelector('#addModal').showModal();
        });

        container.querySelector('#addCancel').addEventListener('click', () => {
            container.querySelector('#addModal').close();
        });

        container.querySelector('#add-member-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const body = {
                member_id: form.member_id.value.trim(),
                name: form.name.value.trim(),
                callsign: form.callsign.value.trim() || null,
                description: form.description.value.trim() || null,
                contact: form.contact.value.trim() || null,
            };

            try {
                await apiPost('/api/v1/members', body);
                container.querySelector('#addModal').close();
                router.navigate('/a/members?message=' + encodeURIComponent('Member added successfully'));
            } catch (err) {
                container.querySelector('#addModal').close();
                router.navigate('/a/members?error=' + encodeURIComponent(err.message));
            }
        });

        // Edit Member
        container.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const row = btn.closest('tr');
                container.querySelector('#edit_id').value = row.dataset.memberId;
                container.querySelector('#edit_member_id').value = row.dataset.memberMemberId;
                container.querySelector('#edit_name').value = row.dataset.memberName;
                container.querySelector('#edit_callsign').value = row.dataset.memberCallsign;
                container.querySelector('#edit_description').value = row.dataset.memberDescription;
                container.querySelector('#edit_contact').value = row.dataset.memberContact;
                container.querySelector('#editModal').showModal();
            });
        });

        container.querySelector('#editCancel').addEventListener('click', () => {
            container.querySelector('#editModal').close();
        });

        container.querySelector('#edit-member-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const id = form.id.value;
            const body = {
                member_id: form.member_id.value.trim(),
                name: form.name.value.trim(),
                callsign: form.callsign.value.trim() || null,
                description: form.description.value.trim() || null,
                contact: form.contact.value.trim() || null,
            };

            try {
                await apiPut('/api/v1/members/' + encodeURIComponent(id), body);
                container.querySelector('#editModal').close();
                router.navigate('/a/members?message=' + encodeURIComponent('Member updated successfully'));
            } catch (err) {
                container.querySelector('#editModal').close();
                router.navigate('/a/members?error=' + encodeURIComponent(err.message));
            }
        });

        // Delete Member
        container.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', () => {
                const row = btn.closest('tr');
                activeDeleteId = row.dataset.memberId;
                container.querySelector('#delete_member_name').textContent = row.dataset.memberName;
                container.querySelector('#deleteModal').showModal();
            });
        });

        container.querySelector('#deleteCancel').addEventListener('click', () => {
            container.querySelector('#deleteModal').close();
        });

        container.querySelector('#deleteConfirm').addEventListener('click', async () => {
            try {
                await apiDelete('/api/v1/members/' + encodeURIComponent(activeDeleteId));
                container.querySelector('#deleteModal').close();
                router.navigate('/a/members?message=' + encodeURIComponent('Member deleted successfully'));
            } catch (err) {
                container.querySelector('#deleteModal').close();
                router.navigate('/a/members?error=' + encodeURIComponent(err.message));
            }
        });

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load members'), container);
    }
}
