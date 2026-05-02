import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, getChannelLabelsMap, resolveChannelLabel,
    typeEmoji, errorAlert, pageColors, renderStatCard, t, formatDateTime,
} from '../components.js';
import {
    iconNodes, iconAdvertisements, iconMessages, iconChannel,
} from '../icons.js';

function channelLabel(channel, channelLabels) {
    const idx = parseInt(String(channel), 10);
    if (Number.isInteger(idx)) {
        return resolveChannelLabel(idx, channelLabels) || `Ch ${idx}`;
    }
    return String(channel);
}

function formatTimeOnly(isoString) {
    return formatDateTime(isoString, {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: false,
    });
}

function formatTimeShort(isoString) {
    return formatDateTime(isoString, {
        hour: '2-digit', minute: '2-digit',
        hour12: false,
    });
}

function renderRecentAds(ads) {
    if (!ads || ads.length === 0) {
        return html`<p class="text-sm opacity-70">${t('common.no_entity_yet', { entity: t('entities.advertisements').toLowerCase() })}</p>`;
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
        <table class="table table-sm w-full">
            <thead>
                <tr>
                    <th>${t('entities.node')}</th>
                    <th>${t('common.type')}</th>
                    <th class="text-right">${t('common.received')}</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function renderChannelMessages(channelMessages, channelLabels) {
    if (!channelMessages || Object.keys(channelMessages).length === 0) return nothing;

    const channels = Object.entries(channelMessages).map(([channel, messages]) => {
        const label = channelLabel(channel, channelLabels);
        const msgLines = messages.map(msg => html`
            <div class="text-sm">
                <span class="text-xs opacity-50">${formatTimeShort(msg.received_at)}</span>
                <span class="break-words" style="white-space: pre-wrap;">${msg.text || ''}</span>
            </div>`);

        return html`<div>
            <h3 class="font-semibold text-sm mb-2 flex items-center gap-2">
                <span class="badge badge-info badge-sm">${label}</span>
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
                ${t('dashboard.recent_channel_messages')}
            </h2>
            <div class="space-y-4">
                ${channels}
            </div>
        </div>
    </div>`;
}

/** Return a Tailwind grid-cols class for the given visible column count. */
function gridCols(count) {
    if (count === 2) return 'md:grid-cols-2';
    if (count === 3) return 'md:grid-cols-3';
    return '';
}

function renderChartCards({ showNodes, showAdverts, showMessages }) {
    const visibleCount = (showNodes ? 1 : 0) + (showAdverts ? 1 : 0) + (showMessages ? 1 : 0);
    if (visibleCount === 0) return nothing;
    return html`
<div class="grid grid-cols-1 ${gridCols(visibleCount)} gap-6 mb-8">
    ${showNodes ? html`
    <div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title text-base">
                ${iconNodes('h-5 w-5')}
                ${t('common.total_entity', { entity: t('entities.nodes') })}
            </h2>
            <p class="text-xs opacity-70">${t('time.over_time_last_7_days')}</p>
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
                ${t('entities.advertisements')}
            </h2>
            <p class="text-xs opacity-70">${t('time.per_day_last_7_days')}</p>
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
                ${t('entities.messages')}
            </h2>
            <p class="text-xs opacity-70">${t('time.per_day_last_7_days')}</p>
            <div class="h-32">
                <canvas id="messageChart"></canvas>
            </div>
        </div>
    </div>` : nothing}
</div>`;
}

export async function render(container, params, router) {
    try {
        const config = getConfig();
        const channelLabels = getChannelLabelsMap(config);
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
    <h1 class="text-3xl font-bold">${t('entities.dashboard')}</h1>
</div>

${topCount > 0 ? html`
<div class="grid grid-cols-1 ${topGrid} gap-6 mb-6">
    ${showNodes ? renderStatCard({
        icon: iconNodes('h-8 w-8'),
        color: pageColors.nodes,
        title: t('common.total_entity', { entity: t('entities.nodes') }),
        value: stats.total_nodes,
        description: t('dashboard.all_discovered_nodes'),
    }) : nothing}

    ${showAdverts ? renderStatCard({
        icon: iconAdvertisements('h-8 w-8'),
        color: pageColors.adverts,
        title: t('entities.advertisements'),
        value: stats.advertisements_7d,
        description: t('time.last_7_days'),
    }) : nothing}

    ${showMessages ? renderStatCard({
        icon: iconMessages('h-8 w-8'),
        color: pageColors.messages,
        title: t('entities.messages'),
        value: stats.messages_7d,
        description: t('time.last_7_days'),
    }) : nothing}
</div>

${renderChartCards({ showNodes, showAdverts, showMessages })}` : nothing}

${bottomCount > 0 ? html`
<div class="grid grid-cols-1 ${bottomGrid} gap-6">
    ${showAdverts ? html`
    <div class="card bg-base-100 shadow-xl panel-glow" style="--panel-color: var(--color-neutral)">
        <div class="card-body">
            <h2 class="card-title">
                ${iconAdvertisements('h-6 w-6')}
                ${t('common.recent_entity', { entity: t('entities.advertisements') })}
            </h2>
            ${renderRecentAds(stats.recent_advertisements)}
        </div>
    </div>` : nothing}

    ${showMessages ? renderChannelMessages(stats.channel_messages, channelLabels) : nothing}
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
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
