import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, typeEmoji, errorAlert, pageColors,
} from '../components.js';
import {
    iconNodes, iconAdvertisements, iconMessages, iconChannel,
} from '../icons.js';

function formatTimeOnly(isoString) {
    if (!isoString) return '-';
    try {
        const config = getConfig();
        const tz = config.timezone_iana || 'UTC';
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '-';
        return date.toLocaleString('en-GB', {
            timeZone: tz,
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false,
        });
    } catch {
        return '-';
    }
}

function formatTimeShort(isoString) {
    if (!isoString) return '-';
    try {
        const config = getConfig();
        const tz = config.timezone_iana || 'UTC';
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '-';
        return date.toLocaleString('en-GB', {
            timeZone: tz,
            hour: '2-digit', minute: '2-digit',
            hour12: false,
        });
    } catch {
        return '-';
    }
}

function renderRecentAds(ads) {
    if (!ads || ads.length === 0) {
        return html`<p class="text-sm opacity-70">No advertisements recorded yet.</p>`;
    }
    const rows = ads.slice(0, 5).map(ad => {
        const friendlyName = ad.tag_name || ad.name;
        const displayName = friendlyName || (ad.public_key.slice(0, 12) + '...');
        const keyLine = friendlyName
            ? html`<div class="text-xs opacity-50 font-mono">${ad.public_key.slice(0, 12)}...</div>`
            : nothing;
        return html`<tr>
            <td>
                <a href="/nodes/${ad.public_key}" class="link link-hover">
                    <div class="font-medium">${displayName}</div>
                </a>
                ${keyLine}
            </td>
            <td>${ad.adv_type ? typeEmoji(ad.adv_type) : html`<span class="opacity-50">-</span>`}</td>
            <td class="text-right text-sm opacity-70">${formatTimeOnly(ad.received_at)}</td>
        </tr>`;
    });

    return html`<div class="overflow-x-auto">
        <table class="table table-compact w-full">
            <thead>
                <tr>
                    <th>Node</th>
                    <th>Type</th>
                    <th class="text-right">Received</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function renderChannelMessages(channelMessages) {
    if (!channelMessages || Object.keys(channelMessages).length === 0) return nothing;

    const channels = Object.entries(channelMessages).map(([channel, messages]) => {
        const msgLines = messages.map(msg => html`
            <div class="text-sm">
                <span class="text-xs opacity-50">${formatTimeShort(msg.received_at)}</span>
                <span class="break-words" style="white-space: pre-wrap;">${msg.text || ''}</span>
            </div>`);

        return html`<div>
            <h3 class="font-semibold text-sm mb-2 flex items-center gap-2">
                <span class="badge badge-info badge-sm">CH${String(channel)}</span>
                Channel ${String(channel)}
            </h3>
            <div class="space-y-1 pl-2 border-l-2 border-base-300">
                ${msgLines}
            </div>
        </div>`;
    });

    return html`<div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title">
                ${iconChannel('h-6 w-6')}
                Recent Channel Messages
            </h2>
            <div class="space-y-4">
                ${channels}
            </div>
        </div>
    </div>`;
}

/** Return a Tailwind grid-cols class for the given visible column count. */
function gridCols(count) {
    if (count <= 1) return '';
    return `md:grid-cols-${count}`;
}

export async function render(container, params, router) {
    try {
        const config = getConfig();
        const features = config.features || {};
        const showNodes = features.nodes !== false;
        const showAdverts = features.advertisements !== false;
        const showMessages = features.messages !== false;

        const [stats, advertActivity, messageActivity, nodeCount] = await Promise.all([
            apiGet('/api/v1/dashboard/stats'),
            apiGet('/api/v1/dashboard/activity', { days: 7 }),
            apiGet('/api/v1/dashboard/message-activity', { days: 7 }),
            apiGet('/api/v1/dashboard/node-count', { days: 7 }),
        ]);

        // Top section: stats + charts
        const topCount = (showNodes ? 1 : 0) + (showAdverts ? 1 : 0) + (showMessages ? 1 : 0);
        const topGrid = gridCols(topCount);

        // Bottom section: recent adverts + recent channel messages
        const bottomCount = (showAdverts ? 1 : 0) + (showMessages ? 1 : 0);
        const bottomGrid = gridCols(bottomCount);

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">Dashboard</h1>
</div>

${topCount > 0 ? html`
<div class="grid grid-cols-1 ${topGrid} gap-6 mb-6">
    ${showNodes ? html`
    <div class="stat bg-base-100 rounded-box shadow-xl panel-glow" style="--panel-color: ${pageColors.nodes}">
        <div class="stat-figure" style="color: ${pageColors.nodes}">
            ${iconNodes('h-8 w-8')}
        </div>
        <div class="stat-title">Total Nodes</div>
        <div class="stat-value" style="color: ${pageColors.nodes}">${stats.total_nodes}</div>
        <div class="stat-desc">All discovered nodes</div>
    </div>` : nothing}

    ${showAdverts ? html`
    <div class="stat bg-base-100 rounded-box shadow-xl panel-glow" style="--panel-color: ${pageColors.adverts}">
        <div class="stat-figure" style="color: ${pageColors.adverts}">
            ${iconAdvertisements('h-8 w-8')}
        </div>
        <div class="stat-title">Advertisements</div>
        <div class="stat-value" style="color: ${pageColors.adverts}">${stats.advertisements_7d}</div>
        <div class="stat-desc">Last 7 days</div>
    </div>` : nothing}

    ${showMessages ? html`
    <div class="stat bg-base-100 rounded-box shadow-xl panel-glow" style="--panel-color: ${pageColors.messages}">
        <div class="stat-figure" style="color: ${pageColors.messages}">
            ${iconMessages('h-8 w-8')}
        </div>
        <div class="stat-title">Messages</div>
        <div class="stat-value" style="color: ${pageColors.messages}">${stats.messages_7d}</div>
        <div class="stat-desc">Last 7 days</div>
    </div>` : nothing}
</div>

<div class="grid grid-cols-1 ${topGrid} gap-6 mb-8">
    ${showNodes ? html`
    <div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title text-base">
                ${iconNodes('h-5 w-5')}
                Total Nodes
            </h2>
            <p class="text-xs opacity-70">Over time (last 7 days)</p>
            <div class="h-32">
                <canvas id="nodeChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${showAdverts ? html`
    <div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title text-base">
                ${iconAdvertisements('h-5 w-5')}
                Advertisements
            </h2>
            <p class="text-xs opacity-70">Per day (last 7 days)</p>
            <div class="h-32">
                <canvas id="advertChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${showMessages ? html`
    <div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title text-base">
                ${iconMessages('h-5 w-5')}
                Messages
            </h2>
            <p class="text-xs opacity-70">Per day (last 7 days)</p>
            <div class="h-32">
                <canvas id="messageChart"></canvas>
            </div>
        </div>
    </div>` : nothing}
</div>` : nothing}

${bottomCount > 0 ? html`
<div class="grid grid-cols-1 ${bottomGrid} gap-6">
    ${showAdverts ? html`
    <div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title">
                ${iconAdvertisements('h-6 w-6')}
                Recent Advertisements
            </h2>
            ${renderRecentAds(stats.recent_advertisements)}
        </div>
    </div>` : nothing}

    ${showMessages ? renderChannelMessages(stats.channel_messages) : nothing}
</div>` : nothing}`, container);

        window.initDashboardCharts(
            showNodes ? nodeCount : null,
            showAdverts ? advertActivity : null,
            showMessages ? messageActivity : null,
        );

        const chartIds = ['nodeChart', 'advertChart', 'messageChart'];
        return () => {
            chartIds.forEach(id => {
                const canvas = document.getElementById(id);
                if (canvas) {
                    const instance = window.Chart.getChart(canvas);
                    if (instance) instance.destroy();
                }
            });
        };

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load dashboard'), container);
    }
}
