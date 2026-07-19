import { apiGet, apiPost, apiPut, apiDelete, isAbortError } from '../api.js';
import { html, litRender, nothing, t, errorAlert, getConfig, hasRole } from '../components.js';
import { iconChannel, iconPlus, iconEdit, iconTrash } from '../icons.js';

const VISIBILITY_ORDER = ['community', 'member', 'operator', 'admin'];

function renderVisibilityBadge(visibility, oidcEnabled) {
    if (!oidcEnabled) return nothing;
    return html`<span class="badge badge-primary badge-sm">${visibility}</span>`;
}

function renderChannelCard(channel, { oidcEnabled, isAdmin, onDelete, onEdit, onNavigate }) {
    const visibilityBadge = renderVisibilityBadge(channel.visibility, oidcEnabled);
    const enabledBadge = !channel.enabled
        ? html`<span class="badge badge-ghost badge-sm">${t('channels.disabled')}</span>`
        : nothing;

    const channelIdx = parseInt(channel.channel_hash, 16);
    const qrId = `qr-${channel.id}`;

    const adminButtons = isAdmin
        ? html`<div class="flex gap-2 mt-2">
            <button class="btn btn-xs btn-outline" @click=${(e) => { e.stopPropagation(); onEdit(channel); }}>
                ${iconEdit('h-3 w-3')} ${t('common.edit')}
            </button>
            <button class="btn btn-xs btn-outline btn-error" @click=${(e) => { e.stopPropagation(); onDelete(channel); }}>
                ${iconTrash('h-3 w-3')} ${t('common.delete')}
            </button>
        </div>`
        : nothing;

    const keyDisplay = channel.key_hex
        ? html`<div class="font-mono text-xs opacity-70 mt-1 break-all select-all">${channel.key_hex.toLowerCase()}</div>`
        : nothing;

    const qrPlaceholder = channel.key_hex
        ? html`<div id="${qrId}" class="qr-container"></div>`
        : nothing;

    return html`<div class="card bg-base-100 shadow-xl cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" role="button" tabindex="0"
        @click=${() => onNavigate(channelIdx)}
        @keydown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate(channelIdx); } }}>
        <div class="card-body flex-row gap-4">
            <div class="flex-1 min-w-0">
                <h2 class="card-title flex items-center gap-2">
                    ${channel.name}
                    ${visibilityBadge}
                    ${enabledBadge}
                </h2>
                ${keyDisplay}
                ${adminButtons}
            </div>
            <div class="flex-shrink-0 self-center">
                ${qrPlaceholder}
            </div>
        </div>
    </div>`;
}

function renderAddButton(onAdd) {
    return html`<button class="btn btn-primary btn-sm" @click=${onAdd}>
        ${iconPlus('h-4 w-4')} ${t('channels.add_channel')}
    </button>`;
}

function renderChannelModal({ channel, isEdit, onSave, onCancel, saving }) {
    const title = isEdit ? t('channels.edit_channel') : t('channels.add_channel');

    return html`<dialog open class="modal modal-open">
        <div class="modal-box">
            <h3 class="font-bold text-lg mb-4">${title}</h3>
            <form @submit=${(e) => { e.preventDefault(); onSave(); }}>
                <div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 items-center mb-4">
                    <label class="text-sm opacity-70 text-right">${t('channels.name_label')}</label>
                    <input type="text" id="channel-modal-name" class="input input-sm"
                        .value=${isEdit ? channel.name : ''}
                        ?disabled=${isEdit}
                        placeholder="${t('channels.name_label')}"
                        required maxlength="100" />
                    ${!isEdit ? html`
                    <label class="text-sm opacity-70 text-right">${t('channels.key_label')}</label>
                    <input type="text" id="channel-modal-key" class="input input-sm font-mono"
                        placeholder="e.g. ABCDEF0123456789..."
                        required minlength="32" maxlength="64"
                        pattern="[0-9A-Fa-f]{32,64}" />` : nothing}
                    <label class="text-sm opacity-70 text-right">${t('channels.visibility_label')}</label>
                    <select id="channel-modal-visibility" class="select select-sm">
                        <option value="community" .selected=${channel?.visibility === 'community' || !channel}>community</option>
                        <option value="member" .selected=${channel?.visibility === 'member'}>member</option>
                        <option value="operator" .selected=${channel?.visibility === 'operator'}>operator</option>
                        <option value="admin" .selected=${channel?.visibility === 'admin'}>admin</option>
                    </select>
                    <div></div>
                    <label class="label cursor-pointer justify-start gap-3">
                        <input type="checkbox" id="channel-modal-enabled" class="checkbox checkbox-sm"
                            .checked=${channel?.enabled !== false} />
                        <span class="text-sm">${t('channels.enabled_label')}</span>
                    </label>
                </div>
                <div class="modal-action">
                    <button type="button" class="btn btn-ghost" @click=${onCancel} ?disabled=${saving}>${t('common.cancel')}</button>
                    <button type="submit" class="btn btn-primary" ?disabled=${saving}>${saving ? html`<span class="loading loading-spinner loading-sm"></span> ` : null}${t('common.save')}</button>
                </div>
            </form>
        </div>
        <form method="dialog" class="modal-backdrop"><button @click=${onCancel}></button></form>
    </dialog>`;
}

function renderDeleteModal({ channel, onConfirm, onCancel, saving }) {
    return html`<dialog open class="modal modal-open">
        <div class="modal-box">
            <h3 class="font-bold text-lg mb-4">${t('channels.delete_channel')}</h3>
            <p>${t('channels.delete_confirm', { name: channel.name })}</p>
            <div class="modal-action">
                <button class="btn btn-ghost" @click=${onCancel} ?disabled=${saving}>${t('common.cancel')}</button>
                <button class="btn btn-error" @click=${onConfirm} ?disabled=${saving}>${saving ? html`<span class="loading loading-spinner loading-sm"></span> ` : null}${t('common.delete')}</button>
            </div>
        </div>
        <form method="dialog" class="modal-backdrop"><button @click=${onCancel}></button></form>
    </dialog>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    try {
        const config = getConfig();
        const oidcEnabled = config.oidc_enabled;
        const isAdmin = hasRole('admin');

        const data = await apiGet('/api/v1/channels', {}, { signal });
        const channels = data.items || [];

        let modalState = null;

        async function refresh() {
            const newData = await apiGet('/api/v1/channels');
            renderPage(newData.items || []);
        }

        function renderPage(channelsList) {
            const adminHeader = isAdmin
                ? html`<div class="flex justify-end mb-4">${renderAddButton(handleAdd)}</div>`
                : nothing;

            const emptyMessage = channelsList.length === 0
                ? html`<div class="text-center py-8 opacity-70">
                    ${t('common.no_entity_found', { entity: t('entities.channels').toLowerCase() })}
                </div>`
                : nothing;

            const groups = new Map();
            for (const vis of VISIBILITY_ORDER) {
                groups.set(vis, []);
            }
            for (const ch of channelsList) {
                const vis = ch.visibility || 'community';
                if (!groups.has(vis)) groups.set(vis, []);
                groups.get(vis).push(ch);
            }

            const cardOpts = {
                oidcEnabled,
                isAdmin,
                onDelete: handleDeleteClick,
                onEdit: handleEditClick,
                onNavigate: (idx) => router.navigate(`/messages?channel_idx=${idx}`),
            };

            const groupedSections = [];
            for (const vis of VISIBILITY_ORDER) {
                const group = groups.get(vis);
                if (!group || group.length === 0) continue;
                groupedSections.push(html`
                    <h2 class="text-lg font-semibold mt-6 mb-3 opacity-70">${t(`channels.visibility_${vis}`)}</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${group.map(ch => renderChannelCard(ch, cardOpts))}
                    </div>
                `);
            }

            let modalHtml = nothing;
            if (modalState?.type === 'add' || modalState?.type === 'edit') {
                modalHtml = renderChannelModal({
                    channel: modalState.channel,
                    isEdit: modalState.type === 'edit',
                    onSave: handleSave,
                    onCancel: () => { modalState = null; renderPage(channelsList); },
                    saving: !!modalState.saving,
                });
            } else if (modalState?.type === 'delete') {
                modalHtml = renderDeleteModal({
                    channel: modalState.channel,
                    onConfirm: handleDeleteConfirm,
                    onCancel: () => { modalState = null; renderPage(channelsList); },
                    saving: !!modalState.saving,
                });
            }

            litRender(html`
                <div class="mb-6">
                    <h1 class="text-3xl font-bold flex items-center gap-2">
                        ${iconChannel('h-8 w-8')}
                        ${t('channels.title')}
                    </h1>
                </div>
                ${adminHeader}
                ${emptyMessage}
                ${groupedSections}
                ${modalHtml}
            `, container);

            channelsList.forEach(ch => {
                const qrEl = document.getElementById(`qr-${ch.id}`);
                if (qrEl && !qrEl.hasChildNodes() && ch.key_hex) {
                    const qrUrl = `meshcore://channel/add?name=${encodeURIComponent(ch.name)}&secret=${ch.key_hex.toLowerCase()}`;
                    new QRCode(qrEl, {
                        text: qrUrl,
                        width: 128,
                        height: 128,
                        correctLevel: QRCode.CorrectLevel.M,
                    });
                }
            });
        }

        function handleAdd() {
            modalState = { type: 'add', channel: { visibility: 'community', enabled: true } };
            renderPage(channels);
        }

        function handleEditClick(channel) {
            modalState = { type: 'edit', channel };
            renderPage(channels);
        }

        function handleDeleteClick(channel) {
            modalState = { type: 'delete', channel };
            renderPage(channels);
        }

        async function handleSave() {
            const nameEl = document.getElementById('channel-modal-name');
            const keyEl = document.getElementById('channel-modal-key');
            const visEl = document.getElementById('channel-modal-visibility');
            const enabledEl = document.getElementById('channel-modal-enabled');

            const isEdit = modalState.type === 'edit';
            const body = {
                visibility: visEl.value,
                enabled: enabledEl.checked,
            };

            if (!isEdit) {
                body.name = nameEl.value.trim();
                body.key_hex = keyEl.value.trim().toUpperCase();
            } else {
                if (keyEl && keyEl.value) {
                    body.key_hex = keyEl.value.trim().toUpperCase();
                }
            }

            modalState = { ...modalState, saving: true };
            renderPage(channels);
            try {
                if (isEdit) {
                    await apiPut(`/api/v1/channels/${modalState.channel.id}`, body);
                } else {
                    await apiPost('/api/v1/channels', body);
                }
                modalState = null;
                await refresh();
            } catch (e) {
                modalState = { ...modalState, saving: false };
                renderPage(channels);
                alert(e.message || 'Failed to save channel');
            }
        }

        async function handleDeleteConfirm() {
            modalState = { ...modalState, saving: true };
            renderPage(channels);
            try {
                await apiDelete(`/api/v1/channels/${modalState.channel.id}`);
                modalState = null;
                await refresh();
            } catch (e) {
                modalState = { ...modalState, saving: false };
                renderPage(channels);
                alert(e.message || 'Failed to delete channel');
            }
        }

        renderPage(channels);

    } catch (e) {
        if (isAbortError(e)) return;
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
