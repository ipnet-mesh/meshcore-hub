import { apiGet, apiPost, apiPut, apiDelete } from '../../api.js';
import {
    html, litRender, nothing,
    getConfig, errorAlert, successAlert, t,
} from '../../components.js';
import { iconLock } from '../../icons.js';

export async function render(container, params, router) {
    try {
        const config = getConfig();

        if (!config.admin_enabled) {
            litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    ${iconLock('h-16 w-16 opacity-30 mb-4')}
    <h1 class="text-3xl font-bold mb-2">${t('admin.access_denied')}</h1>
    <p class="opacity-70">${t('admin.admin_not_enabled')}</p>
    <a href="/" class="btn btn-primary mt-6">${t('common.go_home')}</a>
</div>`, container);
            return;
        }

        if (!config.is_authenticated) {
            litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    ${iconLock('h-16 w-16 opacity-30 mb-4')}
    <h1 class="text-3xl font-bold mb-2">${t('admin.auth_required')}</h1>
    <p class="opacity-70">${t('admin.auth_required_description')}</p>
    <a href="/oauth2/start?rd=${encodeURIComponent(window.location.pathname)}" class="btn btn-primary mt-6">${t('common.sign_in')}</a>
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
                            <th>${t('admin_members.member_id')}</th>
                            <th>${t('common.name')}</th>
                            <th>${t('common.callsign')}</th>
                            <th>${t('common.contact')}</th>
                            <th class="w-32">${t('common.actions')}</th>
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
                                    <button class="btn btn-ghost btn-xs btn-edit">${t('common.edit')}</button>
                                    <button class="btn btn-ghost btn-xs text-error btn-delete">${t('common.delete')}</button>
                                </div>
                            </td>
                        </tr>`)}</tbody>
                </table>
            </div>`
            : html`
            <div class="text-center py-8 text-base-content/60">
                <p>${t('common.no_entity_yet', { entity: t('entities.members').toLowerCase() })}</p>
                <p class="text-sm mt-2">${t('admin_members.empty_state_hint')}</p>
            </div>`;

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <div>
        <h1 class="text-3xl font-bold">${t('entities.members')}</h1>
        <div class="text-sm breadcrumbs">
            <ul>
                <li><a href="/">${t('entities.home')}</a></li>
                <li><a href="/a/">${t('entities.admin')}</a></li>
                <li>${t('entities.members')}</li>
            </ul>
        </div>
    </div>
    <a href="/oauth2/sign_out" target="_blank" class="btn btn-outline btn-sm">${t('common.sign_out')}</a>
</div>

${flashHtml}

<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <div class="flex justify-between items-center">
            <h2 class="card-title">${t('admin_members.network_members', { count: members.length })}</h2>
            <button id="btn-add-member" class="btn btn-primary btn-sm">${t('common.add_entity', { entity: t('entities.member') })}</button>
        </div>
        ${tableHtml}
    </div>
</div>

<dialog id="addModal" class="modal">
    <div class="modal-box w-11/12 max-w-2xl">
        <h3 class="font-bold text-lg">${t('common.add_new_entity', { entity: t('entities.member') })}</h3>
        <form id="add-member-form" class="py-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">${t('admin_members.member_id')} <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="member_id" class="input input-bordered"
                           placeholder="walshie86" required maxlength="50"
                           pattern="[a-zA-Z0-9_]+"
                           title="Letters, numbers, and underscores only">
                    <label class="label">
                        <span class="label-text-alt">${t('admin_members.member_id_hint')}</span>
                    </label>
                </div>
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">${t('common.name')} <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="name" class="input input-bordered"
                           placeholder="John Smith" required maxlength="255">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">${t('common.callsign')}</span></label>
                    <input type="text" name="callsign" class="input input-bordered"
                           placeholder="VK4ABC" maxlength="20">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">${t('common.contact')}</span></label>
                    <input type="text" name="contact" class="input input-bordered"
                           placeholder="john@example.com or phone number" maxlength="255">
                </div>
                <div class="form-control md:col-span-2">
                    <label class="label"><span class="label-text">${t('common.description')}</span></label>
                    <textarea name="description" rows="3" class="textarea textarea-bordered"
                              placeholder="Brief description of member's role and responsibilities..."></textarea>
                </div>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="addCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-primary">${t('common.add_entity', { entity: t('entities.member') })}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>

<dialog id="editModal" class="modal">
    <div class="modal-box w-11/12 max-w-2xl">
        <h3 class="font-bold text-lg">${t('common.edit_entity', { entity: t('entities.member') })}</h3>
        <form id="edit-member-form" class="py-4">
            <input type="hidden" name="id" id="edit_id">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">${t('admin_members.member_id')} <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="member_id" id="edit_member_id" class="input input-bordered"
                           required maxlength="50" pattern="[a-zA-Z0-9_]+"
                           title="Letters, numbers, and underscores only">
                </div>
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">${t('common.name')} <span class="text-error">*</span></span>
                    </label>
                    <input type="text" name="name" id="edit_name" class="input input-bordered"
                           required maxlength="255">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">${t('common.callsign')}</span></label>
                    <input type="text" name="callsign" id="edit_callsign" class="input input-bordered"
                           maxlength="20">
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">${t('common.contact')}</span></label>
                    <input type="text" name="contact" id="edit_contact" class="input input-bordered"
                           maxlength="255">
                </div>
                <div class="form-control md:col-span-2">
                    <label class="label"><span class="label-text">${t('common.description')}</span></label>
                    <textarea name="description" id="edit_description" rows="3"
                              class="textarea textarea-bordered"></textarea>
                </div>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="editCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-primary">${t('common.save_changes')}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>

<dialog id="deleteModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.delete_entity', { entity: t('entities.member') })}</h3>
        <div class="py-4">
            <p class="py-4" id="delete_confirm_message"></p>
            <div class="alert alert-error mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>${t('common.cannot_be_undone')}</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="deleteCancel">${t('common.cancel')}</button>
                <button type="button" class="btn btn-error" id="deleteConfirm">${t('common.delete')}</button>
            </div>
        </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
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
                router.navigate('/a/members?message=' + encodeURIComponent(t('common.entity_added_success', { entity: t('entities.member') })));
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
                router.navigate('/a/members?message=' + encodeURIComponent(t('common.entity_updated_success', { entity: t('entities.member') })));
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
                const memberName = row.dataset.memberName;
                const confirmMsg = t('common.delete_entity_confirm', {
                    entity: t('entities.member').toLowerCase(),
                    name: memberName
                });
                container.querySelector('#delete_confirm_message').innerHTML = confirmMsg;
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
                router.navigate('/a/members?message=' + encodeURIComponent(t('common.entity_deleted_success', { entity: t('entities.member') })));
            } catch (err) {
                container.querySelector('#deleteModal').close();
                router.navigate('/a/members?error=' + encodeURIComponent(err.message));
            }
        });

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
