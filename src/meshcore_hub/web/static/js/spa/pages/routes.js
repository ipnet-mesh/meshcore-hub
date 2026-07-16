import { apiGet, apiPost, apiPut, apiDelete, isAbortError } from '../api.js';
import { html, litRender, nothing, t, errorAlert, getConfig, hasRole } from '../components.js';
import { iconPath, iconPlus, iconEdit, iconTrash, iconPackets, iconClock, iconRuler, iconNodes, iconSatelliteDish, iconRouteFrom, iconRouteTo } from '../icons.js';

const VISIBILITY_ORDER = ['community', 'member', 'operator', 'admin'];

let _pathSearchTimer = null;
let _pathSearchId = 0;
let _obsSearchTimer = null;
let _obsSearchId = 0;

function qualityBadgeClass(quality, enabled) {
    if (!enabled) return 'badge-neutral';
    const map = {
        clear: 'badge-success',
        marginal: 'badge-warning',
        failing: 'badge-error',
        no_coverage: 'badge-info',
        unknown: 'badge-info',
    };
    return map[quality] || 'badge-ghost';
}

function qualityLabel(quality, enabled) {
    if (!enabled) return t('routes.disabled');
    const map = {
        clear: t('routes.quality_clear'),
        marginal: t('routes.quality_marginal'),
        failing: t('routes.quality_failing'),
        no_coverage: t('routes.quality_no_coverage'),
        unknown: t('routes.quality_unknown'),
    };
    return map[quality] || quality || t('routes.quality_unknown');
}

function qualityDot(quality, enabled) {
    if (!enabled) return '\u25CC';
    const dots = { clear: '\u25CF', marginal: '\u25CF', failing: '\u25CF', no_coverage: '\u25D0', unknown: '\u25D0' };
    return dots[quality] || '\u25D0';
}

function diagnosisText(route) {
    const result = route.route_result;
    if (!result || !route.enabled) return '';
    if (result.state === 'healthy') return t('routes.diagnosis_healthy');
    if (result.state === 'unhealthy') return t('routes.diagnosis_unhealthy');
    if (result.state === 'no_coverage') return t('routes.diagnosis_no_coverage');
    return '';
}

function renderSummaryStrip(routes) {
    const counts = { clear: 0, marginal: 0, failing: 0, no_coverage: 0, disabled: 0 };
    for (const r of routes) {
        if (!r.enabled) { counts.disabled++; continue; }
        const q = r.route_result?.quality || 'unknown';
        if (q === 'clear') counts.clear++;
        else if (q === 'marginal') counts.marginal++;
        else if (q === 'failing') counts.failing++;
        else counts.no_coverage++;
    }
    return html`<div class="flex flex-wrap gap-4 mb-6 text-sm">
        <span class="flex items-center gap-1"><span class="text-success">\u25CF</span> ${counts.clear} ${t('routes.quality_clear')}</span>
        <span class="flex items-center gap-1"><span class="text-warning">\u25CF</span> ${counts.marginal} ${t('routes.quality_marginal')}</span>
        <span class="flex items-center gap-1"><span class="text-error">\u25CF</span> ${counts.failing} ${t('routes.quality_failing')}</span>
        <span class="flex items-center gap-1"><span class="text-info">\u25D0</span> ${counts.no_coverage} ${t('routes.quality_no_coverage')}</span>
        <span class="flex items-center gap-1 opacity-50">\u25CC ${counts.disabled} ${t('routes.disabled')}</span>
    </div>`;
}

function renderPathChips(route) {
    const nodes = route.route_nodes || [];
    const arrow = route.reversible !== false ? '\u2194' : '\u2192';
    const prefixLen = 2 * (route.match_width || 1);
    return html`<div class="flex flex-wrap items-center gap-1 text-sm">
        ${nodes.map((rn, i) => html`
            ${i > 0 ? html`<span class="opacity-50">${arrow}</span>` : nothing}
            <span class="badge badge-ghost badge-sm">${rn.name ? html`${rn.name} (${rn.public_key?.slice(0, prefixLen)})` : (rn.public_key?.slice(0, prefixLen) || rn.node_id.slice(0, 8))}</span>
        `)}
    </div>`;
}

function renderStatsRow(route) {
    const result = route.route_result;
    const matched = result?.matched_count ?? '?';
    const threshold = result?.threshold ?? '?';
    const degraded = result?.effective_clear ?? '?';
    const nodeCount = (route.route_nodes || []).length;
    const obsCount = (route.route_observers || []).length;

    return html`<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs opacity-60 mt-1">
        <span class="inline-flex items-center gap-1">
            ${iconPackets('h-3.5 w-3.5')}
            <span>${matched}/${threshold}\u2192${degraded}</span>
        </span>
        <span class="inline-flex items-center gap-1">
            ${iconClock('h-3.5 w-3.5')}
            <span>${route.window_hours}h</span>
        </span>
        <span class="inline-flex items-center gap-1">
            ${iconRuler('h-3.5 w-3.5')}
            <span>${route.match_width}B</span>
        </span>
        <span class="inline-flex items-center gap-1">
            ${iconNodes('h-3.5 w-3.5')}
            <span>${nodeCount}</span>
        </span>
        ${route.max_hop_span ? html`<span class="inline-flex items-center gap-1">
            ${iconPath('h-3.5 w-3.5')}
            <span>${route.max_hop_span}</span>
        </span>` : nothing}
        <span class="inline-flex items-center gap-1">
            ${iconSatelliteDish('h-3.5 w-3.5')}
            <span>${obsCount || '\u221E'}</span>
        </span>
    </div>`;
}

function renderRouteCard(route, { isAdmin, onDelete, onEdit, detail, navigate, packetsEnabled, history }) {
    const q = route.route_result?.quality || 'unknown';
    const badgeCls = qualityBadgeClass(q, route.enabled);
    const label = qualityLabel(q, route.enabled);
    const dot = qualityDot(q, route.enabled);
    const tip = diagnosisText(route);
    const arrow = route.reversible !== false ? '\u2194' : '\u2192';
    const badge = tip
        ? html`<span class="badge ${badgeCls} badge-sm tooltip tooltip-left" data-tip=${tip}>${dot} ${label}</span>`
        : html`<span class="badge ${badgeCls} badge-sm">${dot} ${label}</span>`;

    const adminButtons = isAdmin
        ? html`<div class="flex gap-2 mt-auto pt-2">
            <button class="btn btn-xs btn-outline" @click=${() => onEdit(route)}>
                ${iconEdit('h-3 w-3')} ${t('common.edit')}
            </button>
            <button class="btn btn-xs btn-outline btn-error" @click=${() => onDelete(route)}>
                ${iconTrash('h-3 w-3')} ${t('common.delete')}
            </button>
        </div>`
        : nothing;

    const expandContent = detail
        ? renderDetailContent(route, detail, { navigate, packetsEnabled, history })
        : html`<div class="mt-4 pt-4 border-t border-base-300 flex justify-center">
            <span class="loading loading-spinner loading-sm opacity-50"></span>
          </div>`;

    return html`<div class="card bg-base-100 shadow-xl h-full">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div class="flex-1 min-w-0">
                    <h2 class="card-title">
                        <div class="grid grid-cols-[auto_1fr] gap-x-2 items-center min-w-0">
                            <span class="flex items-center text-base-content/60">${iconRouteFrom('h-5 w-5')}</span>
                            <span class="truncate" title=${route.from_label || ''}>${route.from_label}</span>
                            <span class="flex items-center text-base-content/60">${iconRouteTo('h-5 w-5')}</span>
                            <span class="truncate" title=${route.to_label || ''}>${route.to_label}</span>
                        </div>
                    </h2>
                    ${route.description ? html`<p class="text-sm opacity-70 mt-1">${route.description}</p>` : nothing}
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <span class="badge badge-ghost badge-sm opacity-60 font-mono text-xl leading-none px-2 inline-flex items-center" title=${route.reversible !== false ? t('routes.reversible_label') : ''}>${arrow}</span>
                    ${badge}
                </div>
            </div>
            <div class="mt-2">${renderPathChips(route)}</div>
            ${renderStatsRow(route)}
            ${expandContent}
            ${adminButtons}
        </div>
    </div>`;
}

function renderDetailContent(route, detail, { navigate, packetsEnabled, history }) {
    const matches = detail.recent_matches || [];
    const packetDetailUrl = (packetHash) =>
        (packetsEnabled && packetHash) ? `/packets/hash/${packetHash}` : null;

    const historySection = history
        ? html`<div class="mb-3">
            <div style="height: 40px;">
                <canvas id="routeStripChart-${route.id}"></canvas>
            </div>
            ${history.data && history.data.length > 0 ? html`<div class="flex text-xs opacity-50 mt-0.5">
                ${history.data.map(d => html`<span class="flex-1 text-center">${new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' })}</span>`)}
            </div>` : nothing}
        </div>`
        : nothing;

    return html`<div class="mt-2 space-y-3 text-sm">
        ${historySection}
        ${matches.length > 0 ? html`<div>
            <strong class="opacity-70">${t('routes.recent_packets')}</strong>
            <div class="mt-2 space-y-2">
                ${matches.map(m => {
                    const prefixLen = 2 * (route.match_width || 1);
                    const pathLookup = new Map(
                        (route.route_nodes || []).map(rn =>
                            [rn.expected_hash?.toLowerCase(), rn])
                    );
                    const detailUrl = packetDetailUrl(m.packet_hash);
                    return html`<div class="flex flex-wrap items-center gap-0.5 text-xs pb-1 border-b border-base-300 last:border-0 ${detailUrl ? 'hover:bg-base-200 cursor-pointer -mx-1 px-1 rounded transition-colors' : ''}"
                        @click=${detailUrl ? (e) => { e.stopPropagation(); navigate(detailUrl); } : undefined}>
                        ${(m.hops || []).map((h, i) => {
                            const rn = pathLookup.get((h.node_hash || '').toLowerCase().slice(0, prefixLen));
                            return html`
                                ${i > 0 ? html`<span class="opacity-30 mx-0.5">\u2192</span>` : nothing}
                                ${rn
                                    ? html`<span class="badge badge-primary badge-sm">${(h.node_hash || '').toLowerCase()}</span>`
                                    : html`<span class="badge badge-ghost badge-sm opacity-50">${(h.node_hash || '').toLowerCase()}</span>`}
                            `;
                        })}
                        ${m.received_at ? html`<span class="ml-auto opacity-40 whitespace-nowrap">${new Date(m.received_at).toLocaleString()}</span>` : nothing}
                    </div>`;
                })}
            </div>
        </div>` : nothing}
    </div>`;
}

function renderNodeSearchResult(node, onSelect) {
    const name = node.name || `${node.public_key.slice(0, 12)}\u2026`;
    return html`
        <li>
            <button type="button" class="w-full text-left flex items-center gap-2" @click=${() => onSelect(node)}>
                <span class="flex-1 min-w-0">
                    <span class="block text-sm font-medium truncate">${name}</span>
                    <span class="block text-xs opacity-50 font-mono truncate">${node.public_key}</span>
                </span>
                ${node.adv_type ? html`<span class="badge badge-ghost badge-xs">${node.adv_type}</span>` : nothing}
            </button>
        </li>`;
}

function renderRouteModal({ modalState, onSave, onCancel }) {
    const route = modalState.route;
    const isEdit = modalState.isEdit;
    const title = isEdit ? t('routes.edit_route') : t('routes.add_route');

    const pathNodes = modalState.pathNodes;
    const observerNodes = modalState.observerNodes;
    const pathResults = modalState.pathResults;
    const obsResults = modalState.obsResults;

    const selectedPathKeys = new Set(pathNodes.map(n => n.public_key));
    const selectedObsKeys = new Set(observerNodes.map(n => n.public_key));
    const availPathResults = pathResults.filter(n => !selectedPathKeys.has(n.public_key));
    const availObsResults = obsResults.filter(n => !selectedObsKeys.has(n.public_key));

    return html`<dialog open class="modal modal-open">
        <div class="modal-box modal-box-lg">
            <h3 class="font-bold text-lg mb-4">${title}</h3>
            <form @submit=${(e) => { e.preventDefault(); onSave(); }}>
                <div class="grid grid-cols-1 gap-3 mb-4">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                            <label class="text-sm opacity-70">${t('routes.from_label')}</label>
                            <input type="text" id="route-modal-from" class="input input-sm w-full"
                                .value=${route.from_label || ''}
                                placeholder="${t('routes.from_label')}"
                                required maxlength="255" />
                        </div>
                        <div>
                            <label class="text-sm opacity-70">${t('routes.to_label')}</label>
                            <input type="text" id="route-modal-to" class="input input-sm w-full"
                                .value=${route.to_label || ''}
                                placeholder="${t('routes.to_label')}"
                                required maxlength="255" />
                        </div>
                    </div>
                    <div>
                        <label class="text-sm opacity-70">${t('routes.description_label')}</label>
                        <input type="text" id="route-modal-description" class="input input-sm w-full"
                            .value=${route.description || ''}
                            placeholder="${t('routes.description_label')}" />
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="text-sm opacity-70">${t('routes.visibility_label')}</label>
                            <select id="route-modal-visibility" class="select select-sm w-full">
                                <option value="community" .selected=${route.visibility === 'community' || !route.visibility}>community</option>
                                <option value="member" .selected=${route.visibility === 'member'}>member</option>
                                <option value="operator" .selected=${route.visibility === 'operator'}>operator</option>
                                <option value="admin" .selected=${route.visibility === 'admin'}>admin</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-sm opacity-70">${t('routes.width_label')}</label>
                            <div class="flex gap-1 mt-1">
                                ${[1, 2, 3].map(w => html`
                                    <button type="button"
                                        class="btn btn-xs ${route.match_width === w || (!route.match_width && w === 1) ? 'btn-primary' : 'btn-outline'}"
                                        @click=${() => {
                                            document.querySelectorAll('[data-width-btn]').forEach(b => b.classList.remove('btn-primary'));
                                            document.querySelectorAll('[data-width-btn]').forEach(b => b.classList.add('btn-outline'));
                                            const btn = document.querySelector(`[data-width-btn="${w}"]`);
                                            if (btn) { btn.classList.add('btn-primary'); btn.classList.remove('btn-outline'); }
                                            document.getElementById('route-modal-width').value = w;
                                        }}
                                        data-width-btn="${w}">${w}B</button>
                                `)}
                            </div>
                            <input type="hidden" id="route-modal-width" value=${route.match_width || 1} />
                        </div>
                    </div>
                    <div>
                        <label class="text-sm opacity-70">${t('routes.path_label')}</label>
                        <div class="relative">
                            <input type="text" id="route-modal-path-search" class="input input-sm w-full"
                                placeholder="${t('routes.search_nodes_placeholder')}"
                                autocomplete="off"
                                @input=${(e) => modalState.handlePathSearch(e.target.value)}
                                @keydown=${(e) => modalState.handlePathKeydown(e, availPathResults)} />
                            ${availPathResults.length > 0 ? html`
                                <ul class="menu bg-base-200 rounded-box absolute z-50 left-0 right-0 top-full mt-1 p-2 shadow-lg max-h-60 overflow-auto">
                                    ${availPathResults.map(n => renderNodeSearchResult(n, modalState.handlePathSelect))}
                                </ul>
                            ` : nothing}
                        </div>
                        <p class="text-xs opacity-50 mt-1">${t('routes.path_help')}</p>
                        <div class="flex flex-wrap items-center gap-1 mt-2 min-h-[2.5rem] p-2 bg-base-200 rounded-box">
                            ${pathNodes.length === 0
                                ? html`<span class="text-sm opacity-40">${t('routes.path_empty')}</span>`
                                : pathNodes.map((n, i) => html`
                                    ${i > 0 ? html`<span class="text-primary text-sm px-0.5">\u2192</span>` : nothing}
                                    <span class="inline-flex items-center gap-0.5 bg-primary text-primary-content rounded-full px-2 py-1 text-sm">
                                        ${i > 0
                                            ? html`<button type="button" class="btn btn-ghost btn-xs btn-circle text-primary-content opacity-60 hover:opacity-100"
                                                @click=${() => modalState.handlePathMove(i, -1)}>\u25C4</button>`
                                            : nothing}
                                        <span>${n.name || n.public_key.slice(0, 8)}</span>
                                        <button type="button" class="btn btn-ghost btn-xs btn-circle text-primary-content opacity-60 hover:opacity-100"
                                            @click=${() => modalState.handlePathRemove(i)}>\u2715</button>
                                        ${i < pathNodes.length - 1
                                            ? html`<button type="button" class="btn btn-ghost btn-xs btn-circle text-primary-content opacity-60 hover:opacity-100"
                                                @click=${() => modalState.handlePathMove(i, 1)}>\u25BA</button>`
                                            : nothing}
                                    </span>
                                `)}
                        </div>
                    </div>
                    <div>
                        <label class="text-sm opacity-70">${t('routes.observers_label')}</label>
                        <div class="relative">
                            <input type="text" id="route-modal-obs-search" class="input input-sm w-full"
                                placeholder="${t('routes.search_nodes_placeholder')}"
                                autocomplete="off"
                                @input=${(e) => modalState.handleObsSearch(e.target.value)}
                                @keydown=${(e) => modalState.handleObsKeydown(e, availObsResults)} />
                            ${availObsResults.length > 0 ? html`
                                <ul class="menu bg-base-200 rounded-box absolute z-50 left-0 right-0 top-full mt-1 p-2 shadow-lg max-h-60 overflow-auto">
                                    ${availObsResults.map(n => renderNodeSearchResult(n, modalState.handleObsSelect))}
                                </ul>
                            ` : nothing}
                        </div>
                        <p class="text-xs opacity-50 mt-1">${t('routes.observers_help')}</p>
                        <div class="flex flex-wrap items-center gap-1 mt-2 min-h-[2.5rem] p-2 bg-base-200 rounded-box">
                            ${observerNodes.length === 0
                                ? html`<span class="text-sm opacity-40">${t('routes.observers_empty')}</span>`
                                : observerNodes.map((n, i) => html`
                                    <span class="inline-flex items-center gap-0.5 bg-base-300 rounded-full px-2 py-1 text-sm">
                                        <span>${n.name || n.public_key.slice(0, 8)}</span>
                                        <button type="button" class="btn btn-ghost btn-xs btn-circle opacity-60 hover:opacity-100"
                                            @click=${() => modalState.handleObsRemove(i)}>\u2715</button>
                                    </span>
                                `)}
                        </div>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div>
                            <label class="text-sm opacity-70">${t('routes.window_label')}</label>
                            <input type="number" id="route-modal-window" class="input input-sm w-full"
                                .value=${route.window_hours || 24} min="1" max="720" />
                        </div>
                        <div>
                            <label class="text-sm opacity-70">${t('routes.threshold_label')}</label>
                            <input type="number" id="route-modal-threshold" class="input input-sm w-full"
                                .value=${route.packet_count_threshold || 3} min="1" max="10000" />
                        </div>
                        <div>
                            <label class="text-sm opacity-70">${t('routes.clear_label')}</label>
                            <input type="number" id="route-modal-clear" class="input input-sm w-full"
                                .value=${route.clear_threshold || ''}
                                placeholder="${2 * (route.packet_count_threshold || 3)}" min="1" />
                        </div>
                        <div>
                            <label class="text-sm opacity-70">${t('routes.span_label')}</label>
                            <input type="number" id="route-modal-span" class="input input-sm w-full"
                                .value=${route.max_hop_span || ''}
                                placeholder="\u221E" min="1" />
                        </div>
                    </div>
                    <div class="flex gap-6">
                        <label class="label cursor-pointer justify-start gap-3">
                            <input type="checkbox" id="route-modal-enabled" class="checkbox checkbox-sm"
                                .checked=${route.enabled !== false} />
                            <span class="text-sm">${t('routes.enabled_label')}</span>
                        </label>
                        <label class="label cursor-pointer justify-start gap-3">
                            <input type="checkbox" id="route-modal-reversible" class="checkbox checkbox-sm"
                                .checked=${route.reversible !== false} />
                            <span class="text-sm">${t('routes.reversible_label')}</span>
                        </label>
                    </div>
                </div>
                <div class="modal-action">
                    <button type="button" class="btn btn-ghost" @click=${onCancel}>${t('common.cancel')}</button>
                    <button type="submit" class="btn btn-primary">${t('common.save')}</button>
                </div>
            </form>
        </div>
        <form method="dialog" class="modal-backdrop"><button @click=${onCancel}></button></form>
    </dialog>`;
}

function renderDeleteModal({ route, onConfirm, onCancel }) {
    const arrow = route.reversible !== false ? '\u2194' : '\u2192';
    const label = `${route.from_label} ${arrow} ${route.to_label}`;
    return html`<dialog open class="modal modal-open">
        <div class="modal-box">
            <h3 class="font-bold text-lg mb-4">${t('routes.delete_route')}</h3>
            <p>${t('routes.delete_confirm', { label })}</p>
            <div class="modal-action">
                <button class="btn btn-ghost" @click=${onCancel}>${t('common.cancel')}</button>
                <button class="btn btn-error" @click=${onConfirm}>${t('common.delete')}</button>
            </div>
        </div>
        <form method="dialog" class="modal-backdrop"><button @click=${onCancel}></button></form>
    </dialog>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    try {
        const config = getConfig();
        const isAdmin = hasRole('admin');
        const navigate = (url) => router.navigate(url);
        const packetsEnabled = config.features?.packets !== false;

        const data = await apiGet('/api/v1/routes', {}, { signal });
        const routes = data.items || [];

        let modalState = null;
        const detailCache = new Map();
        const historyCache = new Map();
        const chartRegistry = [];

        function destroyCharts() {
            chartRegistry.forEach(c => { try { c.destroy(); } catch (_) {} });
            chartRegistry.length = 0;
        }

        async function refresh() {
            const newData = await apiGet('/api/v1/routes');
            routes.splice(0, routes.length, ...(newData.items || []));
            renderPage(routes);
            loadAllDetails(routes);
        }

        async function loadAllDetails(routesList) {
            const promises = [];
            for (const r of routesList) {
                if (!detailCache.has(r.id)) {
                    promises.push(
                        apiGet(`/api/v1/routes/${r.id}`, {}, { signal })
                            .then(d => detailCache.set(r.id, d))
                            .catch(() => {})
                    );
                }
                if (!historyCache.has(r.id)) {
                    promises.push(
                        apiGet(`/api/v1/routes/${r.id}/history`, { days: 6 }, { signal })
                            .then(h => historyCache.set(r.id, h))
                            .catch(() => {})
                    );
                }
            }
            if (promises.length > 0) {
                await Promise.allSettled(promises);
                renderPage(routes);
            }
        }

        function renderPage(routesList) {
            const adminHeader = isAdmin
                ? html`<div class="flex justify-end mb-4">
                    <button class="btn btn-primary btn-sm" @click=${handleAdd}>
                        ${iconPlus('h-4 w-4')} ${t('routes.add_route')}
                    </button>
                </div>`
                : nothing;

            const emptyMessage = routesList.length === 0
                ? html`<div class="text-center py-8 opacity-70">
                    ${t('common.no_entity_found', { entity: t('entities.routes').toLowerCase() })}
                </div>`
                : nothing;

            const groups = new Map();
            for (const vis of VISIBILITY_ORDER) groups.set(vis, []);
            for (const r of routesList) {
                const vis = r.visibility || 'community';
                if (!groups.has(vis)) groups.set(vis, []);
                groups.get(vis).push(r);
            }

            const cardOpts = {
                isAdmin,
                onDelete: handleDeleteClick,
                onEdit: handleEditClick,
                detail: (r) => detailCache.get(r.id),
                navigate,
                packetsEnabled,
                history: (r) => historyCache.get(r.id),
            };

            const groupedSections = [];
            for (const vis of VISIBILITY_ORDER) {
                const group = groups.get(vis);
                if (!group || group.length === 0) continue;
                group.sort((a, b) =>
                    (a.from_label || '').localeCompare(b.from_label || '')
                );
                groupedSections.push(html`
                    <h2 class="text-lg font-semibold mt-6 mb-3 opacity-70">${t(`routes.visibility_${vis}`)}</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${group.map(r => renderRouteCard(r, {
                            ...cardOpts,
                            detail: cardOpts.detail(r),
                            history: cardOpts.history(r),
                        }))}
                    </div>
                `);
            }

            let modalHtml = nothing;
            if (modalState?.type === 'add' || modalState?.type === 'edit') {
                modalHtml = renderRouteModal({
                    modalState,
                    onSave: handleSave,
                    onCancel: () => { modalState = null; renderPage(routesList); },
                });
            } else if (modalState?.type === 'delete') {
                modalHtml = renderDeleteModal({
                    route: modalState.route,
                    onConfirm: handleDeleteConfirm,
                    onCancel: () => { modalState = null; renderPage(routesList); },
                });
            }

            destroyCharts();

            litRender(html`
                <div class="mb-6">
                    <h1 class="text-3xl font-bold flex items-center gap-2">
                        ${iconPath('h-8 w-8')}
                        ${t('routes.title')}
                    </h1>
                </div>
                ${renderSummaryStrip(routesList)}
                ${adminHeader}
                ${emptyMessage}
                ${groupedSections}
                ${modalHtml}
            `, container);

            for (const r of routesList) {
                if (historyCache.has(r.id)) {
                    const chart = window.createRouteDetailStrip(`routeStripChart-${r.id}`, historyCache.get(r.id));
                    if (chart) chartRegistry.push(chart);
                }
            }
        }

        function _newModalState(type, route) {
            return {
                type,
                route,
                isEdit: type === 'edit',
                pathNodes: (route.route_nodes || []).map(rn => ({
                    public_key: rn.public_key,
                    name: rn.name,
                })),
                observerNodes: (route.route_observers || []).map(ro => ({
                    public_key: ro.public_key,
                    name: ro.name,
                })),
                pathResults: [],
                obsResults: [],
                handlePathSearch,
                handlePathSelect,
                handlePathRemove,
                handlePathMove,
                handlePathKeydown,
                handleObsSearch,
                handleObsSelect,
                handleObsRemove,
                handleObsKeydown,
            };
        }

        function handleAdd() {
            modalState = _newModalState('add', { visibility: 'community', enabled: true, match_width: 1 });
            renderPage(routes);
        }

        function handleEditClick(route) {
            modalState = _newModalState('edit', route);
            renderPage(routes);
        }

        function handleDeleteClick(route) {
            modalState = { type: 'delete', route };
            renderPage(routes);
        }

        function handlePathSearch(query) {
            clearTimeout(_pathSearchTimer);
            const q = query.trim();
            if (q.length < 2) {
                modalState.pathResults = [];
                renderPage(routes);
                return;
            }
            _pathSearchTimer = setTimeout(async () => {
                const myId = ++_pathSearchId;
                try {
                    const data = await apiGet('/api/v1/nodes', { search: q, limit: 10 });
                    if (myId !== _pathSearchId) return;
                    modalState.pathResults = data.items || [];
                    renderPage(routes);
                } catch (_) { /* ignore */ }
            }, 300);
        }

        function handlePathSelect(node) {
            if (modalState.pathNodes.some(n => n.public_key === node.public_key)) return;
            modalState.pathNodes.push({ public_key: node.public_key, name: node.name });
            modalState.pathResults = [];
            renderPage(routes);
            const el = document.getElementById('route-modal-path-search');
            if (el) el.value = '';
        }

        function handlePathRemove(index) {
            modalState.pathNodes.splice(index, 1);
            renderPage(routes);
        }

        function handlePathMove(index, dir) {
            const newIndex = index + dir;
            if (newIndex < 0 || newIndex >= modalState.pathNodes.length) return;
            const nodes = modalState.pathNodes;
            [nodes[index], nodes[newIndex]] = [nodes[newIndex], nodes[index]];
            renderPage(routes);
        }

        async function handlePathKeydown(e, availResults) {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            if (availResults.length === 1) {
                handlePathSelect(availResults[0]);
                return;
            }
            if (availResults.length > 1) {
                handlePathSelect(availResults[0]);
                return;
            }
            const query = e.target.value.trim();
            if (query.length < 2) return;
            clearTimeout(_pathSearchTimer);
            const myId = ++_pathSearchId;
            try {
                const data = await apiGet('/api/v1/nodes', { search: query, limit: 10 });
                if (myId !== _pathSearchId) return;
                modalState.pathResults = data.items || [];
                renderPage(routes);
                const filtered = modalState.pathResults.filter(
                    n => !modalState.pathNodes.some(pn => pn.public_key === n.public_key)
                );
                if (filtered.length >= 1) {
                    handlePathSelect(filtered[0]);
                }
            } catch (_) { /* ignore */ }
        }

        function handleObsSearch(query) {
            clearTimeout(_obsSearchTimer);
            const q = query.trim();
            if (q.length < 2) {
                modalState.obsResults = [];
                renderPage(routes);
                return;
            }
            _obsSearchTimer = setTimeout(async () => {
                const myId = ++_obsSearchId;
                try {
                    const data = await apiGet('/api/v1/nodes', { search: q, limit: 10, observer: true });
                    if (myId !== _obsSearchId) return;
                    modalState.obsResults = data.items || [];
                    renderPage(routes);
                } catch (_) { /* ignore */ }
            }, 300);
        }

        function handleObsSelect(node) {
            if (modalState.observerNodes.some(n => n.public_key === node.public_key)) return;
            modalState.observerNodes.push({ public_key: node.public_key, name: node.name });
            modalState.obsResults = [];
            renderPage(routes);
            const el = document.getElementById('route-modal-obs-search');
            if (el) el.value = '';
        }

        function handleObsRemove(index) {
            modalState.observerNodes.splice(index, 1);
            renderPage(routes);
        }

        async function handleObsKeydown(e, availResults) {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            if (availResults.length >= 1) {
                handleObsSelect(availResults[0]);
                return;
            }
            const query = e.target.value.trim();
            if (query.length < 2) return;
            clearTimeout(_obsSearchTimer);
        const myId = ++_obsSearchId;
        try {
            const data = await apiGet('/api/v1/nodes', { search: query, limit: 10, observer: true });
            if (myId !== _obsSearchId) return;
            modalState.obsResults = data.items || [];
                renderPage(routes);
                const filtered = modalState.obsResults.filter(
                    n => !modalState.observerNodes.some(on => on.public_key === n.public_key)
                );
                if (filtered.length >= 1) {
                    handleObsSelect(filtered[0]);
                }
            } catch (_) { /* ignore */ }
        }

        async function handleSave() {
            const fromEl = document.getElementById('route-modal-from');
            const toEl = document.getElementById('route-modal-to');
            const descEl = document.getElementById('route-modal-description');
            const visEl = document.getElementById('route-modal-visibility');
            const widthEl = document.getElementById('route-modal-width');
            const windowEl = document.getElementById('route-modal-window');
            const thresholdEl = document.getElementById('route-modal-threshold');
            const clearEl = document.getElementById('route-modal-clear');
            const spanEl = document.getElementById('route-modal-span');
            const enabledEl = document.getElementById('route-modal-enabled');
            const reversibleEl = document.getElementById('route-modal-reversible');

            const isEdit = modalState.isEdit;
            const nodePublicKeys = modalState.pathNodes.map(n => n.public_key);
            const observerPublicKeys = modalState.observerNodes.map(n => n.public_key);

            if (nodePublicKeys.length < 2) {
                alert(t('routes.min_nodes_error'));
                return;
            }

            const body = {
                from_label: fromEl.value.trim(),
                to_label: toEl.value.trim(),
                description: descEl.value.trim() || null,
                visibility: visEl.value,
                match_width: parseInt(widthEl.value, 10) || 1,
                window_hours: parseInt(windowEl.value, 10) || 24,
                packet_count_threshold: parseInt(thresholdEl.value, 10) || 3,
                max_hop_span: spanEl.value ? parseInt(spanEl.value, 10) : null,
                enabled: enabledEl.checked,
                reversible: reversibleEl.checked,
                node_public_keys: nodePublicKeys,
                observer_public_keys: observerPublicKeys.length > 0 ? observerPublicKeys : null,
            };

            const clearVal = clearEl.value.trim();
            if (clearVal) {
                body.clear_threshold = parseInt(clearVal, 10);
            }

            try {
                if (isEdit) {
                    await apiPut(`/api/v1/routes/${modalState.route.id}`, body);
                    detailCache.delete(modalState.route.id);
                    historyCache.delete(modalState.route.id);
                } else {
                    await apiPost('/api/v1/routes', body);
                }
                modalState = null;
                await refresh();
            } catch (e) {
                alert(e.message || 'Failed to save route');
            }
        }

        async function handleDeleteConfirm() {
            try {
                await apiDelete(`/api/v1/routes/${modalState.route.id}`);
                modalState = null;
                await refresh();
            } catch (e) {
                alert(e.message || 'Failed to delete route');
            }
        }

        renderPage(routes);
        loadAllDetails(routes);

        return () => {
            destroyCharts();
        };

    } catch (e) {
        if (isAbortError(e)) return;
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
