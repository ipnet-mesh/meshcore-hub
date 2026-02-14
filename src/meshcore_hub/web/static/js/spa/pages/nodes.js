import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, formatDateTime, formatDateTimeShort,
    truncateKey, errorAlert,
    pagination, timezoneIndicator,
    createFilterHandler, autoSubmit, submitOnEnter, copyToClipboard, renderNodeDisplay, t
} from '../components.js';

export async function render(container, params, router) {
    const query = params.query || {};
    const search = query.search || '';
    const adv_type = query.adv_type || '';
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
    <h1 class="text-3xl font-bold">${t('entities.nodes')}</h1>
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
            apiGet('/api/v1/nodes', { limit, offset, search, adv_type, member_id }),
        ];
        if (showMembers) {
            requests.push(apiGet('/api/v1/members', { limit: 100 }));
        }

        const results = await Promise.all(requests);
        const data = results[0];
        const membersData = showMembers ? results[1] : null;

        const nodes = data.items || [];
        const total = data.total || 0;
        const totalPages = Math.ceil(total / limit);
        const members = membersData?.items || [];

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

        const mobileCards = nodes.length === 0
            ? html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.nodes').toLowerCase() })}</div>`
            : nodes.map(node => {
                const tagName = node.tags?.find(tag => tag.key === 'name')?.value;
                const tagDescription = node.tags?.find(tag => tag.key === 'description')?.value;
                const displayName = tagName || node.name;
                const lastSeen = node.last_seen ? formatDateTimeShort(node.last_seen) : '-';
                const memberIdTag = showMembers ? node.tags?.find(tag => tag.key === 'member_id')?.value : null;
                const member = memberIdTag ? members.find(m => m.member_id === memberIdTag) : null;
                const memberBlock = (showMembers && member)
                    ? html`<div class="text-xs opacity-60">${member.name}</div>`
                    : nothing;
                return html`<a href="/nodes/${node.public_key}" class="card bg-base-100 shadow-sm block">
        <div class="card-body p-3">
            <div class="flex items-center justify-between gap-2">
                ${renderNodeDisplay({
                    name: displayName,
                    description: tagDescription,
                    publicKey: node.public_key,
                    advType: node.adv_type,
                    size: 'sm'
                })}
                <div class="text-right flex-shrink-0">
                    <div class="text-xs opacity-60">${lastSeen}</div>
                    ${memberBlock}
                </div>
            </div>
        </div>
    </a>`;
            });

        const tableColspan = showMembers ? 4 : 3;
        const tableRows = nodes.length === 0
            ? html`<tr><td colspan="${tableColspan}" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.nodes').toLowerCase() })}</td></tr>`
            : nodes.map(node => {
                const tagName = node.tags?.find(tag => tag.key === 'name')?.value;
                const tagDescription = node.tags?.find(tag => tag.key === 'description')?.value;
                const displayName = tagName || node.name;
                const lastSeen = node.last_seen ? formatDateTime(node.last_seen) : '-';
                const memberIdTag = showMembers ? node.tags?.find(tag => tag.key === 'member_id')?.value : null;
                const member = memberIdTag ? members.find(m => m.member_id === memberIdTag) : null;
                const memberBlock = member
                    ? html`${member.name}${member.callsign ? html` <span class="opacity-60">(${member.callsign})</span>` : nothing}`
                    : html`<span class="opacity-50">-</span>`;
                return html`<tr class="hover">
                <td>
                    <a href="/nodes/${node.public_key}" class="link link-hover">
                        ${renderNodeDisplay({
                            name: displayName,
                            description: tagDescription,
                            publicKey: node.public_key,
                            advType: node.adv_type,
                            size: 'base'
                        })}
                    </a>
                </td>
                <td>
                    <code class="font-mono text-xs cursor-pointer hover:bg-base-200 px-1 py-0.5 rounded select-all"
                          @click=${(e) => copyToClipboard(e, node.public_key)}
                          title="Click to copy">${node.public_key}</code>
                </td>
                <td class="text-sm whitespace-nowrap">${lastSeen}</td>
                ${showMembers ? html`<td class="text-sm">${memberBlock}</td>` : nothing}
            </tr>`;
            });

        const paginationBlock = pagination(page, totalPages, '/nodes', {
            search, adv_type, member_id, limit,
        });

        renderPage(html`
<div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
    <div class="card-body py-4">
        <form method="GET" action="/nodes" class="flex gap-4 flex-wrap items-end" @submit=${createFilterHandler('/nodes', navigate)}>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">${t('common.search')}</span>
                </label>
                <input type="text" name="search" .value=${search} placeholder="${t('common.search_placeholder')}" class="input input-bordered input-sm w-80" @keydown=${submitOnEnter} />
            </div>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">${t('common.type')}</span>
                </label>
                <select name="adv_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_types')}</option>
                    <option value="chat" ?selected=${adv_type === 'chat'}>${t('node_types.chat')}</option>
                    <option value="repeater" ?selected=${adv_type === 'repeater'}>${t('node_types.repeater')}</option>
                    <option value="room" ?selected=${adv_type === 'room'}>${t('node_types.room')}</option>
                </select>
            </div>
            ${membersFilter}
            <div class="flex gap-2 w-full sm:w-auto">
                <button type="submit" class="btn btn-primary btn-sm">${t('common.filter')}</button>
                <a href="/nodes" class="btn btn-ghost btn-sm">${t('common.clear')}</a>
            </div>
        </form>
    </div>
</div>

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto bg-base-100 rounded-box shadow">
    <table class="table table-zebra">
        <thead>
            <tr>
                <th>${t('entities.node')}</th>
                <th>${t('common.public_key')}</th>
                <th>${t('common.last_seen')}</th>
                ${showMembers ? html`<th>${t('entities.member')}</th>` : nothing}
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
