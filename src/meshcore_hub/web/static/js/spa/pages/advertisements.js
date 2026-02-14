import { apiGet } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort,
    truncateKey, errorAlert,
    pagination, createFilterHandler, autoSubmit, submitOnEnter, copyToClipboard, renderNodeDisplay
} from '../components.js';

export async function render(container, params, router) {
    const query = params.query || {};
    const search = query.search || '';
    const public_key = query.public_key || '';
    const member_id = query.member_id || '';
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 20;
    const offset = (page - 1) * limit;

    const config = getConfig();
    const features = config.features || {};
    const showMembers = features.members !== false;
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);

    function renderPage(content, { total = null } = {}) {
        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.advertisements')}</h1>
    <div class="flex items-center gap-2">
        ${tzBadge}
        ${total !== null ? html`<span class="badge badge-lg">${t('common.total', { count: total })}</span>` : nothing}
    </div>
</div>
${content}`, container);
    }

    // Render page header immediately (old content stays visible until data loads)
    renderPage(nothing);

    try {
        const requests = [
            apiGet('/api/v1/advertisements', { limit, offset, search, public_key, member_id }),
            apiGet('/api/v1/nodes', { limit: 500 }),
        ];
        if (showMembers) {
            requests.push(apiGet('/api/v1/members', { limit: 100 }));
        }

        const results = await Promise.all(requests);
        const data = results[0];
        const nodesData = results[1];
        const membersData = showMembers ? results[2] : null;

        const advertisements = data.items || [];
        const total = data.total || 0;
        const totalPages = Math.ceil(total / limit);
        const allNodes = nodesData.items || [];
        const members = membersData?.items || [];

        const sortedNodes = allNodes.map(n => {
            const tagName = n.tags?.find(t => t.key === 'name')?.value;
            return { ...n, _sortName: (tagName || n.name || '').toLowerCase(), _displayName: tagName || n.name || n.public_key.slice(0, 12) + '...' };
        }).sort((a, b) => a._sortName.localeCompare(b._sortName));

        const nodesFilter = sortedNodes.length > 0
            ? html`
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">${t('entities.node')}</span>
                </label>
                <select name="public_key" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_entity', { entity: t('entities.nodes') })}</option>
                    ${sortedNodes.map(n => html`<option value=${n.public_key} ?selected=${public_key === n.public_key}>${n._displayName}</option>`)}
                </select>
            </div>`
            : nothing;

        const membersFilter = (showMembers && members.length > 0)
            ? html`
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">${t('entities.member')}</span>
                </label>
                <select name="member_id" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_entity', { entity: t('entities.members') })}</option>
                    ${members.map(m => html`<option value=${m.member_id} ?selected=${member_id === m.member_id}>${m.name}${m.callsign ? ` (${m.callsign})` : ''}</option>`)}
                </select>
            </div>`
            : nothing;

        const mobileCards = advertisements.length === 0
            ? html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.advertisements').toLowerCase() })}</div>`
            : advertisements.map(ad => {
                const adName = ad.node_tag_name || ad.node_name || ad.name;
                const adDescription = ad.node_tag_description;
                let receiversBlock = nothing;
                if (ad.receivers && ad.receivers.length >= 1) {
                    receiversBlock = html`<div class="flex gap-0.5 justify-end mt-1">
                        ${ad.receivers.map(recv => {
                            const recvName = recv.tag_name || recv.name || truncateKey(recv.public_key, 12);
                            return html`<span class="text-sm" title=${recvName}>\u{1F4E1}</span>`;
                        })}
                    </div>`;
                } else if (ad.received_by) {
                    const recvTitle = ad.receiver_tag_name || ad.receiver_name || truncateKey(ad.received_by, 12);
                    receiversBlock = html`<span class="text-sm" title=${recvTitle}>\u{1F4E1}</span>`;
                }
                return html`<a href="/nodes/${ad.public_key}" class="card bg-base-100 shadow-sm block">
        <div class="card-body p-3">
            <div class="flex items-center justify-between gap-2">
                ${renderNodeDisplay({
                    name: adName,
                    description: adDescription,
                    publicKey: ad.public_key,
                    advType: ad.adv_type,
                    size: 'sm'
                })}
                <div class="text-right flex-shrink-0">
                    <div class="text-xs opacity-60">${formatDateTimeShort(ad.received_at)}</div>
                    ${receiversBlock}
                </div>
            </div>
        </div>
    </a>`;
            });

        const tableRows = advertisements.length === 0
            ? html`<tr><td colspan="4" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.advertisements').toLowerCase() })}</td></tr>`
            : advertisements.map(ad => {
                const adName = ad.node_tag_name || ad.node_name || ad.name;
                const adDescription = ad.node_tag_description;
                let receiversBlock;
                if (ad.receivers && ad.receivers.length >= 1) {
                    receiversBlock = html`<div class="flex gap-1">
                        ${ad.receivers.map(recv => {
                            const recvName = recv.tag_name || recv.name || truncateKey(recv.public_key, 12);
                            return html`<a href="/nodes/${recv.public_key}" class="text-lg hover:opacity-70" title=${recvName}>\u{1F4E1}</a>`;
                        })}
                    </div>`;
                } else if (ad.received_by) {
                    const recvTitle = ad.receiver_tag_name || ad.receiver_name || truncateKey(ad.received_by, 12);
                    receiversBlock = html`<a href="/nodes/${ad.received_by}" class="text-lg hover:opacity-70" title=${recvTitle}>\u{1F4E1}</a>`;
                } else {
                    receiversBlock = html`<span class="opacity-50">-</span>`;
                }
                return html`<tr class="hover">
                <td>
                    <a href="/nodes/${ad.public_key}" class="link link-hover">
                        ${renderNodeDisplay({
                            name: adName,
                            description: adDescription,
                            publicKey: ad.public_key,
                            advType: ad.adv_type,
                            size: 'base'
                        })}
                    </a>
                </td>
                <td>
                    <code class="font-mono text-xs cursor-pointer hover:bg-base-200 px-1 py-0.5 rounded select-all"
                          @click=${(e) => copyToClipboard(e, ad.public_key)}
                          title="Click to copy">${ad.public_key}</code>
                </td>
                <td class="text-sm whitespace-nowrap">${formatDateTime(ad.received_at)}</td>
                <td>${receiversBlock}</td>
            </tr>`;
            });

        const paginationBlock = pagination(page, totalPages, '/advertisements', {
            search, public_key, member_id, limit,
        });

        renderPage(html`
<div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
    <div class="card-body py-4">
        <form method="GET" action="/advertisements" class="flex gap-4 flex-wrap items-end" @submit=${createFilterHandler('/advertisements', navigate)}>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">${t('common.search')}</span>
                </label>
                <input type="text" name="search" .value=${search} placeholder="${t('common.search_placeholder')}" class="input input-bordered input-sm w-80" @keydown=${submitOnEnter} />
            </div>
            ${nodesFilter}
            ${membersFilter}
            <div class="flex gap-2 w-full sm:w-auto">
                <button type="submit" class="btn btn-primary btn-sm">${t('common.filter')}</button>
                <a href="/advertisements" class="btn btn-ghost btn-sm">${t('common.clear')}</a>
            </div>
        </form>
    </div>
</div>

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow">
    <table class="table table-zebra">
        <thead>
            <tr>
                <th>${t('entities.node')}</th>
                <th>${t('common.public_key')}</th>
                <th>${t('common.time')}</th>
                <th>${t('common.receivers')}</th>
            </tr>
        </thead>
        <tbody>
            ${tableRows}
        </tbody>
    </table>
</div>

${paginationBlock}`, { total });

    } catch (e) {
        renderPage(errorAlert(e.message));
    }
}
