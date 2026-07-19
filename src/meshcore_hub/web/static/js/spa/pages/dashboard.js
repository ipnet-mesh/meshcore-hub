import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, getChannelLabelsMap, resolveChannelLabel,
    observerIcons, routeTypeBadge, errorAlert, t, formatDateTime, formatNumber,
} from '../components.js';
import {
    iconNodes, iconAdvertisements, iconMessages, iconPackets, iconChannel,
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
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
        hour12: false,
    });
}

function renderRecentAds(ads) {
    if (!ads || ads.length === 0) {
        return html`<p class="text-sm opacity-70">${t('common.no_entity_yet', { entity: t('entities.advertisements').toLowerCase() })}</p>`;
    }
    const rows = ads.map(ad => {
        const friendlyName = ad.tag_name || ad.name;
        const displayName = friendlyName || (ad.public_key.slice(0, 12) + '...');
        const keyLine = friendlyName
            ? html`<div class="text-xs opacity-50 font-mono">${ad.public_key.slice(0, 12)}...</div>`
            : nothing;
        let observersBlock;
        if (ad.observers && ad.observers.length >= 1) {
            observersBlock = html`${observerIcons(ad.observers)}`;
        } else if (ad.observed_by) {
            observersBlock = html`<span class="opacity-50">\u{1F4E1}</span>`;
        } else {
            observersBlock = html`<span class="opacity-50">-</span>`;
        }
        return html`<tr>
            <td>
                <a href="/nodes/${ad.public_key}" class="link link-hover">
                    <div class="font-medium">${displayName}</div>
                </a>
                ${keyLine}
            </td>
            <td class="hidden md:table-cell">${routeTypeBadge(ad.route_type)}</td>
            <td class="text-right text-sm opacity-70">${formatTimeOnly(ad.received_at)}</td>
            <td>${observersBlock}</td>
        </tr>`;
    });

    return html`<div class="overflow-x-auto">
        <table class="table table-sm w-full">
            <thead>
                <tr>
                    <th>${t('entities.node')}</th>
                    <th class="hidden md:table-cell">${t('common.type')}</th>
                    <th class="text-right">${t('common.received')}</th>
                    <th>${t('common.observers')}</th>
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

    return html`<div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-messages)">
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

/** Return responsive Tailwind grid-cols classes for the given visible column count. */
function gridCols(count) {
    if (count === 2) return 'sm:grid-cols-2';
    if (count === 3) return 'sm:grid-cols-2 lg:grid-cols-3';
    if (count === 4) return 'sm:grid-cols-2 lg:grid-cols-4';
    return '';
}

function renderRoutesHealth(routes) {
    if (!routes || routes.length === 0) {
        return html`<p class="text-sm opacity-70">${t('dashboard.routes_empty')}</p>`;
    }
    // Top 6 by current matched_count, mirroring the trend chart cap so the
    // two widgets surface the same routes.
    const sorted = routes.slice().sort((a, b) => (b.matched_count || 0) - (a.matched_count || 0));
    const maxRows = 6;
    const visible = sorted.slice(0, maxRows);
    const hidden = sorted.length - visible.length;

    const colorFor = (q) => {
        // Mirrors ChartColors.quality in charts.js but reads CSS vars so the
        // strips stay in sync with the legend.
        const map = {
            clear:       'oklch(0.72 0.17 145)',
            marginal:    'oklch(0.75 0.18 85)',
            failing:     'oklch(0.62 0.24 25)',
            no_coverage: 'oklch(0.65 0.15 250)',
            disabled:    'oklch(0.55 0 0)',
        };
        return map[q] || map.no_coverage;
    };
    const labelFor = (q) => t('routes.quality_' + (q || 'unknown'));

    const rows = visible.map(r => {
        const cells = (r.history || []).map(d => html`
            <div class="route-health-cell"
                 style="background:${colorFor(d.quality)}"
                 title="${d.date} \u2014 ${labelFor(d.quality)} (${d.matched_count})"></div>`);
        // Right-most dot = rolling 7-day average tier (same computation as
        // the chart line color and the route-card badge on /routes). Falls
        // back to the snapshot if history is missing (e.g. backend degraded).
        const hist = r.history || [];
        const avgTier = (window.averageRouteTier && hist.length > 0)
            ? window.averageRouteTier(hist)
            : null;
        const current = avgTier
            || (r.enabled ? (r.quality || 'no_coverage') : 'disabled');
        return html`<div class="flex items-center gap-2">
            <span class="flex-1 min-w-0 truncate text-sm"
               title="${r.from_label} \u2192 ${r.to_label}">
                ${r.from_label} <span class="opacity-50">\u2192</span> ${r.to_label}
            </span>
            <div class="flex gap-0.5 flex-shrink-0">${cells}</div>
            <span class="w-2 h-2 rounded-full flex-shrink-0"
                  style="background:${colorFor(current)}"
                  title="${labelFor(current)}"></span>
        </div>`;
    });

    return html`<div class="space-y-2">
        ${rows}
        ${hidden > 0 ? html`<p class="text-xs opacity-60 pt-1">${t('dashboard.routes_more', { count: hidden })}</p>` : nothing}
    </div>`;
}

function renderChartCards({ showNodes, showAdverts, showMessages, showPackets, showRoutes, stats, packetBreakdown, routesOverview }) {
    const visibleCount = (showNodes ? 1 : 0) + (showAdverts ? 1 : 0) + (showMessages ? 1 : 0) + (showPackets ? 1 : 0);
    if (visibleCount === 0) return nothing;

    const eventTypeTotal = packetBreakdown?.by_event_type?.reduce((s, b) => s + b.count, 0) ?? 0;
    const pathWidthTotal = packetBreakdown?.by_path_width?.reduce((s, b) => s + b.count, 0) ?? 0;
    const hasRoutes = !!(routesOverview && routesOverview.routes && routesOverview.routes.length);

    return html`
<div class="grid grid-cols-1 ${gridCols(visibleCount)} gap-6 mb-8">
    ${showNodes ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-nodes)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${iconNodes('h-5 w-5')}
                        ${t('entities.nodes')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.over_time_last_7_days')}</p>
                </div>
                <div class="text-3xl font-bold leading-none" style="color: var(--color-nodes)">
                    ${formatNumber(stats.total_nodes)}
                </div>
            </div>
            <div class="h-32">
                <canvas id="nodeChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${showAdverts ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-adverts)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${iconAdvertisements('h-5 w-5')}
                        ${t('entities.advertisements')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.per_day_last_7_days')}</p>
                </div>
                <div class="text-3xl font-bold leading-none" style="color: var(--color-adverts)">
                    ${formatNumber(stats.advertisements_7d)}
                </div>
            </div>
            <div class="h-32">
                <canvas id="advertChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${showMessages ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-messages)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${iconMessages('h-5 w-5')}
                        ${t('entities.messages')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.per_day_last_7_days')}</p>
                </div>
                <div class="text-3xl font-bold leading-none" style="color: var(--color-messages)">
                    ${formatNumber(stats.messages_7d)}
                </div>
            </div>
            <div class="h-32">
                <canvas id="messageChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${showPackets ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-packets)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${iconPackets('h-5 w-5')}
                        ${t('entities.packets')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.per_day_last_7_days')}</p>
                </div>
                <div class="text-3xl font-bold leading-none" style="color: var(--color-packets)">
                    ${formatNumber(stats.packets_7d)}
                </div>
            </div>
            <div class="h-32">
                <canvas id="packetChart"></canvas>
            </div>
        </div>
    </div>` : nothing}
</div>

${(showPackets || (showRoutes && hasRoutes)) ? html`
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
    ${showPackets ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-packets)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${iconPackets('h-5 w-5')}
                        ${t('entities.packet_event_types')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.last_7_days')}</p>
                </div>
                <div class="text-3xl font-bold leading-none" style="color: var(--color-packets)">
                    ${formatNumber(eventTypeTotal)}
                </div>
            </div>
            <div class="h-32">
                <canvas id="packetEventTypeChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${showPackets ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-packets)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${iconPackets('h-5 w-5')}
                        ${t('entities.path_hash_width')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.last_7_days')}</p>
                </div>
                <div class="text-3xl font-bold leading-none" style="color: var(--color-packets)">
                    ${formatNumber(pathWidthTotal)}
                </div>
            </div>
            <div class="h-32">
                <canvas id="packetPathWidthChart"></canvas>
            </div>
        </div>
    </div>` : nothing}

    ${(showRoutes && hasRoutes) ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-routes)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${t('dashboard.route_health')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.last_7_days')}</p>
                </div>
            </div>
            ${renderRoutesHealth(routesOverview.routes)}
        </div>
    </div>` : nothing}

    ${(showRoutes && hasRoutes) ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-routes)">
        <div class="card-body">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h2 class="card-title text-base">
                        ${t('dashboard.routes_trend')}
                    </h2>
                    <p class="text-xs opacity-80">${t('time.routes_over_last_n_days', { n: routesOverview.days })}</p>
                </div>
            </div>
            <div class="h-32">
                <canvas id="routesTrendChart"></canvas>
            </div>
        </div>
    </div>` : nothing}
</div>` : nothing}`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    try {
        const config = getConfig();
        let channelLabels = new Map();
        const features = config.features || {};
        const showNodes = features.nodes !== false;
        const showAdverts = features.advertisements !== false;
        const showMessages = features.messages !== false;
        const showPackets = features.packets !== false;
        const showRoutes = features.routes !== false;

        const [stats, recentActivity, advertActivity, messageActivity, nodeCount, packetActivity, packetBreakdown, routesOverview, channelsData] = await Promise.all([
            apiGet('/api/v1/dashboard/stats', {}, { signal }),
            apiGet('/api/v1/dashboard/recent-activity', {}, { signal }),
            apiGet('/api/v1/dashboard/activity', { days: 7 }, { signal }),
            apiGet('/api/v1/dashboard/message-activity', { days: 7 }, { signal }),
            apiGet('/api/v1/dashboard/node-count', { days: 7 }, { signal }),
            apiGet('/api/v1/dashboard/packet-activity', { days: 7 }, { signal }),
            apiGet('/api/v1/dashboard/packet-breakdown', { days: 7 }, { signal }),
            showRoutes ? apiGet('/api/v1/dashboard/routes-overview', { days: 7 }, { signal }) : Promise.resolve(null),
            apiGet('/api/v1/channels', {}, { signal }),
        ]);
        channelLabels = new Map([
            ...getChannelLabelsMap(config),
            ...(channelsData.items || [])
                .map(ch => [parseInt(ch.channel_hash, 16), ch.name])
                .filter(([idx]) => Number.isInteger(idx)),
        ]);

        // Bottom section: recent adverts + recent channel messages
        const bottomCount = (showAdverts ? 1 : 0) + (showMessages ? 1 : 0);
        const bottomGrid = gridCols(bottomCount);

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.dashboard')}</h1>
</div>

${(showNodes || showAdverts || showMessages || showPackets) ? html`
${renderChartCards({ showNodes, showAdverts, showMessages, showPackets, showRoutes, stats, packetBreakdown, routesOverview })}` : nothing}

${bottomCount > 0 ? html`
<div class="grid grid-cols-1 ${bottomGrid} gap-6">
    ${showAdverts ? html`
    <div class="card bg-base-100 shadow-xl panel-accent" style="--panel-color: var(--color-adverts)">
        <div class="card-body">
            <h2 class="card-title">
                ${iconAdvertisements('h-6 w-6')}
                ${t('common.recent_entity', { entity: t('entities.advertisements') })}
            </h2>
            ${renderRecentAds(recentActivity.recent_advertisements)}
        </div>
    </div>` : nothing}

    ${showMessages ? renderChannelMessages(recentActivity.channel_messages, channelLabels) : nothing}
</div>` : nothing}`, container);

        window.initDashboardCharts(
            showNodes ? nodeCount : null,
            showAdverts ? advertActivity : null,
            showMessages ? messageActivity : null,
            showPackets ? packetActivity : null,
            showPackets ? packetBreakdown.by_event_type : null,
            showPackets ? packetBreakdown.by_path_width : null,
            (showRoutes && routesOverview && routesOverview.routes) ? routesOverview.routes : null,
        );

        const chartIds = ['nodeChart', 'advertChart', 'messageChart', 'packetChart', 'packetEventTypeChart', 'packetPathWidthChart', 'routesTrendChart'];
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
        if (isAbortError(e)) return;
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
