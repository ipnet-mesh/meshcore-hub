import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    typeEmoji, formatRelativeTime, escapeHtml, errorAlert,
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

function getAnchorPoint(nodes, infraCenter) {
    if (infraCenter) return infraCenter;
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
    if (type === 'chat') return 'Chat';
    if (type === 'repeater') return 'Repeater';
    if (type === 'room') return 'Room';
    return type ? type.charAt(0).toUpperCase() + type.slice(1) : 'Unknown';
}

// Leaflet DivIcon requires plain HTML strings, so keep escapeHtml here
function createNodeIcon(node) {
    const displayName = node.name || '';
    const relativeTime = formatRelativeTime(node.last_seen);
    const timeDisplay = relativeTime ? ' (' + relativeTime + ')' : '';

    const iconHtml = node.is_infra
        ? '<div style="width: 12px; height: 12px; background: #ef4444; border: 2px solid #b91c1c; border-radius: 50%; box-shadow: 0 0 4px rgba(239,68,68,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>'
        : '<div style="width: 12px; height: 12px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';

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
function createPopupContent(node) {
    let ownerHtml = '';
    if (node.owner) {
        const ownerDisplay = node.owner.callsign
            ? escapeHtml(node.owner.name) + ' (' + escapeHtml(node.owner.callsign) + ')'
            : escapeHtml(node.owner.name);
        ownerHtml = '<p><span class="opacity-70">Owner:</span> ' + ownerDisplay + '</p>';
    }

    let roleHtml = '';
    if (node.role) {
        roleHtml = '<p><span class="opacity-70">Role:</span> <span class="badge badge-xs badge-ghost">' + escapeHtml(node.role) + '</span></p>';
    }

    const typeDisplay = getTypeDisplay(node);
    const nodeTypeEmoji = typeEmoji(node.adv_type);

    let infraIndicatorHtml = '';
    if (typeof node.is_infra !== 'undefined') {
        const dotColor = node.is_infra ? '#ef4444' : '#3b82f6';
        const borderColor = node.is_infra ? '#b91c1c' : '#1e40af';
        const title = node.is_infra ? 'Infrastructure' : 'Public';
        infraIndicatorHtml = ' <span style="display: inline-block; width: 10px; height: 10px; background: ' + dotColor + '; border: 2px solid ' + borderColor + '; border-radius: 50%; vertical-align: middle;" title="' + title + '"></span>';
    }

    const lastSeenHtml = node.last_seen
        ? '<p><span class="opacity-70">Last seen:</span> ' + node.last_seen.substring(0, 19).replace('T', ' ') + '</p>'
        : '';

    return '<div class="p-2">' +
        '<h3 class="font-bold text-lg mb-2">' + nodeTypeEmoji + ' ' + escapeHtml(node.name || 'Unknown') + infraIndicatorHtml + '</h3>' +
        '<div class="space-y-1 text-sm">' +
        '<p><span class="opacity-70">Type:</span> ' + escapeHtml(typeDisplay) + '</p>' +
        roleHtml +
        ownerHtml +
        '<p><span class="opacity-70">Key:</span> <code class="text-xs">' + escapeHtml(node.public_key.substring(0, 16)) + '...</code></p>' +
        '<p><span class="opacity-70">Location:</span> ' + node.lat.toFixed(4) + ', ' + node.lon.toFixed(4) + '</p>' +
        lastSeenHtml +
        '</div>' +
        '<a href="/nodes/' + encodeURIComponent(node.public_key) + '" class="btn btn-outline btn-xs mt-3">View Details</a>' +
        '</div>';
}

export async function render(container, params, router) {
    try {
        const data = await apiGet('/map/data');
        const allNodes = data.nodes || [];
        const allMembers = data.members || [];
        const mapCenter = data.center || { lat: 0, lon: 0 };
        const infraCenter = data.infra_center || null;
        const debug = data.debug || {};

        const isMobilePortrait = window.innerWidth < 480;
        const isMobile = window.innerWidth < 768;
        const BOUNDS_PADDING = isMobilePortrait ? [50, 50] : (isMobile ? [75, 75] : [100, 100]);

        const sortedMembers = allMembers.slice().sort((a, b) => a.name.localeCompare(b.name));

        function applyFilters() {
            const filteredNodes = applyFiltersCore();
            const categoryFilter = container.querySelector('#filter-category').value;

            if (filteredNodes.length > 0) {
                let nodesToFit = filteredNodes;

                if (categoryFilter !== 'infra') {
                    const anchor = getAnchorPoint(filteredNodes, infraCenter);
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
            container.querySelector('#filter-member').value = '';
            container.querySelector('#show-labels').checked = false;
            updateLabelVisibility();
            applyFilters();
        }

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">Map</h1>
    <div class="flex items-center gap-2">
        ${timezoneIndicator()}
        <span id="node-count" class="badge badge-lg">Loading...</span>
        <span id="filtered-count" class="badge badge-lg badge-ghost hidden"></span>
    </div>
</div>

<div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
    <div class="card-body py-4">
        <div class="flex gap-4 flex-wrap items-end">
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">Show</span>
                </label>
                <select id="filter-category" class="select select-bordered select-sm" @change=${applyFilters}>
                    <option value="">All Nodes</option>
                    <option value="infra">Infrastructure Only</option>
                </select>
            </div>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">Node Type</span>
                </label>
                <select id="filter-type" class="select select-bordered select-sm" @change=${applyFilters}>
                    <option value="">All Types</option>
                    <option value="chat">Chat</option>
                    <option value="repeater">Repeater</option>
                    <option value="room">Room</option>
                </select>
            </div>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">Member</span>
                </label>
                <select id="filter-member" class="select select-bordered select-sm" @change=${applyFilters}>
                    <option value="">All Members</option>
                    ${sortedMembers
                        .filter(m => m.member_id)
                        .map(m => {
                            const label = m.callsign
                                ? m.name + ' (' + m.callsign + ')'
                                : m.name;
                            return html`<option value=${m.member_id}>${label}</option>`;
                        })}
                </select>
            </div>
            <div class="form-control">
                <label class="label cursor-pointer gap-2 py-1">
                    <span class="label-text">Show Labels</span>
                    <input type="checkbox" id="show-labels" class="checkbox checkbox-sm" @change=${updateLabelVisibility}>
                </label>
            </div>
            <button id="clear-filters" class="btn btn-ghost btn-sm" @click=${clearFiltersHandler}>Clear Filters</button>
        </div>
    </div>
</div>

<div class="card bg-base-100 shadow-xl">
    <div class="card-body p-2">
        <div id="spa-map" style="height: calc(100vh - 300px); min-height: 400px;"></div>
    </div>
</div>

<div class="mt-4 flex flex-wrap gap-4 items-center text-sm">
    <span class="opacity-70">Legend:</span>
    <div class="flex items-center gap-1">
        <div style="width: 10px; height: 10px; background: #ef4444; border: 2px solid #b91c1c; border-radius: 50%;"></div>
        <span>Infrastructure</span>
    </div>
    <div class="flex items-center gap-1">
        <div style="width: 10px; height: 10px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%;"></div>
        <span>Public</span>
    </div>
</div>

<div class="mt-2 text-sm opacity-70">
    <p>Nodes are placed on the map based on GPS coordinates from node reports or manual tags.</p>
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
            const memberFilter = container.querySelector('#filter-member').value;

            const filteredNodes = allNodes.filter(node => {
                if (categoryFilter === 'infra' && !node.is_infra) return false;
                const nodeType = normalizeType(node.adv_type);
                if (typeFilter && nodeType !== typeFilter) return false;
                if (memberFilter && node.member_id !== memberFilter) return false;
                return true;
            });

            clearMarkers();

            filteredNodes.forEach(node => {
                const marker = L.marker([node.lat, node.lon], { icon: createNodeIcon(node) }).addTo(map);
                marker.bindPopup(createPopupContent(node));
                markers.push(marker);
            });

            const countEl = container.querySelector('#node-count');
            const filteredEl = container.querySelector('#filtered-count');

            if (filteredNodes.length === allNodes.length) {
                countEl.textContent = allNodes.length + ' nodes on map';
                filteredEl.classList.add('hidden');
            } else {
                countEl.textContent = allNodes.length + ' total';
                filteredEl.textContent = filteredNodes.length + ' shown';
                filteredEl.classList.remove('hidden');
            }

            return filteredNodes;
        }

        if (debug.error) {
            container.querySelector('#node-count').textContent = 'Error: ' + debug.error;
            return () => map.remove();
        }

        if (debug.total_nodes === 0) {
            container.querySelector('#node-count').textContent = 'No nodes in database';
            return () => map.remove();
        }

        if (debug.nodes_with_coords === 0) {
            container.querySelector('#node-count').textContent = debug.total_nodes + ' nodes (none have coordinates)';
            return () => map.remove();
        }

        const infraNodes = allNodes.filter(n => n.is_infra);
        if (infraNodes.length > 0) {
            const bounds = L.latLngBounds(infraNodes.map(n => [n.lat, n.lon]));
            map.fitBounds(bounds, { padding: BOUNDS_PADDING });
        } else if (allNodes.length > 0) {
            const anchor = getAnchorPoint(allNodes, infraCenter);
            const nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
            const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
            const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
            map.fitBounds(bounds, { padding: BOUNDS_PADDING });
        }

        applyFiltersCore();

        return () => map.remove();

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load map'), container);
    }
}
