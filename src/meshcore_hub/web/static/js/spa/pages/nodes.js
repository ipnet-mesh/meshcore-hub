import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, typeEmoji, formatDateTime, formatDateTimeShort,
    truncateKey, errorAlert,
    pagination, timezoneIndicator,
    createFilterHandler, autoSubmit, submitOnEnter
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
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);

    function renderPage(content, { total = null } = {}) {
        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">Nodes</h1>
    <div class="flex items-center gap-2">
        ${tzBadge}
        ${total !== null ? html`<span class="badge badge-lg">${total} total</span>` : nothing}
    </div>
</div>
${content}`, container);
    }

    // Render page header immediately (old content stays visible until data loads)
    renderPage(nothing);

    try {
        const [data, membersData] = await Promise.all([
            apiGet('/api/v1/nodes', { limit, offset, search, adv_type, member_id }),
            apiGet('/api/v1/members', { limit: 100 }),
        ]);

        const nodes = data.items || [];
        const total = data.total || 0;
        const totalPages = Math.ceil(total / limit);
        const members = membersData.items || [];

        const membersFilter = members.length > 0
            ? html`
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">Member</span>
                </label>
                <select name="member_id" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">All Members</option>
                    ${members.map(m => html`<option value=${m.member_id} ?selected=${member_id === m.member_id}>${m.name}${m.callsign ? ` (${m.callsign})` : ''}</option>`)}
                </select>
            </div>`
            : nothing;

        const mobileCards = nodes.length === 0
            ? html`<div class="text-center py-8 opacity-70">No nodes found.</div>`
            : nodes.map(node => {
                const tagName = node.tags?.find(t => t.key === 'name')?.value;
                const displayName = tagName || node.name;
                const emoji = typeEmoji(node.adv_type);
                const nameBlock = displayName
                    ? html`<div class="font-medium text-sm truncate">${displayName}</div>
                           <div class="text-xs font-mono opacity-60 truncate">${node.public_key.slice(0, 16)}...</div>`
                    : html`<div class="font-mono text-sm truncate">${node.public_key.slice(0, 16)}...</div>`;
                const lastSeen = node.last_seen ? formatDateTimeShort(node.last_seen) : '-';
                const tags = node.tags || [];
                const tagsBlock = tags.length > 0
                    ? html`<div class="flex gap-1 justify-end mt-1">
                        ${tags.slice(0, 2).map(t => html`<span class="badge badge-ghost badge-xs">${t.key}</span>`)}
                        ${tags.length > 2 ? html`<span class="badge badge-ghost badge-xs">+${tags.length - 2}</span>` : nothing}
                    </div>`
                    : nothing;
                return html`<a href="/nodes/${node.public_key}" class="card bg-base-100 shadow-sm block">
        <div class="card-body p-3">
            <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 min-w-0">
                    <span class="text-lg flex-shrink-0" title=${node.adv_type || 'Unknown'}>${emoji}</span>
                    <div class="min-w-0">
                        ${nameBlock}
                    </div>
                </div>
                <div class="text-right flex-shrink-0">
                    <div class="text-xs opacity-60">${lastSeen}</div>
                    ${tagsBlock}
                </div>
            </div>
        </div>
    </a>`;
            });

        const tableRows = nodes.length === 0
            ? html`<tr><td colspan="3" class="text-center py-8 opacity-70">No nodes found.</td></tr>`
            : nodes.map(node => {
                const tagName = node.tags?.find(t => t.key === 'name')?.value;
                const displayName = tagName || node.name;
                const emoji = typeEmoji(node.adv_type);
                const nameBlock = displayName
                    ? html`<div class="font-medium">${displayName}</div>
                           <div class="text-xs font-mono opacity-70">${node.public_key.slice(0, 16)}...</div>`
                    : html`<span class="font-mono text-sm">${node.public_key.slice(0, 16)}...</span>`;
                const lastSeen = node.last_seen ? formatDateTime(node.last_seen) : '-';
                const tags = node.tags || [];
                const tagsBlock = tags.length > 0
                    ? html`<div class="flex gap-1 flex-wrap">
                        ${tags.slice(0, 3).map(t => html`<span class="badge badge-ghost badge-xs">${t.key}</span>`)}
                        ${tags.length > 3 ? html`<span class="badge badge-ghost badge-xs">+${tags.length - 3}</span>` : nothing}
                    </div>`
                    : html`<span class="opacity-50">-</span>`;
                return html`<tr class="hover">
                <td>
                    <a href="/nodes/${node.public_key}" class="link link-hover flex items-center gap-2">
                        <span class="text-lg" title=${node.adv_type || 'Unknown'}>${emoji}</span>
                        <div>
                            ${nameBlock}
                        </div>
                    </a>
                </td>
                <td class="text-sm whitespace-nowrap">${lastSeen}</td>
                <td>${tagsBlock}</td>
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
                    <span class="label-text">Search</span>
                </label>
                <input type="text" name="search" .value=${search} placeholder="Search by name, ID, or public key..." class="input input-bordered input-sm w-80" @keydown=${submitOnEnter} />
            </div>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">Type</span>
                </label>
                <select name="adv_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">All Types</option>
                    <option value="chat" ?selected=${adv_type === 'chat'}>Chat</option>
                    <option value="repeater" ?selected=${adv_type === 'repeater'}>Repeater</option>
                    <option value="room" ?selected=${adv_type === 'room'}>Room</option>
                </select>
            </div>
            ${membersFilter}
            <div class="flex gap-2 w-full sm:w-auto">
                <button type="submit" class="btn btn-primary btn-sm">Filter</button>
                <a href="/nodes" class="btn btn-ghost btn-sm">Clear</a>
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
                <th>Node</th>
                <th>Last Seen</th>
                <th>Tags</th>
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
