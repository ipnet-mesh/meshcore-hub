import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, formatDateTime, formatDateTimeShort, formatNumber,
    warningBadge,
    pagination, sortableTableHeader, mobileSortSelect,
    renderFilterForm, renderFilterToggle, autoSubmit, submitOnEnter, copyToClipboard, renderNodeDisplay, t
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

export async function render(container, params, router) {
    const { signal } = params || {};
    const query = params.query || {};
    const search = query.search || '';
    const adv_type = query.adv_type || '';
    const adopted_by = query.adopted_by || '';
    const pubkey_prefix = query.pubkey_prefix || '';
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 20;
    const offset = (page - 1) * limit;
    const sort = query.sort || 'last_seen';
    const order = query.order || 'desc';

    const config = getConfig();
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);

    let lastContent = nothing;
    let lastTotal = null;
    let currentFilterFields = [];
    const hasActiveFilters = search !== '' || adv_type !== '' || pubkey_prefix !== '' || (config.oidc_enabled && adopted_by !== '');

    function onFilterToggle() { renderPage(lastContent, { total: lastTotal }); }

    function renderPage(content, { total = null, error = null } = {}) {
        if (!error) {
            lastContent = content;
            lastTotal = total;
        }
        const displayContent = error ? lastContent : content;
        const displayTotal = error ? lastTotal : total;
        const existingToggle = container.querySelector('#filter-toggle');
        const filterOpen = existingToggle ? existingToggle.checked : hasActiveFilters;
        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.nodes')}</h1>
    ${tzBadge}
</div>
<div class="flex items-center gap-2 mb-4">
    ${displayTotal !== null
        ? html`<span class="badge badge-lg">${t('common.total', { count: formatNumber(displayTotal) })}</span>`
        : nothing}
    ${error ? warningBadge(error) : nothing}
    <div class="ml-auto flex items-center gap-3">
        <span id="auto-refresh-toggle"></span>
    </div>
    <div class="ml-4">${renderFilterToggle({ open: filterOpen, onChange: onFilterToggle })}</div>
</div>
${(filterOpen && currentFilterFields.length > 0)
    ? html`<div class="mb-4">${renderFilterForm({ fields: currentFilterFields, basePath: '/nodes', navigate })}</div>`
    : nothing}
${displayContent}`, container);
    }

    renderPage(nothing);

    async function fetchAndRenderData() {
        try {
            const apiParams = { limit, offset, search, adv_type, sort, order };
            if (adopted_by) apiParams.adopted_by = adopted_by;
            if (pubkey_prefix) apiParams.pubkey_prefix = pubkey_prefix;
            const fetches = [apiGet('/api/v1/nodes', apiParams, { signal })];
            if (config.oidc_enabled) {
                fetches.push(apiGet('/api/v1/user/profiles', { limit: 500 }, { signal }));
            }
            const results = await Promise.all(fetches);
            const data = results[0];
            const operatorRole = config.role_names?.operator || 'operator';
            const profiles = config.oidc_enabled
                ? (results[1]?.items || []).filter(p => p.roles && p.roles.includes(operatorRole))
                : [];

            const nodes = data.items || [];
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);

            const mobileCards = nodes.length === 0
                ? html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.nodes').toLowerCase() })}</div>`
                : nodes.map(node => {
                    const tagName = node.tags?.find(tag => tag.key === 'name')?.value;
                    const tagDescription = node.tags?.find(tag => tag.key === 'description')?.value;
                    const displayName = tagName || node.name;
                    const lastSeen = node.last_seen ? formatDateTimeShort(node.last_seen) : '-';
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
                    </div>
                </div>
            </div>
        </a>`;
                });

            const tableRows = nodes.length === 0
                ? html`<tr><td colspan="3" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.nodes').toLowerCase() })}</td></tr>`
                : nodes.map(node => {
                    const tagName = node.tags?.find(tag => tag.key === 'name')?.value;
                    const tagDescription = node.tags?.find(tag => tag.key === 'description')?.value;
                    const displayName = tagName || node.name;
                    const lastSeen = node.last_seen ? formatDateTime(node.last_seen) : '-';
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
                </tr>`;
                });

            const paginationBlock = pagination(page, totalPages, '/nodes', {
                search, adv_type, adopted_by, pubkey_prefix, limit, sort, order,
            });

            const filterFields = [
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('common.search')}</span>
                </label>
                <input type="text" name="search" .value=${search} placeholder="${t('common.search_placeholder')}" class="input input-sm w-80" @keydown=${submitOnEnter} />
            </div>`,
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('common.type')}</span>
                </label>
                <select name="adv_type" class="select select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_types')}</option>
                    <option value="chat" ?selected=${adv_type === 'chat'}>${t('node_types.chat')}</option>
                    <option value="repeater" ?selected=${adv_type === 'repeater'}>${t('node_types.repeater')}</option>
                    <option value="companion" ?selected=${adv_type === 'companion'}>${t('node_types.companion')}</option>
                    <option value="room" ?selected=${adv_type === 'room'}>${t('node_types.room')}</option>
                </select>
            </div>`,
            ];
            if (config.oidc_enabled && profiles.length > 0) {
                filterFields.push(() => html`
            <div class="flex flex-col gap-1 max-w-56">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('common.filter_operator_label')}</span>
                </label>
                <select name="adopted_by" class="select select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${!adopted_by}>${t('common.all_operators')}</option>
                    ${profiles.sort((a, b) => {
                        const na = a.name || a.callsign || '';
                        const nb = b.name || b.callsign || '';
                        return na.localeCompare(nb);
                    }).map(p => html`
                    <option value=${p.id} ?selected=${adopted_by === p.id}>
                        ${p.callsign ? p.name + ' (' + p.callsign + ')' : (p.name || p.callsign || p.user_id || p.id)}
                    </option>`)}
                </select>
            </div>`);
            }

            const headerParams = { search, adv_type, adopted_by, pubkey_prefix, limit };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/nodes', params: headerParams,
            });

            currentFilterFields = filterFields;

            renderPage(html`

${mobileSortSelect({
    currentSort: sort, currentOrder: order,
    navigate, basePath: '/nodes',
    params: headerParams,
    options: [
        { value: 'last_seen:desc', label: t('nodes.sort.last_seen_newest') },
        { value: 'last_seen:asc', label: t('nodes.sort.last_seen_oldest') },
        { value: 'name:asc', label: t('nodes.sort.name_az') },
        { value: 'name:desc', label: t('nodes.sort.name_za') },
        { value: 'public_key:asc', label: t('nodes.sort.key_asc') },
        { value: 'public_key:desc', label: t('nodes.sort.key_desc') },
    ],
})}

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto bg-base-100 rounded-box shadow-sm">
    <table class="table table-zebra">
        <thead>
            <tr>
                ${sortable(t('entities.node'), 'name')}
                ${sortable(t('common.public_key'), 'public_key')}
                ${sortable(t('common.last_seen'), 'last_seen')}
            </tr>
        </thead>
        <tbody>
            ${tableRows}
        </tbody>
    </table>
</div>

${paginationBlock}`, { total });

        } catch (e) {
            if (isAbortError(e)) return;
            renderPage(nothing, { error: e.message });
        }
    }

    await fetchAndRenderData();

    const toggleEl = container.querySelector('#auto-refresh-toggle');
    const { cleanup } = createAutoRefresh({
        fetchAndRender: fetchAndRenderData,
        toggleContainer: toggleEl,
    });
    return cleanup;
}
