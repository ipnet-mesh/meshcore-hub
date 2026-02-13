/**
 * MeshCore Hub - Chart.js Helpers
 *
 * Provides common chart configuration and initialization helpers
 * for activity charts used on home and dashboard pages.
 */

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

    // Neutral grays (not page-specific)
    grid: 'oklch(0.4 0 0 / 0.2)',
    text: 'oklch(0.7 0 0)',
    tooltipBg: 'oklch(0.25 0 0)',
    tooltipText: 'oklch(0.9 0 0)',
    tooltipBorder: 'oklch(0.4 0 0)'
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
                position: 'bottom',
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
                borderWidth: 1
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
                    precision: 0
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
            fill: false,
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
            fill: false,
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
 * Initialize dashboard charts (nodes, advertisements, messages).
 * Pass null for any data parameter to skip that chart.
 * @param {Object|null} nodeData - Node count data, or null to skip
 * @param {Object|null} advertData - Advertisement data, or null to skip
 * @param {Object|null} messageData - Message data, or null to skip
 */
function initDashboardCharts(nodeData, advertData, messageData) {
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
}
