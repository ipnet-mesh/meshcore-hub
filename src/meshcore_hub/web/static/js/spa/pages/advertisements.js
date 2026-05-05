import { apiGet } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort, formatRelativeTime,
    warningBadge,
    pagination, sortableTableHeader, mobileSortSelect,
    renderFilterCard, autoSubmit, submitOnEnter, copyToClipboard, renderNodeDisplay,
    observerIcons, observerDetailRow, toggleObserverDetail, toggleCardObserverDetail
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

export async function render(container, params, router) {
    const query = params.query || {};
    const search = query.search || '';
    const observed_by = query.observed_by
        ? (Array.isArray(query.observed_by) ? query.observed_by : [query.observed_by])
        : [];
    const adopted_by = query.adopted_by || '';
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 20;
    const offset = (page - 1) * limit;
    const sort = query.sort || 'time';
    const order = query.order || 'desc';

    const config = getConfig();
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);

    let lastContent = nothing;
    let lastTotal = null;

    function renderPage(content, { total = null, error = null } = {}) {
        if (!error) {
            lastContent = content;
            lastTotal = total;
        }
        const displayContent = error ? lastContent : content;
        const displayTotal = error ? lastTotal : total;
        litRender(html`
<div class="flex items-center justify-between mb-4">
    <h1 class="text-3xl font-bold">${t('entities.advertisements')}</h1>
    ${tzBadge}
</div>
<div class="flex items-center gap-2 mb-4">
    ${displayTotal !== null
        ? html`<span class="badge badge-lg">${t('common.total', { count: displayTotal })}</span>`
        : nothing}
    <span id="auto-refresh-toggle"></span>
    ${error ? warningBadge(error) : nothing}
</div>
${displayContent}`, container);
    }

    renderPage(nothing);

    async function fetchAndRenderData() {
        try {
            const apiParams = { limit, offset, search, sort, order };
            if (observed_by.length > 0) apiParams.observed_by = observed_by;
            if (adopted_by) apiParams.adopted_by = adopted_by;
            const fetches = [
                apiGet('/api/v1/advertisements', apiParams),
                apiGet('/api/v1/nodes', { limit: 500, observer: true }),
            ];
            if (config.oidc_enabled) {
                fetches.push(apiGet('/api/v1/user/profiles', { limit: 500 }));
            }
            const results = await Promise.all(fetches);
            const data = results[0];
            const nodesData = results[1];
            const profiles = config.oidc_enabled ? (results[2]?.items || []) : [];

            const advertisements = data.items || [];
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);
            const allNodes = nodesData.items || [];

            const sortedNodes = allNodes.map(n => {
                const tagName = n.tags?.find(t => t.key === 'name')?.value;
                return { ...n, _sortName: (tagName || n.name || '').toLowerCase(), _displayName: tagName || n.name || n.public_key.slice(0, 12) + '...' };
            }).sort((a, b) => a._sortName.localeCompare(b._sortName));

            const nodesFilter = sortedNodes.length > 0
                ? html`
                <div class="flex flex-col gap-1">
                    <label class="flex items-center py-1">
                        <span class="opacity-80 text-sm">${t('common.filter_observer_label')}</span>
                    </label>
                    <select name="observed_by" multiple size="2"
                            class="select select-bordered select-sm w-full max-w-xs">
                        ${sortedNodes.map(n => html`
                            <option value=${n.public_key}
                                    ?selected=${observed_by.includes(n.public_key)}>
                                ${n._displayName}
                            </option>
                        `)}
                    </select>
                </div>`
                : nothing;

            const mobileCards = advertisements.length === 0
                ? html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.advertisements').toLowerCase() })}</div>`
                : advertisements.map(ad => {
                    const adName = ad.node_tag_name || ad.node_name || ad.name;
                    const adDescription = ad.node_tag_description;
                    let receiversBlock = nothing;
                    if (ad.observers && ad.observers.length >= 1) {
                        receiversBlock = html`<span @click=${toggleCardObserverDetail} class="cursor-pointer">${observerIcons(ad.observers)}</span>`;
                    } else if (ad.observed_by) {
                        receiversBlock = html`<span class="opacity-50 text-xs">\u{1F4E1}</span>`;
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
                ${ad.observers && ad.observers.length > 0 ? html`
                    <div class="observer-detail-card hidden mt-2">
                        <table class="table table-xs w-full">
                            <thead><tr><th>Observer</th><th>${t('common.snr_db')}</th><th>Received</th></tr></thead>
                            <tbody>
                                ${ad.observers.map(o => {
                                    const dn = o.tag_name || o.name || o.public_key.slice(0, 12);
                                    const snrD = o.snr != null ? `${Number(o.snr).toFixed(1)}` : '\u2014';
                                    const timeD = formatRelativeTime(o.observed_at);
                                    return html`<tr>
                                        <td>\u{1F4E1} <a href="/nodes/${o.public_key}" class="link link-hover">${dn}</a></td>
                                        <td>${snrD}</td>
                                        <td><span title=${formatDateTime(o.observed_at)}>${timeD}</span></td>
                                    </tr>`;
                                })}
                            </tbody>
                        </table>
                    </div>
                ` : nothing}
            </div>
        </a>`;
                });

            const tableRows = advertisements.length === 0
                ? html`<tr><td colspan="4" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.advertisements').toLowerCase() })}</td></tr>`
                : advertisements.map(ad => {
                    const adName = ad.node_tag_name || ad.node_name || ad.name;
                    const adDescription = ad.node_tag_description;
                    let receiversBlock;
                    if (ad.observers && ad.observers.length >= 1) {
                        receiversBlock = html`${observerIcons(ad.observers)}`;
                    } else if (ad.observed_by) {
                        receiversBlock = html`<span class="opacity-50">\u{1F4E1}</span>`;
                    } else {
                        receiversBlock = html`<span class="opacity-50">-</span>`;
                    }
                    return html`<tr class="hover cursor-pointer" @click=${toggleObserverDetail}>
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
                </tr>${observerDetailRow(ad.observers || [], null, { hidePath: true })}`;
                });

            const paginationBlock = pagination(page, totalPages, '/advertisements', {
                search, observed_by, adopted_by, limit, sort, order,
            });

            const filterFields = [
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('common.search')}</span>
                </label>
                <input type="text" name="search" .value=${search} placeholder="${t('common.search_placeholder')}" class="input input-bordered input-sm w-80" @keydown=${submitOnEnter} />
            </div>`,
            ];
            if (config.oidc_enabled && profiles.length > 0) {
                filterFields.push(() => html`
            <div class="flex flex-col gap-1 max-w-56">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('common.filter_member_label')}</span>
                </label>
                <select name="adopted_by" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${!adopted_by}>${t('common.all_members')}</option>
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
            if (sortedNodes.length > 0) {
                filterFields.push(() => nodesFilter);
            }

            const hasActiveFilters = search !== '' || observed_by.length > 0 || (config.oidc_enabled && adopted_by !== '');
            const existingDetails = container.querySelector('details.collapse');
            const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;

            const filterCard = renderFilterCard({
                fields: filterFields,
                basePath: '/advertisements',
                navigate,
                collapsible: true,
                defaultOpen: isFilterOpen,
            });

            const headerParams = { search, observed_by, adopted_by, limit };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/advertisements', params: headerParams,
            });

            renderPage(html`${filterCard}

${mobileSortSelect({
    currentSort: sort, currentOrder: order,
    navigate, basePath: '/advertisements',
    params: headerParams,
    options: [
        { value: 'time:desc', label: t('advertisements.sort.newest') },
        { value: 'time:asc', label: t('advertisements.sort.oldest') },
        { value: 'node_name:asc', label: t('advertisements.sort.node_az') },
        { value: 'node_name:desc', label: t('advertisements.sort.node_za') },
        { value: 'public_key:asc', label: t('advertisements.sort.key_asc') },
        { value: 'public_key:desc', label: t('advertisements.sort.key_desc') },
    ],
})}

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow">
    <table class="table table-zebra">
        <thead>
            <tr>
                ${sortable(t('entities.node'), 'node_name')}
                ${sortable(t('common.public_key'), 'public_key')}
                ${sortable(t('common.time'), 'time')}
                <th>${t('common.observers')}</th>
            </tr>
        </thead>
        <tbody>
            ${tableRows}
        </tbody>
    </table>
</div>

${paginationBlock}`, { total });

        } catch (e) {
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
