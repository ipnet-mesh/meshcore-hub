import { apiGet, apiPost, apiPut, apiDelete, isAbortError } from '../api.js';
import { html, litRender, nothing, t, errorAlert, getConfig, hasRole } from '../components.js';
import { iconPath, iconPlus, iconEdit, iconTrash, iconChevronRight } from '../icons.js';

const VISIBILITY_ORDER = ['community', 'member', 'operator', 'admin'];
const QUALITY_PRIORITY = { failing: 0, no_coverage: 1, marginal: 2, clear: 3, disabled: 4 };

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
    return html`<div class="flex flex-wrap items-center gap-1 text-sm">
        ${nodes.map((rn, i) => html`
            ${i > 0 ? html`<span class="opacity-50">${arrow}</span>` : nothing}
            <span class="badge badge-ghost badge-sm">${rn.name || rn.public_key?.slice(0, 8) || rn.node_id.slice(0, 8)}</span>
        `)}
    </div>`;
}

function renderNumbersLine(route) {
    const result = route.route_result;
    if (!result) return html`<div class="text-xs opacity-50 mt-1">${t('routes.not_evaluated')}</div>`;
    const matched = result.matched_count ?? '?';
    const threshold = result.threshold ?? '?';
    const degraded = result.effective_degraded ?? '?';
    const evalTime = result.evaluated_at
        ? new Date(result.evaluated_at).toLocaleTimeString()
        : '?';
    return html`<div class="text-xs opacity-60 mt-1">
        ${matched} / ${threshold} \u2192 ${degraded} \u00B7 ${route.window_hours}h \u00B7 ${evalTime}
    </div>`;
}

function renderRouteCard(route, { isAdmin, onDelete, onEdit, onExpand, isExpanded, detail }) {
    const q = route.route_result?.quality || 'unknown';
    const badgeCls = qualityBadgeClass(q, route.enabled);
    const label = qualityLabel(q, route.enabled);
    const dot = qualityDot(q, route.enabled);
    const visBadge = html`<span class="badge badge-primary badge-sm">${route.visibility}</span>`;

    const adminButtons = isAdmin
        ? html`<div class="flex gap-2 mt-2">
            <button class="btn btn-xs btn-outline" @click=${(e) => { e.stopPropagation(); onEdit(route); }}>
                ${iconEdit('h-3 w-3')} ${t('common.edit')}
            </button>
            <button class="btn btn-xs btn-outline btn-error" @click=${(e) => { e.stopPropagation(); onDelete(route); }}>
                ${iconTrash('h-3 w-3')} ${t('common.delete')}
            </button>
        </div>`
        : nothing;

    const expandContent = isExpanded && detail ? renderDetailContent(route, detail) : nothing;

    return html`<div class="card bg-base-100 shadow-xl">
        <div class="card-body cursor-pointer" role="button" tabindex="0"
            @click=${() => onExpand(route)}
            @keydown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onExpand(route); } }}>
            <div class="flex items-start justify-between gap-2">
                <div class="flex-1 min-w-0">
                    <h2 class="card-title flex items-center gap-2">
                        ${route.name}
                        ${visBadge}
                    </h2>
                    ${route.description ? html`<p class="text-sm opacity-70 mt-1">${route.description}</p>` : nothing}
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <span class="badge ${badgeCls} badge-sm">${dot} ${label}</span>
                    ${iconChevronRight(`h-4 w-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`)}
                </div>
            </div>
            <div class="mt-2">${renderPathChips(route)}</div>
            ${renderNumbersLine(route)}
            ${adminButtons}
            ${expandContent}
        </div>
    </div>`;
}

function renderDetailContent(route, detail) {
    const result = detail.route_result || route.route_result;
    const observers = detail.contributing_observers || [];
    const matches = detail.recent_matches || [];

    return html`<div class="mt-4 pt-4 border-t border-base-300 space-y-3 text-sm">
        ${result ? html`<div class="opacity-70">
            <strong>${t('routes.diagnosis')}:</strong>
            ${result.state === 'healthy' ? t('routes.diagnosis_healthy') : nothing}
            ${result.state === 'unhealthy' ? t('routes.diagnosis_unhealthy') : nothing}
            ${result.state === 'no_coverage' ? t('routes.diagnosis_no_coverage') : nothing}
        </div>` : nothing}
        ${observers.length > 0 ? html`<div>
            <strong class="opacity-70">${t('routes.contributing_observers')}:</strong>
            ${observers.map(o => html`<span class="badge badge-ghost badge-sm ml-1">${o.name || o.node_id.slice(0, 8)} (${o.match_count})</span>`)}
        </div>` : html`<div class="opacity-50">${t('routes.no_observers')}</div>`}
        ${matches.length > 0 ? html`<div>
            <strong class="opacity-70">${t('routes.recent_matches')}:</strong>
            <div class="mt-1 space-y-1">
                ${matches.map(m => {
                    const pathLookup = new Map(
                        (route.route_nodes || []).map(rn =>
                            [rn.expected_hash?.toLowerCase(), rn])
                    );
                    return html`<div class="flex flex-wrap items-center gap-0.5 text-xs">
                        ${(m.hops || []).slice(0, 10).map((h, i) => {
                            const rn = pathLookup.get((h.node_hash || '').toLowerCase());
                            return html`
                                ${i > 0 ? html`<span class="opacity-30 mx-0.5">\u2192</span>` : nothing}
                                ${rn
                                    ? html`<span class="badge badge-primary badge-sm">${rn.name || h.node_hash}</span>`
                                    : html`<span class="badge badge-ghost badge-sm opacity-50">${h.node_hash}</span>`}
                            `;
                        })}
                    </div>`;
                })}
            </div>
        </div>` : nothing}
        <div class="opacity-50 text-xs">
            ${t('routes.width')}: ${route.match_width} \u00B7
            ${t('routes.window')}: ${route.window_hours}h \u00B7
            ${t('routes.threshold')}: ${route.packet_count_threshold} \u00B7
            ${route.max_hop_span ? html`${t('routes.span')}: ${route.max_hop_span}` : nothing}
        </div>
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
                    <div>
                        <label class="text-sm opacity-70">${t('routes.name_label')}</label>
                        <input type="text" id="route-modal-name" class="input input-sm w-full"
                            .value=${route.name || ''}
                            placeholder="${t('routes.name_label')}"
                            required maxlength="255" />
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
                            <label class="text-sm opacity-70">${t('routes.degraded_label')}</label>
                            <input type="number" id="route-modal-degraded" class="input input-sm w-full"
                                .value=${route.degraded_threshold || ''}
                                placeholder="2x" min="1" />
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
    return html`<dialog open class="modal modal-open">
        <div class="modal-box">
            <h3 class="font-bold text-lg mb-4">${t('routes.delete_route')}</h3>
            <p>${t('routes.delete_confirm', { name: route.name })}</p>
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

        const data = await apiGet('/api/v1/routes', {}, { signal });
        const routes = data.items || [];

        let modalState = null;
        let expandedId = null;
        const detailCache = new Map();

        async function refresh() {
            const newData = await apiGet('/api/v1/routes');
            renderPage(newData.items || []);
        }

        async function handleExpand(route) {
            if (expandedId === route.id) {
                expandedId = null;
            } else {
                expandedId = route.id;
                if (!detailCache.has(route.id)) {
                    try {
                        const detail = await apiGet(`/api/v1/routes/${route.id}`);
                        detailCache.set(route.id, detail);
                    } catch (e) {
                        // ignore — card still shows basic info
                    }
                }
            }
            renderPage(routes);
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
                onExpand: handleExpand,
                isExpanded: (r) => expandedId === r.id,
                detail: (r) => detailCache.get(r.id),
            };

            const groupedSections = [];
            for (const vis of VISIBILITY_ORDER) {
                const group = groups.get(vis);
                if (!group || group.length === 0) continue;
                group.sort((a, b) => {
                    const qa = a.route_result?.quality || (a.enabled ? 'unknown' : 'disabled');
                    const qb = b.route_result?.quality || (b.enabled ? 'unknown' : 'disabled');
                    return (QUALITY_PRIORITY[qa] ?? 9) - (QUALITY_PRIORITY[qb] ?? 9);
                });
                groupedSections.push(html`
                    <h2 class="text-lg font-semibold mt-6 mb-3 opacity-70">${t(`routes.visibility_${vis}`)}</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${group.map(r => renderRouteCard(r, {
                            ...cardOpts,
                            isExpanded: cardOpts.isExpanded(r),
                            detail: cardOpts.detail(r),
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
                    const data = await apiGet('/api/v1/nodes', { search: q, limit: 10 });
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
                const data = await apiGet('/api/v1/nodes', { search: query, limit: 10 });
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
            const nameEl = document.getElementById('route-modal-name');
            const descEl = document.getElementById('route-modal-description');
            const visEl = document.getElementById('route-modal-visibility');
            const widthEl = document.getElementById('route-modal-width');
            const windowEl = document.getElementById('route-modal-window');
            const thresholdEl = document.getElementById('route-modal-threshold');
            const degradedEl = document.getElementById('route-modal-degraded');
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
                name: nameEl.value.trim(),
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

            const degradedVal = degradedEl.value.trim();
            if (degradedVal) {
                body.degraded_threshold = parseInt(degradedVal, 10);
            }

            try {
                if (isEdit) {
                    await apiPut(`/api/v1/routes/${modalState.route.id}`, body);
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

    } catch (e) {
        if (isAbortError(e)) return;
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
