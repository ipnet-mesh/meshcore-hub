import { apiGet, apiPost, apiPut, apiDelete } from '../../api.js';
import {
    html, litRender, nothing,
    getConfig, typeEmoji, formatDateTimeShort, errorAlert,
    successAlert, truncateKey,
} from '../../components.js';
import { iconTag, iconLock } from '../../icons.js';

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
            const nodeName = selectedNode.name || 'Unnamed Node';
            const otherNodes = allNodes.filter(n => n.public_key !== selectedPublicKey);

            const tagsTableHtml = tags.length > 0
                ? html`
                <div class="overflow-x-auto">
                    <table class="table table-zebra">
                        <thead>
                            <tr>
                                <th>Key</th>
                                <th>Value</th>
                                <th>Type</th>
                                <th>Updated</th>
                                <th class="w-48">Actions</th>
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
                                        <button class="btn btn-ghost btn-xs btn-edit">Edit</button>
                                        <button class="btn btn-ghost btn-xs btn-move">Move</button>
                                        <button class="btn btn-ghost btn-xs text-error btn-delete">Delete</button>
                                    </div>
                                </td>
                            </tr>`)}</tbody>
                    </table>
                </div>`
                : html`
                <div class="text-center py-8 text-base-content/60">
                    <p>No tags found for this node.</p>
                    <p class="text-sm mt-2">Add a new tag below.</p>
                </div>`;

            const bulkButtons = tags.length > 0
                ? html`
                <button id="btn-copy-all" class="btn btn-outline btn-sm">Copy All</button>
                <button id="btn-delete-all" class="btn btn-outline btn-error btn-sm">Delete All</button>`
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
                <a href="/nodes/${encodeURIComponent(selectedPublicKey)}" class="btn btn-ghost btn-sm">View Node</a>
            </div>
        </div>
    </div>
</div>

<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <h2 class="card-title">Tags (${tags.length})</h2>
        ${tagsTableHtml}
    </div>
</div>

<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title">Add New Tag</h2>
        <form id="add-tag-form" class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="form-control">
                <label class="label"><span class="label-text">Key</span></label>
                <input type="text" name="key" class="input input-bordered" placeholder="tag_name" required maxlength="100">
            </div>
            <div class="form-control">
                <label class="label"><span class="label-text">Value</span></label>
                <input type="text" name="value" class="input input-bordered" placeholder="tag value">
            </div>
            <div class="form-control">
                <label class="label"><span class="label-text">Type</span></label>
                <select name="value_type" class="select select-bordered">
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                </select>
            </div>
            <div class="form-control">
                <label class="label"><span class="label-text">&nbsp;</span></label>
                <button type="submit" class="btn btn-primary">Add Tag</button>
            </div>
        </form>
    </div>
</div>

<dialog id="editModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Edit Tag</h3>
        <form id="edit-tag-form" class="py-4">
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Key</span></label>
                <input type="text" id="editKeyDisplay" class="input input-bordered" disabled>
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Value</span></label>
                <input type="text" id="editValue" class="input input-bordered">
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Type</span></label>
                <select id="editValueType" class="select select-bordered w-full">
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                </select>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="editCancel">Cancel</button>
                <button type="submit" class="btn btn-primary">Save Changes</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>

<dialog id="moveModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Move Tag to Another Node</h3>
        <form id="move-tag-form" class="py-4">
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Tag Key</span></label>
                <input type="text" id="moveKeyDisplay" class="input input-bordered" disabled>
            </div>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Destination Node</span></label>
                <select id="moveDestination" class="select select-bordered w-full" required>
                    <option value="">-- Select destination node --</option>
                    ${otherNodes.map(n => {
                        const name = n.name || 'Unnamed';
                        const keyPreview = n.public_key.slice(0, 8) + '...' + n.public_key.slice(-4);
                        return html`<option value=${n.public_key}>${name} (${keyPreview})</option>`;
                    })}
                </select>
            </div>
            <div class="alert alert-warning mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>This will move the tag from the current node to the destination node.</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="moveCancel">Cancel</button>
                <button type="submit" class="btn btn-warning">Move Tag</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>

<dialog id="deleteModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Delete Tag</h3>
        <div class="py-4">
            <p class="py-4">Are you sure you want to delete the tag "<span id="deleteKeyDisplay" class="font-mono font-semibold"></span>"?</p>
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
</dialog>

<dialog id="copyAllModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Copy All Tags to Another Node</h3>
        <form id="copy-all-form" class="py-4">
            <p class="mb-4">Copy all ${tags.length} tag(s) from <strong>${nodeName}</strong> to another node.</p>
            <div class="form-control mb-4">
                <label class="label"><span class="label-text">Destination Node</span></label>
                <select id="copyAllDestination" class="select select-bordered w-full" required>
                    <option value="">-- Select destination node --</option>
                    ${otherNodes.map(n => {
                        const name = n.name || 'Unnamed';
                        const keyPreview = n.public_key.slice(0, 8) + '...' + n.public_key.slice(-4);
                        return html`<option value=${n.public_key}>${name} (${keyPreview})</option>`;
                    })}
                </select>
            </div>
            <div class="alert alert-info mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <span>Tags that already exist on the destination node will be skipped. Original tags remain on this node.</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="copyAllCancel">Cancel</button>
                <button type="submit" class="btn btn-primary">Copy Tags</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>

<dialog id="deleteAllModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Delete All Tags</h3>
        <div class="py-4">
            <p class="mb-4">Are you sure you want to delete all ${tags.length} tag(s) from <strong>${nodeName}</strong>?</p>
            <div class="alert alert-error mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>This action cannot be undone. All tags will be permanently deleted.</span>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="deleteAllCancel">Cancel</button>
                <button type="button" class="btn btn-error" id="deleteAllConfirm">Delete All Tags</button>
            </div>
        </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>close</button></form>
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
        <h2 class="text-xl font-semibold mb-2">Select a Node</h2>
        <p class="opacity-70">Choose a node from the dropdown above to view and manage its tags.</p>
    </div>
</div>`;
        }

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <div>
        <h1 class="text-3xl font-bold">Node Tags</h1>
        <div class="text-sm breadcrumbs">
            <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/a/">Admin</a></li>
                <li>Node Tags</li>
            </ul>
        </div>
    </div>
    <a href="/oauth2/sign_out" target="_blank" class="btn btn-outline btn-sm">Sign Out</a>
</div>

${flashHtml}

<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <h2 class="card-title">Select Node</h2>
        <div class="flex gap-4 items-end">
            <div class="form-control flex-1">
                <label class="label"><span class="label-text">Node</span></label>
                <select id="node-selector" class="select select-bordered w-full">
                    <option value="">-- Select a node --</option>
                    ${allNodes.map(n => {
                        const name = n.name || 'Unnamed';
                        const keyPreview = n.public_key.slice(0, 8) + '...' + n.public_key.slice(-4);
                        return html`<option value=${n.public_key} ?selected=${n.public_key === selectedPublicKey}>${name} (${keyPreview})</option>`;
                    })}
                </select>
            </div>
            <button id="load-tags-btn" class="btn btn-primary">Load Tags</button>
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
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent('Tag added successfully'));
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
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent('Tag updated successfully'));
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
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent('Tag moved successfully'));
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
                    router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent('Tag deleted successfully'));
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
                        const msg = `Copied ${result.copied} tag(s), skipped ${result.skipped}`;
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
                        router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&message=' + encodeURIComponent('All tags deleted successfully'));
                    } catch (err) {
                        container.querySelector('#deleteAllModal').close();
                        router.navigate('/a/node-tags?public_key=' + encodeURIComponent(selectedPublicKey) + '&error=' + encodeURIComponent(err.message));
                    }
                });
            }
        }

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load node tags'), container);
    }
}
