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
 * Initialize dashboard charts (nodes, advertisements, messages, packets,
 * plus optional packet-breakdown stacked bars).
 * Pass null for any data parameter to skip that chart.
 * @param {Object|null} nodeData - Node count data, or null to skip
 * @param {Object|null} advertData - Advertisement data, or null to skip
 * @param {Object|null} messageData - Message data, or null to skip
 * @param {Object|null} packetData - Raw-packet trend data, or null to skip
 * @param {Array|null} [eventTypeData] - Packet event-type breakdown buckets
 * @param {Array|null} [pathWidthData] - Packet path-width breakdown buckets
 */
function initDashboardCharts(nodeData, advertData, messageData, packetData, eventTypeData, pathWidthData) {
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
