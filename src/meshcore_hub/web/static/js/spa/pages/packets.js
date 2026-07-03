import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort, formatNumber,
    warningBadge,
    pagination, sortableTableHeader, mobileSortSelect,
    renderFilterForm, renderFilterToggle, autoSubmit, submitOnEnter
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';
import { iconSatelliteDish, iconPath, iconRuler } from '../icons.js';

const EVENT_TYPES = [
    'advertisement', 'channel_msg_recv', 'contact_msg_recv',
    'trace_data', 'telemetry_response', 'path_updated', 'status_response',
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

function receptionBadge(packet) {
    const rc = packet.reception_count ?? 1;
    const oc = packet.observer_count ?? 1;
    const pb = packet.path_hash_bytes;
    const knownWidth = pb != null && pb > 0;
    const widthLabel = knownWidth
        ? t('packets.path_width_bytes', { count: pb })
        : t('packets.path_width_unknown');
    return html`<span class="inline-flex items-center gap-1">
        ${iconSatelliteDish('h-4 w-4 opacity-70')}
        <span class="badge badge-sm badge-primary" title=${t('common.observers')}>${formatNumber(oc)}</span>
        <span class="opacity-40" aria-hidden="true">×</span>
        ${iconPath('h-4 w-4 opacity-70')}
        <span class="badge badge-sm badge-primary" title=${t('packets.reception_plural')}>${formatNumber(rc)}</span>
        <span class="opacity-40" aria-hidden="true">@</span>
        ${iconRuler('h-4 w-4 opacity-70')}
        <span class="badge badge-sm badge-primary ${knownWidth ? '' : 'opacity-60'}" title=${t('packets.path_width_title')}>${widthLabel}</span>
    </span>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    const query = params.query || {};
    const search = query.search || '';
    const event_type = query.event_type || '';
    const channel_idx = query.channel_idx || '';
    const path_hash_bytes = query.path_hash_bytes || '';
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
    let currentFilterFields = [];
    const hasActiveFilters = search !== '' || event_type !== '' || channel_idx !== '' || path_hash_bytes !== '';

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
    <h1 class="text-3xl font-bold">${t('entities.packets')}</h1>
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
    ? html`<div class="mb-4">${renderFilterForm({ fields: currentFilterFields, basePath: '/packets', navigate })}</div>`
    : nothing}
${displayContent}`, container);
    }

    renderPage(nothing);

    async function fetchAndRenderData() {
        try {
            const apiParams = { limit, offset, search, sort, order };
            if (event_type) apiParams.event_type = event_type;
            if (channel_idx !== '') apiParams.channel_idx = channel_idx;
            if (path_hash_bytes !== '') apiParams.path_hash_bytes = path_hash_bytes;

            const [data, channelsData] = await Promise.all([
                apiGet('/api/v1/packet-groups', apiParams, { signal }),
                apiGet('/api/v1/channels', { limit: 200 }, { signal }).catch(() => ({ items: [] })),
            ]);

            const packets = data.items || [];
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);

            const channelList = (channelsData.items || []).map(c => ({
                name: c.name,
                idx: parseInt(c.channel_hash, 16),
            })).filter(c => !Number.isNaN(c.idx));
            const channelNames = new Map(channelList.map(c => [c.idx, c.name]));

            const noneFound = html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.packets').toLowerCase() })}</div>`;

            function packetUrl(p) {
                if (p.packet_hash) return `/packets/hash/${p.packet_hash}`;
                if (p.receptions && p.receptions.length > 0) return `/packets/${p.receptions[0].packet_id}`;
                return '/packets';
            }

            const mobileCards = packets.length === 0
                ? noneFound
                : packets.map(p => html`
        <a href="${packetUrl(p)}" class="card bg-base-100 shadow-sm block">
            <div class="card-body p-3">
                <div class="flex items-center justify-between gap-2">
                    <div class="min-w-0">
                        <div class="font-mono text-sm truncate">${p.event_type || '—'}</div>
                        <div class="text-xs opacity-60">${channelLabel(p, channelNames)}</div>
                    </div>
                    <div class="text-right flex-shrink-0">
                        <div class="text-xs opacity-60">${formatDateTimeShort(p.first_seen)}</div>
                        <div class="text-xs opacity-60">${receptionBadge(p)}</div>
                    </div>
                </div>
            </div>
        </a>`);

            const tableRows = packets.length === 0
                ? html`<tr><td colspan="5" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.packets').toLowerCase() })}</td></tr>`
                : packets.map(p => html`<tr class="hover cursor-pointer" @click=${() => navigate(packetUrl(p))}>
                    <td class="text-sm whitespace-nowrap">${formatDateTime(p.first_seen)}</td>
                    <td>${p.packet_hash ? html`<code class="font-mono text-xs">${p.packet_hash}</code>` : html`<span class="opacity-50">—</span>`}</td>
                    <td class="text-sm">${receptionBadge(p)}</td>
                    <td class="font-mono text-xs">${p.event_type || '—'}</td>
                    <td class="text-sm">${channelLabel(p, channelNames)}</td>
                </tr>`);

            const paginationBlock = pagination(page, totalPages, '/packets', {
                search, event_type, channel_idx, path_hash_bytes, limit, sort, order,
            });

            const filterFields = [
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('common.search')}</span></label>
                <input type="text" name="search" .value=${search} placeholder="${t('common.search_placeholder')}" class="input input-sm w-80" @keydown=${submitOnEnter} />
            </div>`,
                () => html`
            <div class="flex flex-col gap-1 max-w-48">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('packets.filter_event_type')}</span></label>
                <select name="event_type" class="select select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${!event_type}>${t('common.all_types')}</option>
                    ${EVENT_TYPES.map(et => html`<option value=${et} ?selected=${event_type === et}>${et}</option>`)}
                </select>
            </div>`,
                () => html`
            <div class="flex flex-col gap-1 max-w-48">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('entities.channel')}</span></label>
                <select name="channel_idx" class="select select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${channel_idx === ''}>${t('common.all_channels')}</option>
                    ${channelList.map(c => html`<option value=${c.idx} ?selected=${String(channel_idx) === String(c.idx)}>${c.name} (${c.idx})</option>`)}
                </select>
            </div>`,
                () => html`
            <div class="flex flex-col gap-1 max-w-48">
                <label class="flex items-center py-1"><span class="opacity-80 text-sm">${t('packets.filter_path_width')}</span></label>
                <select name="path_hash_bytes" class="select select-sm" @change=${autoSubmit}>
                    <option value="" ?selected=${path_hash_bytes === ''}>${t('common.all')}</option>
                    ${[1, 2, 3].map(w => html`<option value=${w} ?selected=${path_hash_bytes === String(w)}>${t('packets.path_width_bytes', { count: w })}</option>`)}
                </select>
            </div>`,
            ];

            const headerParams = { search, event_type, channel_idx, path_hash_bytes, limit };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/packets', params: headerParams,
            });

            currentFilterFields = filterFields;

            renderPage(html`

${mobileSortSelect({
    currentSort: sort, currentOrder: order,
    navigate, basePath: '/packets',
    params: headerParams,
    options: [
        { value: 'time:desc', label: t('packets.sort.newest') },
        { value: 'time:asc', label: t('packets.sort.oldest') },
        { value: 'event_type:asc', label: t('packets.sort.event_az') },
        { value: 'reception_count:desc', label: t('packets.sort.receptions_high') },
    ],
})}

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow-sm">
    <table class="table table-zebra">
        <thead>
            <tr>
                ${sortable(t('common.time'), 'time')}
                <th>${t('packets.packet_hash')}</th>
                <th title="${t('packets.receptions_title')}">${t('packets.col_receptions')}</th>
                ${sortable(t('packets.col_event_type'), 'event_type')}
                <th>${t('entities.channel')}</th>
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
