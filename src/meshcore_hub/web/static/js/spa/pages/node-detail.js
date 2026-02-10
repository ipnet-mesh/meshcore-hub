import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, typeEmoji, formatDateTime,
    truncateKey, errorAlert,
} from '../components.js';
import { iconError } from '../icons.js';

export async function render(container, params, router) {
    const cleanupFns = [];
    let publicKey = params.publicKey;

    try {
        if (publicKey.length !== 64) {
            const resolved = await apiGet('/api/v1/nodes/prefix/' + encodeURIComponent(publicKey));
            router.navigate('/nodes/' + resolved.public_key, true);
            return;
        }

        const [node, adsData, telemetryData] = await Promise.all([
            apiGet('/api/v1/nodes/' + publicKey),
            apiGet('/api/v1/advertisements', { public_key: publicKey, limit: 10 }),
            apiGet('/api/v1/telemetry', { node_public_key: publicKey, limit: 10 }),
        ]);

        if (!node) {
            litRender(renderNotFound(publicKey), container);
            return;
        }

        const config = getConfig();
        const tagName = node.tags?.find(t => t.key === 'name')?.value;
        const displayName = tagName || node.name || 'Unnamed Node';
        const emoji = typeEmoji(node.adv_type);

        let lat = node.lat;
        let lon = node.lon;
        if (!lat || !lon) {
            for (const tag of node.tags || []) {
                if (tag.key === 'lat' && !lat) lat = parseFloat(tag.value);
                if (tag.key === 'lon' && !lon) lon = parseFloat(tag.value);
            }
        }
        const hasCoords = lat != null && lon != null && !(lat === 0 && lon === 0);

        const advertisements = adsData.items || [];

        const heroHtml = hasCoords
            ? html`
<div class="relative rounded-box overflow-hidden mb-6 shadow-xl" style="height: 180px;">
    <div id="header-map" class="absolute inset-0 z-0"></div>
    <div class="relative z-20 h-full p-3 flex items-center justify-end">
        <div id="qr-code" class="bg-white p-2 rounded shadow-lg"></div>
    </div>
</div>`
            : html`
<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body flex-row items-center gap-4">
        <div id="qr-code" class="bg-white p-1 rounded"></div>
        <p class="text-sm opacity-70">Scan to add as contact</p>
    </div>
</div>`;

        const coordsHtml = hasCoords
            ? html`<div><span class="opacity-70">Location:</span> ${lat}, ${lon}</div>`
            : nothing;

        const adsTableHtml = advertisements.length > 0
            ? html`<div class="overflow-x-auto">
                <table class="table table-compact w-full">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Type</th>
                            <th>Received By</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${advertisements.map(adv => {
                            const advEmoji = adv.adv_type ? typeEmoji(adv.adv_type) : '';
                            const advTypeHtml = adv.adv_type
                                ? html`<span title=${adv.adv_type.charAt(0).toUpperCase() + adv.adv_type.slice(1)}>${advEmoji}</span>`
                                : html`<span class="opacity-50">-</span>`;
                            const recvName = adv.received_by ? (adv.receiver_tag_name || adv.receiver_name) : null;
                            const receiverHtml = !adv.received_by
                                ? html`<span class="opacity-50">-</span>`
                                : recvName
                                    ? html`<a href="/nodes/${adv.received_by}" class="link link-hover">
                                        <div class="font-medium text-sm">${recvName}</div>
                                        <div class="text-xs font-mono opacity-70">${adv.received_by.slice(0, 16)}...</div>
                                    </a>`
                                    : html`<a href="/nodes/${adv.received_by}" class="link link-hover">
                                        <span class="font-mono text-xs">${adv.received_by.slice(0, 16)}...</span>
                                    </a>`;
                            return html`<tr>
                                <td class="text-xs whitespace-nowrap">${formatDateTime(adv.received_at)}</td>
                                <td>${advTypeHtml}</td>
                                <td>${receiverHtml}</td>
                            </tr>`;
                        })}
                    </tbody>
                </table>
            </div>`
            : html`<p class="opacity-70">No advertisements recorded.</p>`;

        const tags = node.tags || [];
        const tagsTableHtml = tags.length > 0
            ? html`<div class="overflow-x-auto">
                <table class="table table-compact w-full">
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Value</th>
                            <th>Type</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tags.map(tag => html`<tr>
                            <td class="font-mono">${tag.key}</td>
                            <td>${tag.value || ''}</td>
                            <td class="opacity-70">${tag.value_type || 'string'}</td>
                        </tr>`)}
                    </tbody>
                </table>
            </div>`
            : html`<p class="opacity-70">No tags defined.</p>`;

        const adminTagsHtml = (config.admin_enabled && config.is_authenticated)
            ? html`<div class="mt-3">
                <a href="/a/node-tags?public_key=${node.public_key}" class="btn btn-sm btn-outline">${tags.length > 0 ? 'Edit Tags' : 'Add Tags'}</a>
            </div>`
            : nothing;

        litRender(html`
<div class="breadcrumbs text-sm mb-4">
    <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/nodes">Nodes</a></li>
        <li>${tagName || node.name || node.public_key.slice(0, 12) + '...'}</li>
    </ul>
</div>

<h1 class="text-3xl font-bold mb-6">
    <span title=${node.adv_type || 'Unknown'}>${emoji}</span>
    ${displayName}
</h1>

${heroHtml}

<div class="card bg-base-100 shadow-xl mb-6">
    <div class="card-body">
        <div>
            <h3 class="font-semibold opacity-70 mb-2">Public Key</h3>
            <code class="text-sm bg-base-200 p-2 rounded block break-all">${node.public_key}</code>
        </div>
        <div class="flex flex-wrap gap-x-8 gap-y-2 mt-4 text-sm">
            <div><span class="opacity-70">First seen:</span> ${formatDateTime(node.first_seen)}</div>
            <div><span class="opacity-70">Last seen:</span> ${formatDateTime(node.last_seen)}</div>
            ${coordsHtml}
        </div>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Recent Advertisements</h2>
            ${adsTableHtml}
        </div>
    </div>

    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Tags</h2>
            ${tagsTableHtml}
            ${adminTagsHtml}
        </div>
    </div>
</div>`, container);

        // Initialize map if coordinates exist
        if (hasCoords && typeof L !== 'undefined') {
            const map = L.map('header-map', {
                zoomControl: false, dragging: false, scrollWheelZoom: false,
                doubleClickZoom: false, boxZoom: false, keyboard: false,
                attributionControl: false,
            });
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            map.setView([lat, lon], 14);
            const point = map.latLngToContainerPoint([lat, lon]);
            const newPoint = L.point(point.x + map.getSize().x * 0.17, point.y);
            const newLatLng = map.containerPointToLatLng(newPoint);
            map.setView(newLatLng, 14, { animate: false });
            const icon = L.divIcon({
                html: '<span style="font-size: 32px; text-shadow: 0 0 3px #1a237e, 0 0 6px #1a237e, 0 1px 2px rgba(0,0,0,0.7);">' + emoji + '</span>',
                className: '', iconSize: [32, 32], iconAnchor: [16, 16],
            });
            L.marker([lat, lon], { icon }).addTo(map);
            cleanupFns.push(() => map.remove());
        }

        // Initialize QR code (defer to next frame so layout settles after map init)
        requestAnimationFrame(() => {
            const qrEl = document.getElementById('qr-code');
            if (qrEl && typeof QRCode !== 'undefined') {
                const typeMap = { chat: 1, repeater: 2, room: 3, sensor: 4 };
                const typeNum = typeMap[(node.adv_type || '').toLowerCase()] || 1;
                const url = 'meshcore://contact/add?name=' + encodeURIComponent(displayName) + '&public_key=' + node.public_key + '&type=' + typeNum;
                new QRCode(qrEl, {
                    text: url, width: 140, height: 140,
                    colorDark: '#000000', colorLight: '#ffffff',
                    correctLevel: QRCode.CorrectLevel.L,
                });
            }
        });

        return () => {
            cleanupFns.forEach(fn => fn());
        };
    } catch (e) {
        if (e.message && e.message.includes('404')) {
            litRender(renderNotFound(publicKey), container);
        } else {
            litRender(errorAlert(e.message), container);
        }
    }
}

function renderNotFound(publicKey) {
    return html`
<div class="breadcrumbs text-sm mb-4">
    <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/nodes">Nodes</a></li>
        <li>Not Found</li>
    </ul>
</div>
<div class="alert alert-error">
    ${iconError('stroke-current shrink-0 h-6 w-6')}
    <span>Node not found: ${publicKey}</span>
</div>
<a href="/nodes" class="btn btn-primary mt-4">Back to Nodes</a>`;
}
