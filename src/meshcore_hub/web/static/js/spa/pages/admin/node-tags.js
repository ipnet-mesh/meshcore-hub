import { apiGet, apiPost, apiPut, apiDelete } from '../../api.js';
import {
    html, litRender, nothing, unsafeHTML,
    getConfig, typeEmoji, formatDateTimeShort, errorAlert,
    successAlert, truncateKey, t,
} from '../../components.js';
import { iconTag, iconLock } from '../../icons.js';

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

        const selectedPublicKey = (params.query && params.query.public_key) || '';
        const flashMessage = (params.query && params.query.message) || '';
        const flashError = (params.query && params.query.error) || '';

        const nodesData = await apiGet('/api/v1/nodes', { limit: 500 });
        const allNodes = nodesData.items || [];

        let selectedNode = null;
        let tags = [];

        if (selectedPublicKey) {
            try {
                selectedNode = await apiGet('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey));
                tags = selectedNode.tags || [];
            } catch {
                selectedNode = null;
            }
        }

        const flashHtml = html`${flashMessage ? successAlert(flashMessage) : nothing}${flashError ? errorAlert(flashError) : nothing}`;

        let contentHtml = nothing;

        if (selectedPublicKey && selectedNode) {
            const nodeEmoji = typeEmoji(selectedNode.adv_type);
            const nodeName = selectedNode.name || t('common.unnamed_node');
            const otherNodes = allNodes.filter(n => n.public_key !== selectedPublicKey);

            const tagsTableHtml = tags.length > 0
                ? html`
                <div class="overflow-x-auto">
                    <table class="table table-zebra">
                        <thead>
                            <tr>
                                <th>${t('common.key')}</th>
                                <th>${t('common.value')}</th>
                                <th>${t('common.type')}</th>
                                <th>${t('common.updated')}</th>
                                <th class="w-48">${t('common.actions')}</th>
                            </tr>
                        </thead>
                        <tbody>${tags.map(tag => html`
                            <tr data-tag-key=${tag.key} data-tag-value=${tag.value || ''} data-tag-type=${tag.value_type}>
                                <td class="font-mono font-semibold">${tag.key}</td>
                                <td class="max-w-xs truncate" title=${tag.value || ''}>${tag.value || '-'}</td>
                                <td>
                                    <span class="badge badge-ghost badge-sm">${tag.value_type}</span>
                                </td>
                                <td class="text-sm opacity-70">${formatDateTimeShort(tag.updated_at)}</td>
                                <td>
                                    <div class="flex gap-1">
                                        <button class="btn btn-ghost btn-xs btn-edit">${t('common.edit')}</button>
                                        <button class="btn btn-ghost btn-xs btn-move">${t('common.move')}</button>
                                        <button class="btn btn-ghost btn-xs text-error btn-delete">${t('common.delete')}</button>
                                    </div>
                                </td>
                            </tr>`)}</tbody>
                    </table>
                </div>`
                : html`
                <div class="text-center py-8 text-base-content/60">
                    <p>${t('admin_node_tags.no_tags_found')}</p>
                    <p class="text-sm mt-2">${t('admin_node_tags.no_tags_hint')}</p>
                </div>`;

            const bulkButtons = tags.length > 0
                ? html`
                <button id="btn-copy-all" class="btn btn-outline btn-sm">${t('admin_node_tags.copy_all')}</button>
                <button id="btn-delete-all" class="btn btn-outline btn-error btn-sm">${t('admin_node_tags.delete_all')}</button>`
                : nothing;

            contentHtml = html`
<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <div class="flex justify-between items-start">
            <div class="flex items-start gap-3">
                <span class="text-2xl" title=${selectedNode.adv_type || 'Unknown'}>${nodeEmoji}</span>
                <div>
                    <h2 class="card-title">${nodeName}</h2>
                    <p class="text-sm opacity-70 font-mono">${selectedPublicKey}</p>
                </div>
            </div>
            <div class="flex gap-2">
                ${bulkButtons}
                <a href="/nodes/${encodeURIComponent(selectedPublicKey)}" class="btn btn-ghost btn-sm">${t('admin_node_tags.view_node')}</a>
            </div>
        </div>
    </div>
</div>

<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <h2 class="card-title">${t('admin_node_tags.tags_count', { count: tags.length })}</h2>
        ${tagsTableHtml}
    </div>
</div>

<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title">${t('common.add_new_entity', { entity: t('entities.tag') })}</h2>
        <form id="add-tag-form" class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="form-control">
                <label class="label"><span class="label-text">${t('common.key')}</span></label>
                <input type="text" name="key" class="input input-bordered" placeholder="tag_name" required maxlength="100">
            </div>
            <div class="form-control">
                <label class="label"><span class="label-text">${t('common.value')}</span></label>
                <input type="text" name="value" class="input input-bordered" placeholder="tag value">
            </div>
            <div class="form-control">
                <label class="label"><span class="label-text">${t('common.type')}</span></label>
                <select name="value_type" class="select select-bordered">
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                </select>
            </div>
            <div class="form-control">
                <label class="label"><span class="label-text">&nbsp;</span></label>
                <button type="submit" class="btn btn-primary">${t('common.add_entity', { entity: t('entities.tag') })}</button>
            </div>
        </form>
    </div>
</div>

<dialog id="editModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.edit_entity', { entity: t('entities.tag') })}</h3>
        <form id="edit-tag-form" class="py-4">
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('common.key')}</span></label>
                <input type="text" id="editKeyDisplay" class="input input-bordered" disabled>
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('common.value')}</span></label>
                <input type="text" id="editValue" class="input input-bordered">
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('common.type')}</span></label>
                <select id="editValueType" class="select select-bordered w-full">
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                </select>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="editCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-primary">${t('common.save_changes')}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>

<dialog id="moveModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('admin_node_tags.move_to_another_node')}</h3>
        <form id="move-tag-form" class="py-4">
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('admin_node_tags.tag_key')}</span></label>
                <input type="text" id="moveKeyDisplay" class="input input-bordered" disabled>
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('admin_node_tags.destination_node')}</span></label>
                <select id="moveDestination" class="select select-bordered w-full" required>
                    <option value="">${t('map.select_destination_node')}</option>
                    ${otherNodes.map(n => {
                        const name = n.name || t('common.unnamed');
                        const keyPreview = n.public_key.slice(0, 8) + '...' + n.public_key.slice(-4);
                        return html`<option value=${n.public_key}>${name} (${keyPreview})</option>`;
                    })}
                </select>
            </div>
            <div class="alert alert-warning mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>${t('admin_node_tags.move_warning')}</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="moveCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-warning">${t('common.move_entity', { entity: t('entities.tag') })}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>

<dialog id="deleteModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.delete_entity', { entity: t('entities.tag') })}</h3>
        <div class="py-4">
            <p class="py-4">Are you sure you want to delete the tag "<span id="deleteKeyDisplay" class="font-mono font-semibold"></span>"?</p>
            <div class="alert alert-error mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>${t('admin_node_tags.cannot_be_undone')}</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="deleteCancel">${t('common.cancel')}</button>
                <button type="button" class="btn btn-error" id="deleteConfirm">${t('common.delete')}</button>
            </div>
        </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>

<dialog id="copyAllModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('admin_node_tags.copy_all_title')}</h3>
        <form id="copy-all-form" class="py-4">
            <p class="mb-4">${unsafeHTML(t('admin_node_tags.copy_all_description', { count: tags.length, name: nodeName }))}</p>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">${t('admin_node_tags.destination_node')}</span></label>
                <select id="copyAllDestination" class="select select-bordered w-full" required>
                    <option value="">${t('map.select_destination_node')}</option>
                    ${otherNodes.map(n => {
                        const name = n.name || t('common.unnamed');
                        const keyPreview = n.public_key.slice(0, 8) + '...' + n.public_key.slice(-4);
                        return html`<option value=${n.public_key}>${name} (${keyPreview})</option>`;
                    })}
                </select>
            </div>
            <div class="alert alert-info mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <span>${t('admin_node_tags.copy_all_info')}</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="copyAllCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-primary">${t('admin_node_tags.copy_tags')}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>

<dialog id="deleteAllModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.delete_all_entity', { entity: t('entities.tags') })}</h3>
        <div class="py-4">
            <p class="mb-4">${unsafeHTML(t('admin_node_tags.delete_all_confirm', { count: tags.length, name: nodeName }))}</p>
            <div class="alert alert-error mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>${t('admin_node_tags.delete_all_warning')}</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="deleteAllCancel">${t('common.cancel')}</button>
                <button type="button" class="btn btn-error" id="deleteAllConfirm">${t('common.delete_all_entity', { entity: t('entities.tags') })}</button>
            </div>
        </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>`;
        } else if (selectedPublicKey && !selectedNode) {
            contentHtml = html`
<div class="alert alert-warning">
    <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
    <span>Node not found: ${selectedPublicKey}</span>
</div>`;
        } else {
            contentHtml = html`
<div class="card bg-base-100 shadow-xl">
    <div class="card-body text-center py-12">
        ${iconTag('h-16 w-16 mx-auto mb-4 opacity-30')}
        <h2 class="text-xl font-semibold mb-2">${t('admin_node_tags.select_a_node')}</h2>
        <p class="opacity-70">${t('admin_node_tags.select_a_node_description')}</p>
    </div>
</div>`;
        }

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <div>
        <h1 class="text-3xl font-bold">${t('entities.tags')}</h1>
        <div class="text-sm breadcrumbs">
            <ul>
                <li><a href="/">${t('entities.home')}</a></li>
                <li><a href="/a/">${t('entities.admin')}</a></li>
                <li>${t('entities.tags')}</li>
            </ul>
        </div>
    </div>
    <a href="/oauth2/sign_out" target="_blank" class="btn btn-outline btn-sm">${t('common.sign_out')}</a>
</div>

${flashHtml}

<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <h2 class="card-title">${t('admin_node_tags.select_node')}</h2>
        <div class="flex gap-4 items-end">
            <div class="form-control flex-1">
                <label class="label"><span class="label-text">${t('common.node')}</span></label>
                <select id="node-selector" class="select select-bordered w-full">
                    <option value="">${t('admin_node_tags.select_node_placeholder')}</option>
                    ${allNodes.map(n => {
                        const name = n.name || t('common.unnamed');
                        const keyPreview = n.public_key.slice(0, 8) + '...' + n.public_key.slice(-4);
                        return html`<option value=${n.public_key} ?selected=${n.public_key === selectedPublicKey}>${name} (${keyPreview})</option>`;
                    })}
                </select>
            </div>
            <button id="load-tags-btn" class="btn btn-primary">${t('admin_node_tags.load_tags')}</button>
        </div>
    </div>
</div>

${contentHtml}`, container);

        // Event: node selector change
        const nodeSelector = container.querySelector('#node-selector');
        nodeSelector.addEventListener('change', () => {
            const pk = nodeSelector.value;
            if (pk) {
                router.navigate('/a/node-tags?public_key=' + encodeURIComponent(pk));
            } else {
                router.navigate('/a/node-tags');
            }
        });

        container.querySelector('#load-tags-btn').addEventListener('click', () => {
            const pk = nodeSelector.value;
            if (pk) {
                router.navigate('/a/node-tags?public_key=' + encodeURIComponent(pk));
            }
        });

        if (selectedPublicKey && selectedNode) {
            let activeTagKey = '';

            // Add tag form
            container.querySelector('#add-tag-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const form = e.target;
                const key = form.key.value.trim();
                const value = form.value.value;
                const value_type = form.value_type.value;

                try {
                    await apiPost('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey) + '/tags', {
                        key, value, value_type,
                    });
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent(t('admin_node_tags.entity_added')));
                } catch (err) {
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                }
            });

            // Edit button handlers
            container.querySelectorAll('.btn-edit').forEach(btn => {
                btn.addEventListener('click', () => {
                    const row = btn.closest('tr');
                    activeTagKey = row.dataset.tagKey;
                    container.querySelector('#editKeyDisplay').value = activeTagKey;
                    container.querySelector('#editValue').value = row.dataset.tagValue;
                    container.querySelector('#editValueType').value = row.dataset.tagType;
                    container.querySelector('#editModal').showModal();
                });
            });

            container.querySelector('#editCancel').addEventListener('click', () => {
                container.querySelector('#editModal').close();
            });

            container.querySelector('#edit-tag-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const value = container.querySelector('#editValue').value;
                const value_type = container.querySelector('#editValueType').value;

                try {
                    await apiPut('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey) + '/tags/' + encodeURIComponent(activeTagKey), {
                        value, value_type,
                    });
                    container.querySelector('#editModal').close();
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent(t('admin_node_tags.entity_updated')));
                } catch (err) {
                    container.querySelector('#editModal').close();
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                }
            });

            // Move button handlers
            container.querySelectorAll('.btn-move').forEach(btn => {
                btn.addEventListener('click', () => {
                    const row = btn.closest('tr');
                    activeTagKey = row.dataset.tagKey;
                    container.querySelector('#moveKeyDisplay').value = activeTagKey;
                    container.querySelector('#moveDestination').selectedIndex = 0;
                    container.querySelector('#moveModal').showModal();
                });
            });

            container.querySelector('#moveCancel').addEventListener('click', () => {
                container.querySelector('#moveModal').close();
            });

            container.querySelector('#move-tag-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const newPublicKey = container.querySelector('#moveDestination').value;
                if (!newPublicKey) return;

                try {
                    await apiPut('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey) + '/tags/' + encodeURIComponent(activeTagKey) + '/move', {
                        new_public_key: newPublicKey,
                    });
                    container.querySelector('#moveModal').close();
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent(t('admin_node_tags.entity_moved')));
                } catch (err) {
                    container.querySelector('#moveModal').close();
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                }
            });

            // Delete button handlers
            container.querySelectorAll('.btn-delete').forEach(btn => {
                btn.addEventListener('click', () => {
                    const row = btn.closest('tr');
                    activeTagKey = row.dataset.tagKey;
                    container.querySelector('#deleteKeyDisplay').textContent = activeTagKey;
                    container.querySelector('#deleteModal').showModal();
                });
            });

            container.querySelector('#deleteCancel').addEventListener('click', () => {
                container.querySelector('#deleteModal').close();
            });

            container.querySelector('#deleteConfirm').addEventListener('click', async () => {
                try {
                    await apiDelete('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey) + '/tags/' + encodeURIComponent(activeTagKey));
                    container.querySelector('#deleteModal').close();
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent(t('admin_node_tags.entity_deleted')));
                } catch (err) {
                    container.querySelector('#deleteModal').close();
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                }
            });

            // Copy All button
            const copyAllBtn = container.querySelector('#btn-copy-all');
            if (copyAllBtn) {
                copyAllBtn.addEventListener('click', () => {
                    container.querySelector('#copyAllDestination').selectedIndex = 0;
                    container.querySelector('#copyAllModal').showModal();
                });

                container.querySelector('#copyAllCancel').addEventListener('click', () => {
                    container.querySelector('#copyAllModal').close();
                });

                container.querySelector('#copy-all-form').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const destKey = container.querySelector('#copyAllDestination').value;
                    if (!destKey) return;

                    try {
                        const result = await apiPost('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey) + '/tags/copy-to/' + encodeURIComponent(destKey));
                        container.querySelector('#copyAllModal').close();
                        const msg = t('admin_node_tags.copied_entities', { copied: result.copied, skipped: result.skipped });
                        router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent(msg));
                    } catch (err) {
                        container.querySelector('#copyAllModal').close();
                        router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                    }
                });
            }

            // Delete All button
            const deleteAllBtn = container.querySelector('#btn-delete-all');
            if (deleteAllBtn) {
                deleteAllBtn.addEventListener('click', () => {
                    container.querySelector('#deleteAllModal').showModal();
                });

                container.querySelector('#deleteAllCancel').addEventListener('click', () => {
                    container.querySelector('#deleteAllModal').close();
                });

                container.querySelector('#deleteAllConfirm').addEventListener('click', async () => {
                    try {
                        await apiDelete('/api/v1/nodes/' + encodeURIComponent(selectedPublicKey) + '/tags');
                        container.querySelector('#deleteAllModal').close();
                        router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent(t('admin_node_tags.all_entities_deleted')));
                    } catch (err) {
                        container.querySelector('#deleteAllModal').close();
                        router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                    }
                });
            }
        }

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
