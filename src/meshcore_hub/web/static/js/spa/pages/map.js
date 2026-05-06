import { apiGet } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, typeEmoji, formatRelativeTime, escapeHtml, errorAlert,
    timezoneIndicator,
} from '../components.js';

const MAX_BOUNDS_RADIUS_KM = 20;

function getDistanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function getNodesWithinRadius(nodes, anchorLat, anchorLon, radiusKm) {
    return nodes.filter(n => getDistanceKm(anchorLat, anchorLon, n.lat, n.lon) <= radiusKm);
}

function getAnchorPoint(nodes, adoptedCenter) {
    if (adoptedCenter) return adoptedCenter;
    if (nodes.length === 0) return { lat: 0, lon: 0 };
    return {
        lat: nodes.reduce((sum, n) => sum + n.lat, 0) / nodes.length,
        lon: nodes.reduce((sum, n) => sum + n.lon, 0) / nodes.length,
    };
}

function normalizeType(type) {
    return type ? type.toLowerCase() : null;
}

function getTypeDisplay(node) {
    const type = normalizeType(node.adv_type);
    if (type === 'chat') return (window.t && window.t('node_types.chat')) || 'Chat';
    if (type === 'repeater') return (window.t && window.t('node_types.repeater')) || 'Repeater';
    if (type === 'room') return (window.t && window.t('node_types.room')) || 'Room';
    return type ? type.charAt(0).toUpperCase() + type.slice(1) : (window.t && window.t('node_types.unknown')) || 'Unknown';
}

// Leaflet DivIcon requires plain HTML strings, so keep escapeHtml here
function createNodeIcon(node, oidcEnabled) {
    const displayName = node.name || '';
    const relativeTime = formatRelativeTime(node.last_seen);
    const timeDisplay = relativeTime ? ' (' + relativeTime + ')' : '';

    const iconHtml = (oidcEnabled && node.is_adopted)
        ? '<div style="width: 12px; height: 12px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>'
        : '<div style="width: 12px; height: 12px; background: #22c55e; border: 2px solid #15803d; border-radius: 50%; box-shadow: 0 0 4px rgba(34,197,94,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';

    return L.divIcon({
        className: 'custom-div-icon',
        html: '<div class="map-marker" style="display: flex; flex-direction: column; align-items: center; gap: 2px;">' +
            iconHtml +
            '<span class="map-label" style="font-size: 10px; font-weight: bold; color: #fff; background: rgba(0,0,0,0.5); padding: 1px 4px; border-radius: 3px; white-space: nowrap; text-align: center;">' +
            escapeHtml(displayName) + timeDisplay + '</span>' +
            '</div>',
        iconSize: [120, 50],
        iconAnchor: [60, 12],
    });
}

// Leaflet popup requires plain HTML strings, so keep escapeHtml here
function createPopupContent(node, oidcEnabled) {
    const typeDisplay = getTypeDisplay(node);
    const nodeTypeEmoji = typeEmoji(node.adv_type);

    let infraIndicatorHtml = '';
    if (oidcEnabled && typeof node.is_adopted !== 'undefined') {
        const dotColor = node.is_adopted ? '#3b82f6' : '#22c55e';
        const borderColor = node.is_adopted ? '#1e40af' : '#15803d';
        const title = node.is_adopted ? ((window.t && window.t('map.infrastructure')) || 'Infrastructure') : ((window.t && window.t('map.public')) || 'Public');
        infraIndicatorHtml = ' <span style="display: inline-block; width: 10px; height: 10px; background: ' + dotColor + '; border: 2px solid ' + borderColor + '; border-radius: 50%; vertical-align: middle;" title="' + title + '"></span>';
    }

    const typeLabel = (window.t && window.t('common.type')) || 'Type:';
    const keyLabel = (window.t && window.t('common.key')) || 'Key:';
    const locationLabel = (window.t && window.t('common.location')) || 'Location:';
    const lastSeenLabel = (window.t && window.t('common.last_seen_label')) || 'Last seen:';
    const unknownLabel = (window.t && window.t('node_types.unknown')) || 'Unknown';
    const viewDetailsLabel = (window.t && window.t('common.view_details')) || 'View Details';

    let rows = '';
    rows += '<div class="opacity-70">' + typeLabel + '</div><div>' + escapeHtml(typeDisplay) + '</div>';

    if (node.role) {
        const roleLabel = (window.t && window.t('map.role')) || 'Role:';
        rows += '<div class="opacity-70">' + roleLabel + '</div><div><span class="badge badge-xs badge-ghost">' + escapeHtml(node.role) + '</span></div>';
    }

    if (node.owner) {
        const ownerLabel = (window.t && window.t('map.owner')) || 'Owner:';
        const ownerDisplay = node.owner.callsign
            ? escapeHtml(node.owner.name) + ' (' + escapeHtml(node.owner.callsign) + ')'
            : escapeHtml(node.owner.name);
        rows += '<div class="opacity-70">' + ownerLabel + '</div><div>' + ownerDisplay + '</div>';
    }

    rows += '<div class="opacity-70">' + keyLabel + '</div><div><code class="text-xs">' + escapeHtml(node.public_key.substring(0, 16)) + '...</code></div>';
    rows += '<div class="opacity-70">' + locationLabel + '</div><div>' + node.lat.toFixed(4) + ', ' + node.lon.toFixed(4) + '</div>';

    if (node.last_seen) {
        rows += '<div class="opacity-70">' + lastSeenLabel + '</div><div>' + node.last_seen.substring(0, 19).replace('T', ' ') + '</div>';
    }

    return '<div class="p-2">' +
        '<h3 class="font-bold text-lg mb-2">' + nodeTypeEmoji + ' ' + escapeHtml(node.name || unknownLabel) + infraIndicatorHtml + '</h3>' +
        '<div class="text-sm grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">' + rows + '</div>' +
        '<a href="/nodes/' + encodeURIComponent(node.public_key) + '" class="btn btn-outline btn-xs mt-3">' + viewDetailsLabel + '</a>' +
        '</div>';
}

export async function render(container, params, router) {
    try {
        const config = getConfig();
        const data = await apiGet('/map/data');
        let allNodes = data.nodes || [];
        const mapCenter = data.center || { lat: 0, lon: 0 };
        const adoptedCenter = data.adopted_center || null;
        const debug = data.debug || {};
        const profiles = data.profiles || [];

        const isMobilePortrait = window.innerWidth < 480;
        const isMobile = window.innerWidth < 768;
        const BOUNDS_PADDING = isMobilePortrait ? [50, 50] : (isMobile ? [75, 75] : [100, 100]);

        let lastMemberFilter = '';

        async function applyFilters() {
            const memberFilter = document.getElementById('member-filter')?.value || '';

            if (memberFilter !== lastMemberFilter) {
                lastMemberFilter = memberFilter;
                const params = {};
                if (memberFilter) params.adopted_by = memberFilter;
                const newData = await apiGet('/map/data', params);
                allNodes = newData.nodes || [];
            }
            const filteredNodes = applyFiltersCore();
            const categoryFilter = container.querySelector('#filter-category').value;

            if (filteredNodes.length > 0) {
                let nodesToFit = filteredNodes;

                if (categoryFilter !== 'infra') {
                    const anchor = getAnchorPoint(filteredNodes, adoptedCenter);
                    const nearbyNodes = getNodesWithinRadius(filteredNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
                    if (nearbyNodes.length > 0) {
                        nodesToFit = nearbyNodes;
                    }
                }

                const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
                map.fitBounds(bounds, { padding: BOUNDS_PADDING });
            } else if (mapCenter.lat !== 0 || mapCenter.lon !== 0) {
                map.setView([mapCenter.lat, mapCenter.lon], 10);
            }
        }

        function updateLabelVisibility() {
            const showLabels = container.querySelector('#show-labels').checked;
            if (showLabels) {
                mapEl.classList.add('show-labels');
            } else {
                mapEl.classList.remove('show-labels');
            }
        }

        function clearFiltersHandler() {
            container.querySelector('#filter-category').value = '';
            container.querySelector('#filter-type').value = '';
            container.querySelector('#show-labels').checked = false;
            const memberEl = container.querySelector('#member-filter');
            if (memberEl) memberEl.value = '';
            updateLabelVisibility();
            applyFilters();
        }

        const existingDetails = container.querySelector('details.collapse');
        const isFilterOpen = existingDetails ? existingDetails.open : false;

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.map')}</h1>
    <div class="flex items-center gap-2">
        ${timezoneIndicator()}
        <span id="node-count" class="badge badge-lg">${t('common.loading')}</span>
        <span id="filtered-count" class="badge badge-lg badge-ghost hidden"></span>
    </div>
</div>

<details class="collapse collapse-arrow bg-base-200 border-2 border-base-content/25 rounded-box mb-6"
         ?open=${isFilterOpen}>
    <summary class="collapse-title text-sm font-medium cursor-pointer">
        ${t('common.filters')}
    </summary>
    <div class="collapse-content pt-4">
        <div class="flex gap-4 flex-wrap items-end">
            <div class="fieldset">
                <label class="fieldset-label">${t('common.show')}</label>
                <select id="filter-category" class="select select-bordered select-sm" @change=${applyFilters}>
                    <option value="">${t('common.all_entity', { entity: t('entities.nodes') })}</option>
                    ${config.oidc_enabled ? html`<option value="infra">${t('map.infrastructure_only')}</option>` : nothing}
                </select>
            </div>
            <div class="fieldset">
                <label class="fieldset-label">${t('common.node_type')}</label>
                <select id="filter-type" class="select select-bordered select-sm" @change=${applyFilters}>
                    <option value="">${t('common.all_types')}</option>
                    <option value="chat">${t('node_types.chat')}</option>
                    <option value="repeater">${t('node_types.repeater')}</option>
                    <option value="room">${t('node_types.room')}</option>
                </select>
            </div>
            ${config.oidc_enabled && profiles.length > 0 ? html`
            <div class="fieldset">
                <label class="fieldset-label">${t('common.filter_member_label')}</label>
                <select id="member-filter" class="select select-bordered select-sm" @change=${applyFilters}>
                    <option value="">${t('common.all_members')}</option>
                    ${profiles.sort((a, b) => {
                        const na = a.name || a.callsign || '';
                        const nb = b.name || b.callsign || '';
                        return na.localeCompare(nb);
                    }).map(p => html`
                    <option value=${p.id}>${p.callsign ? p.name + ' (' + p.callsign + ')' : (p.name || p.callsign || p.id)}</option>`)}
                </select>
            </div>
            ` : nothing}
            <div class="fieldset">
                <label class="fieldset-label cursor-pointer gap-2">
                    <span>${t('map.show_labels')}</span>
                    <input type="checkbox" id="show-labels" class="checkbox checkbox-sm" @change=${updateLabelVisibility}>
                </label>
            </div>
            <button id="clear-filters" class="btn btn-ghost btn-sm" @click=${clearFiltersHandler}>${t('common.clear_filters')}</button>
        </div>
    </div>
</details>

<div class="card bg-base-100 shadow-xl">
    <div class="card-body p-2">
        <div id="spa-map" style="height: calc(100vh - 300px); min-height: 400px;"></div>
    </div>
</div>

${config.oidc_enabled ? html`
<div class="mt-4 flex flex-wrap gap-4 items-center text-sm">
    <span class="opacity-70">${t('map.legend')}</span>
    <div class="flex items-center gap-1">
        <div style="width: 10px; height: 10px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%;"></div>
        <span>${t('map.infrastructure')}</span>
    </div>
    <div class="flex items-center gap-1">
        <div style="width: 10px; height: 10px; background: #22c55e; border: 2px solid #15803d; border-radius: 50%;"></div>
        <span>${t('map.public')}</span>
    </div>
</div>
` : nothing}

<div class="mt-2 text-sm opacity-70">
    <p>${t('map.gps_description')}</p>
</div>`, container);

        const mapEl = container.querySelector('#spa-map');
        const map = L.map(mapEl).setView([0, 0], 2);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map);

        let markers = [];

        function clearMarkers() {
            markers.forEach(m => map.removeLayer(m));
            markers = [];
        }

        function applyFiltersCore() {
            const categoryFilter = container.querySelector('#filter-category').value;
            const typeFilter = container.querySelector('#filter-type').value;

            const filteredNodes = allNodes.filter(node => {
                if (categoryFilter === 'infra' && !node.is_adopted) return false;
                const nodeType = normalizeType(node.adv_type);
                if (typeFilter && nodeType !== typeFilter) return false;
                return true;
            });

            clearMarkers();

            filteredNodes.forEach(node => {
                const marker = L.marker([node.lat, node.lon], { icon: createNodeIcon(node, config.oidc_enabled) }).addTo(map);
                marker.bindPopup(createPopupContent(node, config.oidc_enabled));
                markers.push(marker);
            });

            const countEl = container.querySelector('#node-count');
            const filteredEl = container.querySelector('#filtered-count');

            if (filteredNodes.length === allNodes.length) {
                countEl.textContent = t('map.nodes_on_map', { count: allNodes.length });
                filteredEl.classList.add('hidden');
            } else {
                countEl.textContent = t('common.total', { count: allNodes.length });
                filteredEl.textContent = t('common.shown', { count: filteredNodes.length });
                filteredEl.classList.remove('hidden');
            }

            return filteredNodes;
        }

        if (debug.error) {
            container.querySelector('#node-count').textContent = 'Error: ' + debug.error;
            return () => map.remove();
        }

        if (debug.total_nodes === 0) {
            container.querySelector('#node-count').textContent = t('common.no_entity_in_database', { entity: t('entities.nodes').toLowerCase() });
            return () => map.remove();
        }

        if (debug.nodes_with_coords === 0) {
            container.querySelector('#node-count').textContent = t('map.nodes_none_have_coordinates', { count: debug.total_nodes });
            return () => map.remove();
        }

        if (config.oidc_enabled) {
            const adoptedNodes = allNodes.filter(n => n.is_adopted);
            if (adoptedNodes.length > 0) {
                const bounds = L.latLngBounds(adoptedNodes.map(n => [n.lat, n.lon]));
                map.fitBounds(bounds, { padding: BOUNDS_PADDING });
            } else if (allNodes.length > 0) {
                const anchor = getAnchorPoint(allNodes, adoptedCenter);
                const nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
                const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
                const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
                map.fitBounds(bounds, { padding: BOUNDS_PADDING });
            }
        } else if (allNodes.length > 0) {
            const anchor = getAnchorPoint(allNodes, null);
            const nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
            const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
            const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
            map.fitBounds(bounds, { padding: BOUNDS_PADDING });
        }

        applyFiltersCore();

        return () => map.remove();

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
