import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort,
    warningBadge,
    pagination, sortableTableHeader, mobileSortSelect,
    renderFilterCard, autoSubmit, submitOnEnter, copyToClipboard, renderNodeDisplay,
    observerIcons, getDisabledObservers, toggleObserver, observerFilterBadges, routeTypeBadge
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

export async function render(container, params, router) {
    const { signal } = params || {};
    const query = params.query || {};
    const search = query.search || '';
    const adopted_by = query.adopted_by || '';
    const route_type = query.route_type || 'flood,transport_flood';
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 20;
    const offset = (page - 1) * limit;
    const sort = query.sort || 'time';
    const order = query.order || 'desc';

    // Observer filter is sourced from localStorage (shared toggle badges), not the URL.
    let disabledObservers = getDisabledObservers();

    const config = getConfig();
    const features = config.features || {};
    const packetsEnabled = features.packets !== false;
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);
    // For links nested inside a row/card whose own @click navigates elsewhere:
    // suppress the row handler and drive SPA navigation explicitly (the router
    // listens on document, so stopPropagation alone would force a full reload).
    const stopAndNavigate = (url) => (e) => {
        e.preventDefault();
        e.stopPropagation();
        navigate(url);
    };
    // Packet-detail target for a row/card, or null when not navigable.
    const packetDetailUrl = (packetHash) =>
        (packetsEnabled && packetHash) ? `/packets/hash/${packetHash}` : null;

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
<div class="flex items-center justify-between mb-6">
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
            // Phase 1: fetch the observer node list (and operator profiles) first.
            // The advertisements API filters observers by inclusion only, so we need
            // the full observer list to translate the stored "disabled" set into an
            // explicit include-list before fetching the data.
            const metaFetches = [
                apiGet('/api/v1/nodes', { limit: 500, observer: true }, { signal }),
            ];
            if (config.oidc_enabled) {
                metaFetches.push(apiGet('/api/v1/user/profiles', { limit: 500 }, { signal }));
            }
            const metaResults = await Promise.all(metaFetches);
            const nodesData = metaResults[0];
            const operatorRole = config.role_names?.operator || 'operator';
            const profiles = config.oidc_enabled
                ? (metaResults[1]?.items || []).filter(p => p.roles && p.roles.includes(operatorRole))
                : [];
            const allNodes = nodesData.items || [];

            const sortedNodes = allNodes.map(n => {
                const tagName = n.tags?.find(t => t.key === 'name')?.value;
                return { ...n, _sortName: (tagName || n.name || '').toLowerCase(), _displayName: tagName || n.name || n.public_key.slice(0, 12) + '...' };
            }).sort((a, b) => a._sortName.localeCompare(b._sortName));

            const enabledObserverKeys = sortedNodes
                .filter(n => !disabledObservers.has(n.public_key))
                .map(n => n.public_key);
            // Only constrain when some current observer is actually hidden (a stale
            // disabled key that no longer matches a node should not filter anything).
            const observerFilterActive = enabledObserverKeys.length < sortedNodes.length;

            const onObserverToggle = (pubkey) => {
                disabledObservers = toggleObserver(pubkey, sortedNodes.length);
                if (page > 1) {
                    // Re-scoping the data invalidates the current page; reset to page 1.
                    const sp = new URLSearchParams(window.location.search);
                    sp.delete('page');
                    const qs = sp.toString();
                    navigate(qs ? `/advertisements?${qs}` : '/advertisements');
                } else {
                    fetchAndRenderData();
                }
            };

            // Phase 2: fetch the advertisements with the resolved observer filter.
            const apiParams = { limit, offset, search, sort, order, route_type };
            if (observerFilterActive) apiParams.observed_by = enabledObserverKeys;
            if (adopted_by) apiParams.adopted_by = adopted_by;
            const data = await apiGet('/api/v1/advertisements', apiParams, { signal });

            const advertisements = data.items || [];
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);

            const observerBadges = (extraClass) => observerFilterBadges({
                nodes: sortedNodes, disabled: disabledObservers, onToggle: onObserverToggle, extraClass,
            });

            const mobileCards = advertisements.length === 0
                ? html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.advertisements').toLowerCase() })}</div>`
                : advertisements.map(ad => {
                    const adName = ad.node_tag_name || ad.node_name || ad.name;
                    const adDescription = ad.node_tag_description;
                    let receiversBlock = nothing;
                    if (ad.observers && ad.observers.length >= 1) {
                        receiversBlock = observerIcons(ad.observers);
                    } else if (ad.observed_by) {
                        receiversBlock = html`<span class="opacity-50 text-xs">\u{1F4E1}</span>`;
                    }
                    const detailUrl = packetDetailUrl(ad.packet_hash);
                    return html`<div class="card bg-base-100 shadow-sm block ${detailUrl ? 'cursor-pointer' : ''}"
                @click=${detailUrl ? () => navigate(detailUrl) : undefined}>
            <div class="card-body p-3">
                <div class="flex items-center justify-between gap-2">
                    <a href="/nodes/${ad.public_key}" class="min-w-0" @click=${stopAndNavigate(`/nodes/${ad.public_key}`)}>
                        ${renderNodeDisplay({
                            name: adName,
                            description: adDescription,
                            publicKey: ad.public_key,
                            advType: ad.adv_type,
                            size: 'sm'
                        })}
                    </a>
                    <div class="text-right flex-shrink-0">
                        <div class="text-xs opacity-60">${formatDateTimeShort(ad.received_at)}</div>
                        <div class="flex items-center justify-end gap-1">
                            ${routeTypeBadge(ad.route_type)}
                            ${receiversBlock}
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
                });

            const tableRows = advertisements.length === 0
                ? html`<tr><td colspan="5" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.advertisements').toLowerCase() })}</td></tr>`
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
                    const detailUrl = packetDetailUrl(ad.packet_hash);
                    return html`<tr class="${detailUrl ? 'hover cursor-pointer' : ''}"
                    @click=${detailUrl ? () => navigate(detailUrl) : undefined}>
                    <td>
                        <a href="/nodes/${ad.public_key}" class="link link-hover" @click=${stopAndNavigate(`/nodes/${ad.public_key}`)}>
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
                    <td>${routeTypeBadge(ad.route_type)}</td>
                    <td class="text-sm whitespace-nowrap">${formatDateTime(ad.received_at)}</td>
                    <td>${receiversBlock}</td>
                </tr>`;
                });

            const paginationBlock = pagination(page, totalPages, '/advertisements', {
                search, adopted_by, route_type, limit, sort, order,
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
            <div class="flex flex-col gap-1 max-w-48">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('advertisements.filter_route_type_label')}</span>
                </label>
                <select name="route_type" class="select select-sm" @change=${autoSubmit}>
                    <option value="flood,transport_flood" ?selected=${route_type === 'flood,transport_flood'}>${t('advertisements.route_type_flood')}</option>
                    <option value="all" ?selected=${route_type === 'all'}>${t('advertisements.route_type_all')}</option>
                    <option value="direct" ?selected=${route_type === 'direct'}>${t('advertisements.route_type_direct')}</option>
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
            const hasActiveFilters = search !== '' || (config.oidc_enabled && adopted_by !== '') || route_type !== 'flood,transport_flood';
            const existingDetails = container.querySelector('details.collapse');
            const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;

            const filterCard = renderFilterCard({
                fields: filterFields,
                basePath: '/advertisements',
                navigate,
                collapsible: true,
                defaultOpen: isFilterOpen,
            });

            const headerParams = { search, adopted_by, route_type, limit };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/advertisements', params: headerParams,
            });

            renderPage(html`${filterCard}

${observerBadges('hidden lg:flex mb-4')}

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

${observerBadges('flex lg:hidden mb-4')}

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow-sm">
    <table class="table table-zebra">
        <thead>
            <tr>
                ${sortable(t('entities.node'), 'node_name')}
                ${sortable(t('common.public_key'), 'public_key')}
                <th>${t('advertisements.col_route_type')}</th>
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
