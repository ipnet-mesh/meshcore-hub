/**
 * MeshCore Hub - Chart.js Helpers
 *
 * Provides common chart configuration and initialization helpers
 * for activity charts used on home and dashboard pages.
 */

// Match app typography (IBM Plex Sans); Chart.js defaults to Helvetica/Arial.
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = '"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif';
}

/**
 * Format a number with locale-appropriate grouping separators.
 * Uses the visitor's browser locale (no explicit locale argument).
 * @param {number} v
 * @returns {string}
 */
function formatNumber(v) {
    return new Intl.NumberFormat().format(v);
}

/**
 * Read page colors from CSS custom properties (defined in app.css :root).
 * Falls back to hardcoded values if CSS vars are unavailable.
 */
function getCSSColor(varName, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || fallback;
}

function withAlpha(color, alpha) {
    // oklch(0.65 0.24 265) -> oklch(0.65 0.24 265 / 0.1)
    return color.replace(')', ' / ' + alpha + ')');
}

const ChartColors = {
    get nodes()        { return getCSSColor('--color-nodes', 'oklch(0.65 0.24 265)'); },
    get nodesFill()    { return withAlpha(this.nodes, 0.1); },
    get adverts()      { return getCSSColor('--color-adverts', 'oklch(0.7 0.17 330)'); },
    get advertsFill()  { return withAlpha(this.adverts, 0.1); },
    get messages()     { return getCSSColor('--color-messages', 'oklch(0.75 0.18 180)'); },
    get messagesFill() { return withAlpha(this.messages, 0.1); },
    get packets()      { return getCSSColor('--color-packets', 'oklch(0.72 0.17 145)'); },
    get packetsFill()  { return withAlpha(this.packets, 0.1); },
    get routes()       { return getCSSColor('--color-routes', 'oklch(0.72 0.17 30)'); },
    get routesFill()   { return withAlpha(this.routes, 0.1); },

    // Neutral grays (not page-specific)
    grid: 'oklch(0.4 0 0 / 0.2)',
    text: 'oklch(0.7 0 0)',
    tooltipBg: 'oklch(0.25 0 0)',
    tooltipText: 'oklch(0.9 0 0)',
    tooltipBorder: 'oklch(0.4 0 0)',

    // Qualitative palette for stacked breakdown bars (6 hues + neutral grey
    // for "other"). Hardcoded oklch values render consistently across light
    // and dark themes without extra CSS tokens.
    breakdown: [
        'oklch(0.65 0.24 265)',   // blue
        'oklch(0.7 0.17 330)',    // magenta
        'oklch(0.75 0.18 180)',   // teal
        'oklch(0.72 0.17 145)',   // green
        'oklch(0.7 0.19 80)',     // yellow-green
        'oklch(0.65 0.22 25)',    // orange
        'oklch(0.55 0 0)'        // neutral grey (for "other")
    ],

    // Semantic quality palette for route health charts. Hardcoded oklch
    // values (same approach as `breakdown`) — app.css defines no semantic
    // status colors.
    quality: {
        clear:       'oklch(0.72 0.17 145)',
        marginal:    'oklch(0.75 0.18 85)',
        failing:     'oklch(0.62 0.24 25)',
        no_coverage: 'oklch(0.65 0.15 250)',
        disabled:    'oklch(0.55 0 0)'
    }
};

/**
 * Create common chart options with optional legend
 * @param {boolean} showLegend - Whether to show the legend
 * @returns {Object} Chart.js options object
 */
function createChartOptions(showLegend) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: showLegend,
                position: 'top',
                align: 'end',
                labels: {
                    color: ChartColors.text,
                    boxWidth: 12,
                    padding: 8
                }
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                backgroundColor: ChartColors.tooltipBg,
                titleColor: ChartColors.tooltipText,
                bodyColor: ChartColors.tooltipText,
                borderColor: ChartColors.tooltipBorder,
                borderWidth: 1,
                callbacks: {
                    label: function(ctx) {
                        const label = ctx.dataset.label || '';
                        const value = formatNumber(ctx.parsed.y);
                        return label ? label + ': ' + value : value;
                    }
                }
            }
        },
        scales: {
            x: {
                grid: { color: ChartColors.grid },
                ticks: {
                    color: ChartColors.text,
                    maxRotation: 45,
                    minRotation: 45,
                    maxTicksLimit: 10
                }
            },
            y: {
                beginAtZero: true,
                grid: { color: ChartColors.grid },
                ticks: {
                    color: ChartColors.text,
                    precision: 0,
                    callback: function(value) { return formatNumber(value); }
                }
            }
        },
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        }
    };
}

/**
 * Format date labels for chart display (e.g., "8 Feb")
 * @param {Array} data - Array of objects with 'date' property
 * @returns {Array} Formatted date strings
 */
function formatDateLabels(data) {
    return data.map(function(d) {
        var date = new Date(d.date);
        return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    });
}

/**
 * Create a single-dataset line chart
 * @param {string} canvasId - ID of the canvas element
 * @param {Object} data - Data object with 'data' array containing {date, count} objects
 * @param {string} label - Dataset label
 * @param {string} borderColor - Line color
 * @param {string} backgroundColor - Fill color
 * @param {boolean} fill - Whether to fill under the line
 */
function createLineChart(canvasId, data, label, borderColor, backgroundColor, fill) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || !data || !data.data || data.data.length === 0) {
        return null;
    }

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: formatDateLabels(data.data),
            datasets: [{
                label: label,
                data: data.data.map(function(d) { return d.count; }),
                borderColor: borderColor,
                backgroundColor: backgroundColor,
                fill: fill,
                tension: 0.3,
                pointRadius: 2,
                pointHoverRadius: 5
            }]
        },
        options: createChartOptions(false)
    });
}

/**
 * Create a multi-dataset activity chart (for home page).
 * Pass null for advertData or messageData to omit that series.
 * @param {string} canvasId - ID of the canvas element
 * @param {Object|null} advertData - Advertisement data with 'data' array, or null to omit
 * @param {Object|null} messageData - Message data with 'data' array, or null to omit
 */
function createActivityChart(canvasId, advertData, messageData) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    // Build datasets from whichever series are provided
    var datasets = [];
    var labels = null;

    if (advertData && advertData.data && advertData.data.length > 0) {
        if (!labels) labels = formatDateLabels(advertData.data);
        datasets.push({
            label: (window.t && window.t('entities.advertisements')) || 'Advertisements',
            data: advertData.data.map(function(d) { return d.count; }),
            borderColor: ChartColors.adverts,
            backgroundColor: ChartColors.advertsFill,
            fill: true,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 5
        });
    }

    if (messageData && messageData.data && messageData.data.length > 0) {
        if (!labels) labels = formatDateLabels(messageData.data);
        datasets.push({
            label: (window.t && window.t('entities.messages')) || 'Messages',
            data: messageData.data.map(function(d) { return d.count; }),
            borderColor: ChartColors.messages,
            backgroundColor: ChartColors.messagesFill,
            fill: true,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 5
        });
    }

    if (datasets.length === 0 || !labels) return null;

    return new Chart(ctx, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: createChartOptions(true)
    });
}

/**
 * Create a horizontal 100% stacked bar chart from labeled buckets.
 *
 * Each bucket becomes one dataset sized proportionally to its count. The
 * x-axis is fixed at 0-100% and tooltips show the raw count and percentage.
 * Returns null when buckets is empty or the total is zero (matching
 * createLineChart's empty-data idiom).
 *
 * @param {string} canvasId - ID of the canvas element
 * @param {Array|null} buckets - Array of {label, count} objects
 * @param {Array<string>} colors - Ordered color strings (one per bucket)
 * @returns {Chart|null}
 */
function createStackedBarChart(canvasId, buckets, colors) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || !buckets || buckets.length === 0) return null;

    var total = buckets.reduce(function(sum, b) { return sum + b.count; }, 0);
    if (total === 0) return null;

    var datasets = buckets.map(function(bucket, i) {
        var pct = (bucket.count / total) * 100;
        return {
            label: bucket.label,
            data: [pct],
            backgroundColor: colors[i % colors.length],
            borderColor: colors[i % colors.length],
            borderWidth: 1,
            rawCount: bucket.count
        };
    });

    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [''],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: ChartColors.tooltipBg,
                    titleColor: ChartColors.tooltipText,
                    bodyColor: ChartColors.tooltipText,
                    borderColor: ChartColors.tooltipBorder,
                    borderWidth: 1,
                    callbacks: {
                        label: function(ctx) {
                            var label = ctx.dataset.label || '';
                            var count = formatNumber(ctx.dataset.rawCount);
                            var pct = ctx.parsed.x.toFixed(1);
                            return label + ': ' + count + ' (' + pct + '%)';
                        }
                    }
                }
            },
            scales: {
                x: {
                    max: 100,
                    stacked: true,
                    grid: { color: ChartColors.grid },
                    ticks: {
                        color: ChartColors.text,
                        callback: function(value) { return value + '%'; }
                    }
                },
                y: {
                    stacked: true,
                    grid: { display: false },
                    ticks: { display: false }
                }
            },
            interaction: {
                mode: 'nearest',
                intersect: false
            }
        }
    });
}

/**
 * Create a multi-line route-status trend chart for the dashboard.
 *
 * Each route becomes one line plotted on a 3-tier categorical Y axis
 * (``failing`` → ``marginal`` → ``clear``, bottom to top). The line's
 * color reflects the route's CURRENT quality (its latest evaluation),
 * so multiple routes in the same health band share a color — the chart
 * reads as a fleet-health overview rather than per-route identity.
 * Hover tooltips still show the route label, tier, and matched_count.
 *
 * Input is the ``routes`` array from ``GET /dashboard/routes-overview``.
 * The top ``maxRoutes`` routes by current ``matched_count`` are drawn;
 * the rest are dropped silently (summing quality tiers is meaningless).
 *
 * Quality → tier mapping (per the merged-3-tier design):
 *   ``clear``       → clear
 *   ``marginal``    → marginal
 *   anything else   → failing   (covers ``failing``, ``unknown``,
 *                                 ``no_coverage``, ``disabled``, null)
 *
 * @param {string} canvasId - ID of the canvas element
 * @param {Array|null} routes - Array of RouteOverviewEntry objects
 * @param {number} [maxRoutes=6] - Top-N routes drawn distinctly
 * @returns {Chart|null}
 */
function createRoutesTrendChart(canvasId, routes, maxRoutes) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || !routes || routes.length === 0) return null;

    maxRoutes = maxRoutes || 6;

    // Bottom-to-top tier order on the categorical Y axis.
    var tierOrder = ['failing', 'marginal', 'clear'];

    function qualityToTier(q) {
        if (q === 'clear') return 'clear';
        if (q === 'marginal') return 'marginal';
        return 'failing';
    }

    function tierColor(tier) {
        return ChartColors.quality[tier] || ChartColors.quality.failing;
    }

    // Mean tier over the displayed window. Maps the 3-tier space onto a
    // 0/1/2 numeric scale (failing < marginal < clear), averages, then
    // buckets back: >=1.5 → clear, >=0.75 → marginal, else failing.
    // Empty history falls through to failing (matches qualityToTier's
    // default for unknown / null quality).
    function averageTier(history) {
        if (!history || history.length === 0) return 'failing';
        var sum = 0;
        for (var i = 0; i < history.length; i++) {
            var tier = qualityToTier(history[i].quality);
            sum += (tier === 'clear' ? 2 : tier === 'marginal' ? 1 : 0);
        }
        var mean = sum / history.length;
        if (mean >= 1.5) return 'clear';
        if (mean >= 0.75) return 'marginal';
        return 'failing';
    }

    // Sort by current matched_count desc; routes with null matched_count
    // (disabled / never evaluated) sort to the end.
    var sorted = routes.slice().sort(function(a, b) {
        var am = a.matched_count || 0;
        var bm = b.matched_count || 0;
        return bm - am;
    });
    var top = sorted.slice(0, maxRoutes);

    // Use the longest history as the X-axis label source (all routes
    // share the same window in practice, but be defensive).
    var labels = [];
    for (var i = 0; i < top.length; i++) {
        if (top[i].history && top[i].history.length > labels.length) {
            labels = formatDateLabels(top[i].history);
        }
    }
    if (labels.length === 0) return null;

    var datasets = top.map(function(entry) {
        var history = entry.history || [];
        var avgTier = averageTier(history);
        return {
            label: entry.from_label + ' \u2192 ' + entry.to_label,
            data: history.map(function(d) { return qualityToTier(d.quality); }),
            borderColor: tierColor(avgTier),
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.3,
            cubicInterpolationMode: 'monotone',
            pointRadius: 2,
            pointHoverRadius: 5,
            spanGaps: true,
            _matched: history.map(function(d) { return d.matched_count || 0; })
        };
    });

    var opts = createChartOptions(false);
    // Replace the default numeric Y axis with a 3-tier categorical axis.
    opts.scales.y = {
        type: 'category',
        labels: tierOrder,
        reverse: true,
        grid: { color: ChartColors.grid },
        ticks: {
            color: ChartColors.text,
            callback: function(_value, index) {
                var tier = tierOrder[index];
                return (window.t && window.t('routes.quality_' + tier)) || tier;
            }
        }
    };
    // The default tooltip formatter calls formatNumber(ctx.parsed.y),
    // which is wrong for categorical string values; emit tier + matched.
    opts.plugins.tooltip.callbacks = {
        title: function(items) { return items[0].label; },
        label: function(ctx) {
            var tier = tierOrder[ctx.parsed.y] || 'failing';
            var tierLabel = (window.t && window.t('routes.quality_' + tier)) || tier;
            var matched = (ctx.dataset._matched && ctx.dataset._matched[ctx.dataIndex]) || 0;
            return ctx.dataset.label + ': ' + tierLabel + ' (' + matched + ')';
        }
    };

    return new Chart(ctx, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: opts
    });
}

/**
 * Initialize dashboard charts (nodes, advertisements, messages, packets,
 * plus optional packet-breakdown stacked bars and routes overview).
 * Pass null for any data parameter to skip that chart.
 * @param {Object|null} nodeData - Node count data, or null to skip
 * @param {Object|null} advertData - Advertisement data, or null to skip
 * @param {Object|null} messageData - Message data, or null to skip
 * @param {Object|null} packetData - Raw-packet trend data, or null to skip
 * @param {Array|null} [eventTypeData] - Packet event-type breakdown buckets
 * @param {Array|null} [pathWidthData] - Packet path-width breakdown buckets
 * @param {Array|null} [routesData] - Routes overview ``routes`` array
 */
function initDashboardCharts(nodeData, advertData, messageData, packetData, eventTypeData, pathWidthData, routesData) {
    if (nodeData) {
        createLineChart(
            'nodeChart',
            nodeData,
            (window.t && window.t('common.total_entity', { entity: t('entities.nodes') })) || 'Total Nodes',
            ChartColors.nodes,
            ChartColors.nodesFill,
            true
        );
    }

    if (advertData) {
        createLineChart(
            'advertChart',
            advertData,
            (window.t && window.t('entities.advertisements')) || 'Advertisements',
            ChartColors.adverts,
            ChartColors.advertsFill,
            true
        );
    }

    if (messageData) {
        createLineChart(
            'messageChart',
            messageData,
            (window.t && window.t('entities.messages')) || 'Messages',
            ChartColors.messages,
            ChartColors.messagesFill,
            true
        );
    }

    if (packetData) {
        createLineChart(
            'packetChart',
            packetData,
            (window.t && window.t('entities.packets')) || 'Packets',
            ChartColors.packets,
            ChartColors.packetsFill,
            true
        );
    }

    if (eventTypeData && eventTypeData.length > 0) {
        createStackedBarChart(
            'packetEventTypeChart',
            eventTypeData,
            ChartColors.breakdown
        );
    }

    if (pathWidthData && pathWidthData.length > 0) {
        createStackedBarChart(
            'packetPathWidthChart',
            pathWidthData,
            ChartColors.breakdown.slice(0, 3)
        );
    }

    if (routesData && routesData.length > 0) {
        createRoutesTrendChart('routesTrendChart', routesData);
    }
}

/**
 * Create a per-route health status strip — single horizontal bar of N equal
 * colored day-segments.
 *
 * @param {string} canvasId - ID of the canvas element
 * @param {Object} routeData - RouteHistory payload with `data` array
 * @returns {Chart|null}
 */
function createRouteDetailStrip(canvasId, routeData) {
    var ctx = document.getElementById(canvasId);
    if (!ctx || !routeData || !routeData.data || routeData.data.length === 0) {
        return null;
    }

    var existing = Chart.getChart(ctx);
    if (existing) existing.destroy();

    var datasets = routeData.data.map(function(day) {
        return {
            label: day.date,
            data: [1],
            backgroundColor: ChartColors.quality[day.quality] || ChartColors.quality.no_coverage,
            borderColor: ChartColors.quality[day.quality] || ChartColors.quality.no_coverage,
            borderWidth: 1,
            _quality: day.quality,
            _matched_count: day.matched_count || 0
        };
    });

    return new Chart(ctx, {
        type: 'bar',
        data: { labels: [''], datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: ChartColors.tooltipBg,
                    titleColor: ChartColors.tooltipText,
                    bodyColor: ChartColors.tooltipText,
                    borderColor: ChartColors.tooltipBorder,
                    borderWidth: 1,
                    callbacks: {
                        title: function(ctx) { return ctx[0].dataset.label; },
                        label: function(ctx) {
                            var q = ctx.dataset._quality || 'unknown';
                            var label = (window.t && window.t('routes.quality_' + q)) || q;
                            return label + ' (' + ctx.dataset._matched_count + ')';
                        }
                    }
                }
            },
            scales: {
                x: { stacked: true, grid: { display: false }, ticks: { display: false } },
                y: { stacked: true, grid: { display: false }, ticks: { display: false } }
            },
            interaction: { mode: 'nearest', intersect: true }
        }
    });
}
