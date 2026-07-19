import { apiGet, apiPost, apiPut, apiDelete, isAbortError } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, hasRole, typeEmoji, formatDateTime,
    truncateKey, errorAlert, successAlert, copyToClipboard, t,
} from '../components.js';
import { iconError, iconPlus, iconEdit, iconTrash } from '../icons.js';

let _mapInstance = null;

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

function renderEditTagModal() {
    return html`
<dialog id="tagEditModal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">${t('common.edit_entity', { entity: t('entities.tag') })}: <span id="tagEditKeyDisplay" class="font-mono text-base font-normal"></span></h3>
        <form id="tag-edit-form" class="py-4">
            <input type="hidden" id="tagEditKey">
            <div class="fieldset mb-4">
                <label class="fieldset-label">${t('common.value')}</label>
                <input type="text" id="tagEditValue" class="input w-full">
                <div class="hidden text-xs text-error" id="tagEditError"></div>
            </div>
            <div class="fieldset mb-4">
                <label class="fieldset-label">${t('common.type')}</label>
                <select id="tagEditType" class="select w-full">
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                </select>
            </div>
            <div class="modal-action">
                <button type="button" class="btn" id="tagEditCancel">${t('common.cancel')}</button>
                <button type="submit" class="btn btn-primary" id="tagEditSubmit">${t('common.save_changes')}</button>
            </div>
        </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${t('common.close')}</button></form>
</dialog>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    const cleanupFns = [];
    let publicKey = params.publicKey;

    try {
        if (publicKey.length !== 64) {
            const resolved = await apiGet('/api/v1/nodes/prefix/' + encodeURIComponent(publicKey), {}, { signal });
            router.navigate('/nodes/' + resolved.public_key, true);
            return;
        }

        const [node, adsData, telemetryData] = await Promise.all([
            apiGet('/api/v1/nodes/' + publicKey, {}, { signal }),
            apiGet('/api/v1/advertisements', { public_key: publicKey, limit: 10 }, { signal }),
            apiGet('/api/v1/telemetry', { node_public_key: publicKey, limit: 10 }, { signal }),
        ]);

        if (!node) {
            litRender(renderNotFound(publicKey), container);
            return;
        }

        const config = getConfig();
        const tagName = node.tags?.find(t => t.key === 'name')?.value;
        const tagDescription = node.tags?.find(t => t.key === 'description')?.value;
        const displayName = tagName || node.name || t('common.unnamed_node');
        const emoji = typeEmoji(node.adv_type);

        let lat = node.lat;
        let lon = node.lon;
        if (!lat || !lon) {
            for (const tag of node.tags || []) {
                if (tag.key === 'lat' && !lat) lat = parseFloat(tag.value);
                if (tag.key === 'lon' && !lon) lon = parseFloat(tag.value);
            }
        }
        const hasCoords = lat != null && lon != null && !(lat === 0 && lon === 0);

        const advertisements = adsData.items || [];

        const heroHtml = hasCoords
            ? html`
<div class="relative rounded-box overflow-hidden mb-6 shadow-xl" style="height: 180px;">
    <div id="header-map" class="absolute inset-0 z-0"></div>
    <div class="relative z-20 h-full p-3 flex items-center justify-end">
        <div id="qr-code" class="bg-white p-2 rounded-box shadow-lg"></div>
    </div>
</div>`
            : html`
<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body flex-row items-center gap-4">
        <div id="qr-code" class="bg-white p-2 rounded-box"></div>
        <p class="text-sm opacity-70">${t('nodes.scan_to_add')}</p>
    </div>
</div>`;

        const coordsHtml = hasCoords
            ? html`<div><span class="opacity-70">${t('common.location')}:</span> ${lat}, ${lon}</div>`
            : nothing;

        const adsTableHtml = advertisements.length > 0
            ? html`<div class="overflow-x-auto">
                <table class="table table-sm w-full">
                    <thead>
                        <tr>
                            <th>${t('common.time')}</th>
                            <th>${t('common.type')}</th>
                            <th>${t('common.received_by')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${advertisements.map(adv => {
                            const advEmoji = adv.adv_type ? typeEmoji(adv.adv_type) : '';
                            const advTypeHtml = adv.adv_type
                                ? html`<span title=${adv.adv_type.charAt(0).toUpperCase() + adv.adv_type.slice(1)}>${advEmoji}</span>`
                                : html`<span class="opacity-50">-</span>`;
                            const recvName = adv.observed_by ? (adv.observer_tag_name || adv.observer_name) : null;
                            const receiverHtml = !adv.observed_by
                                ? html`<span class="opacity-50">-</span>`
                                : recvName
                                    ? html`<a href="/nodes/${adv.observed_by}" class="link link-hover">
                                        <div class="font-medium text-sm truncate max-w-[8rem]">${recvName}</div>
                                        <div class="text-xs font-mono opacity-70 hidden sm:block">${adv.observed_by.slice(0, 16)}...</div>
                                    </a>`
                                    : html`<a href="/nodes/${adv.observed_by}" class="link link-hover">
                                        <span class="font-mono text-xs">${adv.observed_by.slice(0, 12)}...</span>
                                    </a>`;
                            return html`<tr>
                                <td class="text-xs whitespace-nowrap">${formatDateTime(adv.received_at)}</td>
                                <td>${advTypeHtml}</td>
                                <td>${receiverHtml}</td>
                            </tr>`;
                        })}
                    </tbody>
                </table>
            </div>`
            : html`<p class="opacity-70">${t('common.no_entity_recorded', { entity: t('entities.advertisements').toLowerCase() })}</p>`;

        const tags = node.tags || [];
        const canEditTags = config.oidc_enabled && config.user && (
            hasRole('admin') || (hasRole('operator') && node.adopted_by?.user_id === config.user.sub)
        );

        const tagsTableHtml = canEditTags
            ? (tags.length > 0
                ? html`<div class="overflow-x-auto">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr>
                                <th>${t('common.key')}</th>
                                <th>${t('common.value')}</th>
                                <th class="hidden sm:table-cell">${t('common.type')}</th>
                                <th class="w-16">${t('common.actions')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${tags.map(tag => html`<tr>
                                <td class="font-mono min-w-0 truncate max-w-[8rem]">${tag.key}</td>
                                <td class="min-w-0 truncate max-w-[12rem]">${tag.value || ''}</td>
                                <td class="hidden sm:table-cell opacity-70">${tag.value_type || 'string'}</td>
                                <td>
                                    <div class="flex gap-1">
                                        <button class="btn btn-xs btn-ghost tag-edit-btn" data-key=${tag.key} data-value=${tag.value || ''} data-type=${tag.value_type || 'string'}>${iconEdit('h-4 w-4')}</button>
                                        <button class="btn btn-xs btn-ghost tag-delete-btn" data-key=${tag.key}>${iconTrash('h-4 w-4')}</button>
                                    </div>
                                </td>
                            </tr>`)}
                        </tbody>
                    </table>
                </div>`
                : html`<p class="opacity-70">${t('common.no_entity_defined', { entity: t('entities.tags').toLowerCase() })}</p>`)
            : (tags.length > 0
                ? html`<div class="overflow-x-auto">
                    <table class="table table-sm w-full">
                        <thead>
                            <tr>
                                <th>${t('common.key')}</th>
                                <th>${t('common.value')}</th>
                                <th>${t('common.type')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${tags.map(tag => html`<tr>
                                <td class="font-mono">${tag.key}</td>
                                <td>${tag.value || ''}</td>
                                <td class="opacity-70">${tag.value_type || 'string'}</td>
                            </tr>`)}
                        </tbody>
                    </table>
                </div>`
                : html`<p class="opacity-70">${t('common.no_entity_defined', { entity: t('entities.tags').toLowerCase() })}</p>`);

        const addTagFormHtml = canEditTags
            ? html`<form id="tag-add-form" class="mt-4">
                <div class="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-2 items-end">
                    <div class="fieldset">
                        <input type="text" name="key" class="input input-sm w-full" placeholder=${t('common.key')} required>
                    </div>
                    <div class="fieldset">
                        <input type="text" name="value" class="input input-sm w-full" placeholder=${t('common.value')}>
                        <div class="hidden text-xs text-error" id="tagAddError"></div>
                    </div>
                    <select name="value_type" class="select select-sm w-28">
                        <option value="string">string</option>
                        <option value="number">number</option>
                        <option value="boolean">boolean</option>
                    </select>
                    <button type="submit" class="btn btn-sm btn-primary">${iconPlus('h-4 w-4')} ${t('common.add')}</button>
                </div>
            </form>`
            : nothing;

        const adoptionHtml = renderAdoptionSection(node, config);

        const flashMessage = (params.query && params.query.message) || '';
        const flashError = (params.query && params.query.error) || '';
        const flashHtml = flashMessage ? successAlert(flashMessage) : flashError ? errorAlert(flashError) : nothing;

        const infoGridHtml = adoptionHtml
            ? html`<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <div>
                <h3 class="font-semibold opacity-70 mb-2">${t('common.public_key')}</h3>
                <code class="text-sm bg-base-200 p-2 rounded block break-all cursor-pointer hover:bg-base-300 select-all"
                      @click=${(e) => copyToClipboard(e, node.public_key)}
                      title="Click to copy">${node.public_key}</code>
            </div>
            <div class="flex flex-wrap gap-x-8 gap-y-2 mt-4 text-sm">
                <div><span class="opacity-70">${t('common.first_seen_label')}</span> ${formatDateTime(node.first_seen)}</div>
                <div><span class="opacity-70">${t('common.last_seen_label')}</span> ${formatDateTime(node.last_seen)}</div>
                ${coordsHtml}
            </div>
        </div>
    </div>
    ${adoptionHtml}
</div>`
            : html`<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <div>
            <h3 class="font-semibold opacity-70 mb-2">${t('common.public_key')}</h3>
            <code class="text-sm bg-base-200 p-2 rounded block break-all cursor-pointer hover:bg-base-300 select-all"
                  @click=${(e) => copyToClipboard(e, node.public_key)}
                  title="Click to copy">${node.public_key}</code>
        </div>
        <div class="flex flex-wrap gap-x-8 gap-y-2 mt-4 text-sm">
            <div><span class="opacity-70">${t('common.first_seen_label')}</span> ${formatDateTime(node.first_seen)}</div>
            <div><span class="opacity-70">${t('common.last_seen_label')}</span> ${formatDateTime(node.last_seen)}</div>
            ${coordsHtml}
        </div>
    </div>
</div>`;

        litRender(html`
<div class="breadcrumbs text-sm mb-4">
    <ul>
        <li><a href="/">${t('entities.home')}</a></li>
        <li><a href="/nodes">${t('entities.nodes')}</a></li>
        <li>${tagName || node.name || node.public_key.slice(0, 12) + '...'}</li>
    </ul>
</div>

<div class="flex items-start gap-4 mb-6">
    <span class="text-6xl flex-shrink-0" title=${node.adv_type || t('node_types.unknown')}>${emoji}</span>
    <div class="flex-1 min-w-0">
        <h1 class="text-3xl font-bold">${displayName}</h1>
        ${tagDescription ? html`<p class="opacity-70 mt-2">${tagDescription}</p>` : nothing}
    </div>
</div>

${flashHtml}

<div id="flash-container"></div>

${heroHtml}

${infoGridHtml}

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">${t('common.recent_entity', { entity: t('entities.advertisements') })}</h2>
            ${adsTableHtml}
        </div>
    </div>

    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">${t('entities.tags')}</h2>
            ${tagsTableHtml}
            ${addTagFormHtml}
        </div>
    </div>
</div>

${canEditTags ? renderDeleteTagModal() : nothing}
${canEditTags ? renderEditTagModal() : nothing}`, container);
        if (hasCoords && typeof L !== 'undefined') {
            const mapEl = document.getElementById('header-map');
            if (mapEl) {
                if (_mapInstance) {
                    try { _mapInstance.remove(); } catch (e) { /* ignore */ }
                    _mapInstance = null;
                }
                if (mapEl._leaflet_id != null) {
                    delete mapEl._leaflet_id;
                }
            }
            const map = L.map('header-map', {
                zoomControl: false, dragging: false, scrollWheelZoom: false,
                doubleClickZoom: false, boxZoom: false, keyboard: false,
                attributionControl: false,
            });
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            map.setView([lat, lon], 14);
            const point = map.latLngToContainerPoint([lat, lon]);
            const newPoint = L.point(point.x + map.getSize().x * 0.17, point.y);
            const newLatLng = map.containerPointToLatLng(newPoint);
            map.setView(newLatLng, 14, { animate: false });
            const mapIcon = L.divIcon({
                html: '<span style="font-size: 32px; text-shadow: 0 0 3px #1a237e, 0 0 6px #1a237e, 0 1px 2px rgba(0,0,0,0.7);">' + emoji + '</span>',
                className: '', iconSize: [32, 32], iconAnchor: [16, 16],
            });
            L.marker([lat, lon], { icon: mapIcon }).addTo(map);
            _mapInstance = map;
            cleanupFns.push(() => { _mapInstance = null; try { map.remove(); } catch (e) { /* ignore */ } });
        }

        // Initialize QR code - wait for both DOM element and QRCode library
        const initQr = () => {
            const qrEl = document.getElementById('qr-code');
            if (!qrEl || typeof QRCode === 'undefined') return false;
            const typeMap = { chat: 1, repeater: 2, room: 3, companion: 1, sensor: 4 };
            const typeNum = typeMap[(node.adv_type || '').toLowerCase()] || 1;
            const url = 'meshcore://contact/add?name=' + encodeURIComponent(displayName) + '&public_key=' + node.public_key + '&type=' + typeNum;
            new QRCode(qrEl, {
                text: url, width: 140, height: 140,
                colorDark: '#000000', colorLight: '#ffffff',
                correctLevel: QRCode.CorrectLevel.L,
            });
            return true;
        };
        if (!initQr()) {
            let attempts = 0;
            const qrInterval = setInterval(() => {
                if (initQr() || ++attempts >= 20) clearInterval(qrInterval);
            }, 100);
            cleanupFns.push(() => clearInterval(qrInterval));
        }

        // Wire up adoption buttons
        const adoptReleaseAc = new AbortController();
        const adoptReleaseSignal = adoptReleaseAc.signal;
        cleanupFns.push(() => adoptReleaseAc.abort());

        const adoptBtn = container.querySelector('.btn-adopt-node');
        if (adoptBtn) {
            adoptBtn.addEventListener('click', async () => {
                try {
                    await apiPost('/api/v1/adoptions', { public_key: node.public_key });
                    router.navigate('/nodes/' + node.public_key + '?message=' + encodeURIComponent(t('nodes.adopt_success')), true);
                } catch (err) {
                    router.navigate('/nodes/' + node.public_key + '?error=' + encodeURIComponent(err.message), true);
                }
            }, { signal: adoptReleaseSignal });
        }

        const releaseBtn = container.querySelector('.btn-release-node');
        if (releaseBtn) {
            releaseBtn.addEventListener('click', async () => {
                if (!confirm(t('nodes.release_confirm'))) return;
                try {
                    await apiDelete('/api/v1/adoptions/' + node.public_key);
                    router.navigate('/nodes/' + node.public_key + '?message=' + encodeURIComponent(t('nodes.release_success')), true);
                } catch (err) {
                    router.navigate('/nodes/' + node.public_key + '?error=' + encodeURIComponent(err.message), true);
                }
            }, { signal: adoptReleaseSignal });
        }

        // Tag editor event handlers
        if (canEditTags) {
            const ac = new AbortController();
            const { signal } = ac;
            cleanupFns.push(() => ac.abort());

            const refreshNode = async () => {
                const fresh = await apiGet('/api/v1/nodes/' + node.public_key);
                return fresh;
            };

            const showFlash = (type, message) => {
                const flashContainer = container.querySelector('#flash-container');
                if (!flashContainer) return;
                litRender(type === 'success' ? successAlert(message) : errorAlert(message), flashContainer);
                setTimeout(() => {
                    if (flashContainer) litRender(nothing, flashContainer);
                }, 3000);
            };

            // Add tag form
            const addForm = container.querySelector('#tag-add-form');
            if (addForm) {
                addForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const formData = new FormData(addForm);
                    const key = formData.get('key');
                    const value = formData.get('value') || '';
                    const valueType = formData.get('value_type');
                    const errEl = container.querySelector('#tagAddError');

                    const validationError = validateTagValue(value, valueType);
                    if (validationError) {
                        if (errEl) { errEl.textContent = validationError; errEl.classList.remove('hidden'); }
                        return;
                    }
                    if (errEl) { errEl.textContent = ''; errEl.classList.add('hidden'); }

                    try {
                        await apiPost('/api/v1/nodes/' + node.public_key + '/tags', { key, value, value_type: valueType });
                        showFlash('success', t('common.entity_added_success', { entity: t('entities.tag') }));
                        addForm.reset();
                        router.navigate('/nodes/' + node.public_key, true);
                    } catch (err) {
                        showFlash('error', err.message);
                    }
                }, { signal });
            }

            // Edit buttons
            container.querySelectorAll('.tag-edit-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const modal = container.querySelector('#tagEditModal');
                    const keyInput = container.querySelector('#tagEditKey');
                    const keyDisplay = container.querySelector('#tagEditKeyDisplay');
                    const valueInput = container.querySelector('#tagEditValue');
                    const typeSelect = container.querySelector('#tagEditType');
                    const errorLabel = container.querySelector('#tagEditError');

                    keyInput.value = btn.dataset.key;
                    if (keyDisplay) keyDisplay.textContent = btn.dataset.key;
                    valueInput.value = btn.dataset.value;
                    typeSelect.value = btn.dataset.type;
                    if (errorLabel) { errorLabel.textContent = ''; errorLabel.classList.add('hidden'); }
                    modal.showModal();
                }, { signal });
            });

            // Edit form submit
            const editForm = container.querySelector('#tag-edit-form');
            if (editForm) {
                editForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const key = container.querySelector('#tagEditKey').value;
                    const value = container.querySelector('#tagEditValue').value;
                    const valueType = container.querySelector('#tagEditType').value;
                    const errorLabel = container.querySelector('#tagEditError');

                    const validationError = validateTagValue(value, valueType);
                    if (validationError) {
                        if (errorLabel) { errorLabel.textContent = validationError; errorLabel.classList.remove('hidden'); }
                        return;
                    }
                    if (errorLabel) { errorLabel.textContent = ''; errorLabel.classList.add('hidden'); }

                    const submitBtn = container.querySelector('#tagEditSubmit');
                    const cancelBtn = container.querySelector('#tagEditCancel');
                    const orig = submitBtn.innerHTML;
                    submitBtn.disabled = true;
                    cancelBtn.disabled = true;
                    submitBtn.innerHTML = `<span class="loading loading-spinner loading-sm"></span> ${orig}`;
                    try {
                        await apiPut('/api/v1/nodes/' + node.public_key + '/tags/' + encodeURIComponent(key), { value, value_type: valueType });
                        container.querySelector('#tagEditModal').close();
                        showFlash('success', t('common.entity_updated_success', { entity: t('entities.tag') }));
                        router.navigate('/nodes/' + node.public_key, true);
                    } catch (err) {
                        if (errorLabel) { errorLabel.textContent = err.message; errorLabel.classList.remove('hidden'); }
                    } finally {
                        submitBtn.disabled = false;
                        cancelBtn.disabled = false;
                        submitBtn.innerHTML = orig;
                    }
                }, { signal });
            }

            // Edit cancel
            const editCancel = container.querySelector('#tagEditCancel');
            if (editCancel) {
                editCancel.addEventListener('click', () => {
                    container.querySelector('#tagEditModal').close();
                }, { signal });
            }

            // Delete buttons
            container.querySelectorAll('.tag-delete-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const modal = container.querySelector('#tagDeleteModal');
                    const msg = container.querySelector('#tag-delete-msg');
                        msg.innerHTML = t('common.delete_entity_confirm', { entity: t('entities.tag'), name: btn.dataset.key });
                    modal._tagKey = btn.dataset.key;
                    modal.showModal();
                }, { signal });
            });

            // Delete confirm
            const deleteConfirm = container.querySelector('#tagDeleteConfirm');
            if (deleteConfirm) {
                deleteConfirm.addEventListener('click', async () => {
                    const modal = container.querySelector('#tagDeleteModal');
                    const key = modal._tagKey;
                    const cancelBtn = container.querySelector('#tagDeleteCancel');
                    const orig = deleteConfirm.innerHTML;
                    deleteConfirm.disabled = true;
                    cancelBtn.disabled = true;
                    deleteConfirm.innerHTML = `<span class="loading loading-spinner loading-sm"></span> ${orig}`;
                    try {
                        await apiDelete('/api/v1/nodes/' + node.public_key + '/tags/' + encodeURIComponent(key));
                        modal.close();
                        showFlash('success', t('common.entity_deleted_success', { entity: t('entities.tag') }));
                        router.navigate('/nodes/' + node.public_key, true);
                    } catch (err) {
                        modal.close();
                        showFlash('error', err.message);
                    } finally {
                        deleteConfirm.disabled = false;
                        cancelBtn.disabled = false;
                        deleteConfirm.innerHTML = orig;
                    }
                }, { signal });
            }

            // Delete cancel
            const deleteCancel = container.querySelector('#tagDeleteCancel');
            if (deleteCancel) {
                deleteCancel.addEventListener('click', () => {
                    container.querySelector('#tagDeleteModal').close();
                }, { signal });
            }
        }

        return () => {
            cleanupFns.forEach(fn => fn());
        };
    } catch (e) {
        if (isAbortError(e)) return;
        if (e.message && e.message.includes('404')) {
            litRender(renderNotFound(publicKey), container);
        } else {
            litRender(errorAlert(e.message), container);
        }
    }
}

function renderAdoptionSection(node, config) {
    if (!config.oidc_enabled || !config.user) return nothing;

    const isOperator = hasRole('operator');
    const isAdmin = hasRole('admin');
    if (!isOperator && !isAdmin) {
        if (node.adopted_by) {
            const ownerName = node.adopted_by.name || node.adopted_by.user_id;
            return html`<div class="card bg-base-100 shadow-xl h-full">
                <div class="card-body">
                    <h2 class="card-title">${t('nodes.ownership')}</h2>
                    <p class="text-sm opacity-70">
                        ${t('nodes.adopted_by_prefix')}
                        <a href="/profile/${node.adopted_by.profile_id}" class="link link-hover text-primary">${ownerName}</a>
                    </p>
                </div>
            </div>`;
        }
        return nothing;
    }

    if (node.adopted_by) {
        const ownerName = node.adopted_by.name || node.adopted_by.user_id;
        const isOwner = node.adopted_by.user_id === config.user.sub;
        const canRelease = isOwner || isAdmin;

        const releaseBtnHtml = canRelease
            ? html`<button class="btn btn-sm btn-outline btn-error btn-release-node">${t('nodes.release')}</button>`
            : nothing;

        return html`<div class="card bg-base-100 shadow-xl h-full">
            <div class="card-body">
                <h2 class="card-title">${t('nodes.ownership')}</h2>
                <div class="flex items-center justify-between">
                    <p class="text-sm opacity-70">
                        ${t('nodes.adopted_by_prefix')}
                        <a href="/profile/${node.adopted_by.profile_id}" class="link link-hover text-primary">${ownerName}</a>
                    </p>
                    ${releaseBtnHtml}
                </div>
            </div>
        </div>`;
    }

    return html`<div class="card bg-base-100 shadow-xl h-full">
        <div class="card-body">
            <h2 class="card-title">${t('nodes.ownership')}</h2>
            <p class="text-sm opacity-70">${t('nodes.not_adopted')}</p>
            <div class="mt-2">
                <button class="btn btn-sm btn-primary btn-adopt-node">${t('nodes.adopt')}</button>
            </div>
        </div>
    </div>`;
}

function renderNotFound(publicKey) {
    return html`
<div class="breadcrumbs text-sm mb-4">
    <ul>
        <li><a href="/">${t('entities.home')}</a></li>
        <li><a href="/nodes">${t('entities.nodes')}</a></li>
        <li>${t('common.page_not_found')}</li>
    </ul>
</div>
<div class="alert alert-error">
    ${iconError('stroke-current shrink-0 h-6 w-6')}
    <span>${t('common.entity_not_found_details', { entity: t('entities.node'), details: publicKey })}</span>
</div>
<a href="/nodes" class="btn btn-primary mt-4">${t('common.view_entity', { entity: t('entities.nodes') })}</a>`;
}
