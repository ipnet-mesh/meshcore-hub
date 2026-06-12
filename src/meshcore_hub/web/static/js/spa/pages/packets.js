import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort,
    warningBadge,
    pagination, sortableTableHeader, mobileSortSelect,
    renderFilterCard, autoSubmit, submitOnEnter
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

const EVENT_TYPES = [
    // Structured classifications
    'advertisement', 'channel_msg_recv', 'contact_msg_recv',
    'trace_data', 'telemetry_response', 'path_updated', 'status_response',
    // Per-payload-type classifications for otherwise-unhandled packets
    'req', 'response', 'ack', 'encrypted_direct', 'encrypted_channel',
    'grp_data', 'anon_req', 'multipart', 'control', 'raw_custom',
    'advert', 'path', 'trace', 'letsmesh_packet',
];

function lockBadge() {
    return html`<span class="opacity-60" title="${t('packets.redacted_title')}">\u{1F512}</span>`;
}

function channelLabel(packet, channelNames) {
    if (packet.channel_idx == null) {
        return html`<span class="opacity-50">—</span>`;
    }
    const name = channelNames.get(packet.channel_idx);
    const text = name ? `${name} (${packet.channel_idx})` : `${packet.channel_idx}`;
    return html`${text}${packet.redacted ? html` ${lockBadge()}` : nothing}`;
}

function observerCell(packet) {
    const name = packet.observer_tag_name || packet.observer_name;
    if (!packet.observed_by) {
        return html`<span class="opacity-50">—</span>`;
    }
    const label = name || (packet.observed_by.slice(0, 12) + '…');
    return html`<a href="/nodes/${packet.observed_by}" class="link link-hover" @click=${(e) => e.stopPropagation()}>${label}</a>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    const query = params.query || {};
    const search = query.search || '';
    const packet_hash = query.packet_hash || '';
    const event_type = query.event_type || '';
    const channel_idx = query.channel_idx || '';
    const route_type = query.route_type || 'all';
    const observed_by = query.observed_by
        ? (Array.isArray(query.observed_by) ? query.observed_by : [query.observed_by])
        : [];
    const min_snr = query.min_snr || '';
    const max_snr = query.max_snr || '';
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
    <h1 class="text-3xl font-bold">${t('entities.packets')}</h1>
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
            if (packet_hash) apiParams.packet_hash = packet_hash;
            if (event_type) apiParams.event_type = event_type;
            if (channel_idx !== '') apiParams.channel_idx = channel_idx;
            if (route_type && route_type !== 'all') apiParams.route_type = route_type;
            if (observed_by.length > 0) apiParams.observed_by = observed_by;
            if (min_snr !== '') apiParams.min_snr = min_snr;
            if (max_snr !== '') apiParams.max_snr = max_snr;

            const [data, nodesData, channelsData] = await Promise.all([
                apiGet('/api/v1/packets', apiParams, { signal }),
                apiGet('/api/v1/nodes', { limit: 500, observer: true }, { signal }),
                apiGet('/api/v1/channels', { limit: 200 }, { signal }).catch(() => ({ items: [] })),
            ]);

            const packets = data.items || [];
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);

            const sortedNodes = (nodesData.items || []).map(n => {
                const tagName = n.tags?.find(tg => tg.key === 'name')?.value;
                return { ...n, _sortName: (tagName || n.name || '').toLowerCase(), _displayName: tagName || n.name || n.public_key.slice(0, 12) + '...' };
            }).sort((a, b) => a._sortName.localeCompare(b._sortName));

            const channelList = (channelsData.items || []).map(c => ({
                name: c.name,
                idx: parseInt(c.channel_hash, 16),
            })).filter(c => !Number.isNaN(c.idx));
            const channelNames = new Map(channelList.map(c => [c.idx, c.name]));

            const noneFound = html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.packets').toLowerCase() })}</div>`;

            const mobileCards = packets.length === 0
                ? noneFound
                : packets.map(p => html`
        <a href="/packets/${p.id}" class="card bg-base-100 shadow-sm block">
            <div class="card-body p-3">
                <div class="flex items-center justify-between gap-2">
                    <div class="min-w-0">
                        <div class="font-mono text-sm truncate">${p.event_type || '—'}</div>
                        <div class="text-xs opacity-60">${channelLabel(p, channelNames)}</div>
                    </div>
                    <div class="text-right flex-shrink-0">
                        <div class="text-xs opacity-60">${formatDateTimeShort(p.received_at)}</div>
                        <div class="text-xs opacity-60">${observerCell(p)}</div>
                    </div>
                </div>
                <div class="flex items-center gap-2 mt-1 text-xs opacity-60">
                    ${p.snr != null ? html`<span>${Number(p.snr).toFixed(1)} dB</span>` : nothing}
                    ${p.path_len != null ? html`<span>${p.path_len} ${t('common.hops').toLowerCase()}</span>` : nothing}
                </div>
            </div>
        </a>`);

            const tableRows = packets.length === 0
                ? html`<tr><td colspan="7" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.packets').toLowerCase() })}</td></tr>`
                : packets.map(p => html`<tr class="hover cursor-pointer" @click=${() => navigate(`/packets/${p.id}`)}>
                    <td class="text-sm whitespace-nowrap">${formatDateTime(p.received_at)}</td>
                    <td>${p.packet_hash ? html`<code class="font-mono text-xs">${p.packet_hash}</code>` : html`<span class="opacity-50">—</span>`}</td>
                    <td class="text-sm">${observerCell(p)}</td>
                    <td class="font-mono text-xs">${p.event_type || '—'}</td>
                    <td class="text-sm">${channelLabel(p, channelNames)}</td>
                    <td class="text-sm">${p.snr != null ? Number(p.snr).toFixed(1) : '—'}</td>
                    <td class="text-sm">${p.path_len != null ? p.path_len : '—'}</td>
                </tr>`);

            const paginationBlock = pagination(page, totalPages, '/packets', {
                search, packet_hash, event_type, channel_idx, route_type, observed_by,
                min_snr, max_snr, limit, sort, order,
            });

            const filterFields = [
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('common.search')}</span></label>
                <input type="text" name="search" .value=${search} placeholder="${t('common.search_placeholder')}" class="input input-bordered input-sm w-80" @keydown=${submitOnEnter} />
            </div>`,
                () => html`
            <div class="flex flex-col gap-1 max-w-48">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('packets.filter_event_type')}</span></label>
                <select name="event_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${!event_type}>${t('common.all_types')}</option>
                    ${EVENT_TYPES.map(et => html`<option value=${et} ?selected=${event_type === et}>${et}</option>`)}
                </select>
            </div>`,
                () => html`
            <div class="flex flex-col gap-1 max-w-48">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('entities.channel')}</span></label>
                <select name="channel_idx" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${channel_idx === ''}>${t('common.all_channels')}</option>
                    ${channelList.map(c => html`<option value=${c.idx} ?selected=${String(channel_idx) === String(c.idx)}>${c.name} (${c.idx})</option>`)}
                </select>
            </div>`,
            ];
            if (sortedNodes.length > 0) {
                filterFields.push(() => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('common.filter_observer_label')}</span></label>
                <select name="observed_by" multiple size="2" class="select select-bordered select-sm w-full max-w-xs">
                    ${sortedNodes.map(n => html`<option value=${n.public_key} ?selected=${observed_by.includes(n.public_key)}>${n._displayName}</option>`)}
                </select>
            </div>`);
            }
            filterFields.push(() => html`
            <div class="flex flex-col gap-1 max-w-32">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('packets.filter_min_snr')}</span></label>
                <input type="number" step="0.1" name="min_snr" .value=${min_snr} class="input input-bordered input-sm" @keydown=${submitOnEnter} />
            </div>`);
            filterFields.push(() => html`
            <div class="flex flex-col gap-1 max-w-32">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('packets.filter_max_snr')}</span></label>
                <input type="number" step="0.1" name="max_snr" .value=${max_snr} class="input input-bordered input-sm" @keydown=${submitOnEnter} />
            </div>`);

            const hasActiveFilters = search !== '' || event_type !== '' || channel_idx !== '' || observed_by.length > 0 || min_snr !== '' || max_snr !== '';
            const existingDetails = container.querySelector('details.collapse');
            const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;

            const filterCard = renderFilterCard({
                fields: filterFields,
                basePath: '/packets',
                navigate,
                collapsible: true,
                defaultOpen: isFilterOpen,
            });

            const headerParams = { search, packet_hash, event_type, channel_idx, route_type, observed_by, min_snr, max_snr, limit };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/packets', params: headerParams,
            });

            const packetHashChip = packet_hash
                ? html`<div class="flex items-center gap-2 mb-3">
                    <span class="badge badge-neutral inline-flex items-center">
                        <code class="font-mono text-xs leading-none">${packet_hash}</code>
                    </span>
                    <a href="/packets" class="btn btn-xs btn-ghost">${t('common.clear_filters')}</a>
                </div>`
                : nothing;

            renderPage(html`${filterCard}
${packetHashChip}

${mobileSortSelect({
    currentSort: sort, currentOrder: order,
    navigate, basePath: '/packets',
    params: headerParams,
    options: [
        { value: 'time:desc', label: t('packets.sort.newest') },
        { value: 'time:asc', label: t('packets.sort.oldest') },
        { value: 'event_type:asc', label: t('packets.sort.event_az') },
        { value: 'snr:desc', label: t('packets.sort.snr_high') },
        { value: 'path_len:desc', label: t('packets.sort.path_high') },
    ],
})}

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow">
    <table class="table table-zebra">
        <thead>
            <tr>
                ${sortable(t('common.time'), 'time')}
                <th>${t('packets.packet_hash')}</th>
                <th>${t('common.observers')}</th>
                ${sortable(t('packets.col_event_type'), 'event_type')}
                <th>${t('entities.channel')}</th>
                ${sortable(t('common.snr_db'), 'snr')}
                ${sortable(t('common.hops'), 'path_len')}
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
