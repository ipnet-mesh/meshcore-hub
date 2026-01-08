/**
 * MeshCore Hub - Common JavaScript Utilities
 */

/**
 * Format a timestamp as relative time (e.g., "2m", "1h", "2d")
 * @param {string|Date} timestamp - ISO timestamp string or Date object
 * @returns {string} Relative time string, or empty string if invalid
 */
function formatRelativeTime(timestamp) {
    if (!timestamp) return '';

    const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
    if (isNaN(date.getTime())) return '';

    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffDay > 0) return `${diffDay}d`;
    if (diffHour > 0) return `${diffHour}h`;
    if (diffMin > 0) return `${diffMin}m`;
    return '<1m';
}

/**
 * Populate all elements with data-timestamp attribute with relative time
 */
function populateRelativeTimestamps() {
    document.querySelectorAll('[data-timestamp]:not([data-receiver-tooltip])').forEach(el => {
        const timestamp = el.dataset.timestamp;
        if (timestamp) {
            el.textContent = formatRelativeTime(timestamp);
        }
    });
}

/**
 * Populate receiver tooltip elements with name and relative time
 */
function populateReceiverTooltips() {
    document.querySelectorAll('[data-receiver-tooltip]').forEach(el => {
        const name = el.dataset.name || '';
        const timestamp = el.dataset.timestamp;
        const relTime = timestamp ? formatRelativeTime(timestamp) : '';

        // Build tooltip: "NodeName (2m ago)" or just "NodeName" or just "2m ago"
        let tooltip = name;
        if (relTime) {
            tooltip = name ? `${name} (${relTime} ago)` : `${relTime} ago`;
        }
        el.title = tooltip;
    });
}

/**
 * Populate <time> elements with data-relative-time attribute
 * Uses the datetime attribute as the timestamp source
 */
function populateRelativeTimeElements() {
    document.querySelectorAll('time[data-relative-time]').forEach(el => {
        const timestamp = el.getAttribute('datetime');
        if (timestamp) {
            const relTime = formatRelativeTime(timestamp);
            el.textContent = relTime ? `${relTime} ago` : '';
        }
    });
}

// Auto-populate when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    populateRelativeTimestamps();
    populateReceiverTooltips();
    populateRelativeTimeElements();
});
