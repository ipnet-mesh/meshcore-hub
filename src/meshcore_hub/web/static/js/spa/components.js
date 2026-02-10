/**
 * MeshCore Hub SPA - Shared UI Components
 *
 * Reusable rendering functions using lit-html.
 */

import { html, nothing } from 'lit-html';
import { render } from 'lit-html';
import { unsafeHTML } from 'lit-html/directives/unsafe-html.js';

// Re-export lit-html utilities for page modules
export { html, nothing, unsafeHTML };
export { render as litRender } from 'lit-html';

/**
 * Get app config from the embedded window object.
 * @returns {Object} App configuration
 */
export function getConfig() {
    return window.__APP_CONFIG__ || {};
}

/**
 * Page color palette - reads from CSS custom properties (defined in app.css :root).
 * Use for inline styles or dynamic coloring in page modules.
 */
export const pageColors = {
    get dashboard() { return getComputedStyle(document.documentElement).getPropertyValue('--color-dashboard').trim(); },
    get nodes()     { return getComputedStyle(document.documentElement).getPropertyValue('--color-nodes').trim(); },
    get adverts()   { return getComputedStyle(document.documentElement).getPropertyValue('--color-adverts').trim(); },
    get messages()  { return getComputedStyle(document.documentElement).getPropertyValue('--color-messages').trim(); },
    get map()       { return getComputedStyle(document.documentElement).getPropertyValue('--color-map').trim(); },
    get members()   { return getComputedStyle(document.documentElement).getPropertyValue('--color-members').trim(); },
};

// --- Formatting Helpers (return strings) ---

/**
 * Get the type emoji for a node advertisement type.
 * @param {string|null} advType
 * @returns {string} Emoji character
 */
export function typeEmoji(advType) {
    switch ((advType || '').toLowerCase()) {
        case 'chat': return '\u{1F4AC}';     // 💬
        case 'repeater': return '\u{1F4E1}';  // 📡
        case 'room': return '\u{1FAA7}';      // 🪧
        default: return '\u{1F4CD}';          // 📍
    }
}

/**
 * Format an ISO datetime string to the configured timezone.
 * @param {string|null} isoString
 * @param {Object} [options] - Intl.DateTimeFormat options override
 * @returns {string} Formatted datetime string
 */
export function formatDateTime(isoString, options) {
    if (!isoString) return '-';
    try {
        const config = getConfig();
        const tz = config.timezone_iana || 'UTC';
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '-';
        const opts = options || {
            timeZone: tz,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false,
        };
        if (!opts.timeZone) opts.timeZone = tz;
        return date.toLocaleString('en-GB', opts);
    } catch {
        return isoString ? isoString.slice(0, 19).replace('T', ' ') : '-';
    }
}

/**
 * Format an ISO datetime string to short format (date + HH:MM).
 * @param {string|null} isoString
 * @returns {string}
 */
export function formatDateTimeShort(isoString) {
    if (!isoString) return '-';
    try {
        const config = getConfig();
        const tz = config.timezone_iana || 'UTC';
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '-';
        return date.toLocaleString('en-GB', {
            timeZone: tz,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit',
            hour12: false,
        });
    } catch {
        return isoString ? isoString.slice(0, 16).replace('T', ' ') : '-';
    }
}

/**
 * Format an ISO datetime as relative time (e.g., "2m ago", "1h ago").
 * @param {string|null} isoString
 * @returns {string}
 */
export function formatRelativeTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '';
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay > 0) return `${diffDay}d ago`;
    if (diffHour > 0) return `${diffHour}h ago`;
    if (diffMin > 0) return `${diffMin}m ago`;
    return '<1m ago';
}

/**
 * Truncate a public key for display.
 * @param {string} key - Full public key
 * @param {number} [length=12] - Characters to show
 * @returns {string} Truncated key with ellipsis
 */
export function truncateKey(key, length = 12) {
    if (!key) return '-';
    if (key.length <= length) return key;
    return key.slice(0, length) + '...';
}

/**
 * Escape HTML special characters. Rarely needed with lit-html
 * since template interpolation auto-escapes, but kept for edge cases.
 * @param {string} str
 * @returns {string}
 */
export function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// --- UI Components (return lit-html TemplateResult) ---

/**
 * Render a loading spinner.
 * @returns {TemplateResult}
 */
export function loading() {
    return html`<div class="flex justify-center py-12"><span class="loading loading-spinner loading-lg"></span></div>`;
}

/**
 * Render an error alert.
 * @param {string} message
 * @returns {TemplateResult}
 */
export function errorAlert(message) {
    return html`<div role="alert" class="alert alert-error mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <span>${message}</span>
    </div>`;
}

/**
 * Render an info alert. Use unsafeHTML for HTML content.
 * @param {string} message - Plain text message
 * @returns {TemplateResult}
 */
export function infoAlert(message) {
    return html`<div role="alert" class="alert alert-info mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <span>${message}</span>
    </div>`;
}

/**
 * Render a success alert.
 * @param {string} message
 * @returns {TemplateResult}
 */
export function successAlert(message) {
    return html`<div role="alert" class="alert alert-success mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <span>${message}</span>
    </div>`;
}

/**
 * Render pagination controls.
 * @param {number} page - Current page (1-based)
 * @param {number} totalPages - Total number of pages
 * @param {string} basePath - Base URL path (e.g., '/nodes')
 * @param {Object} [params={}] - Extra query parameters to preserve
 * @returns {TemplateResult|nothing}
 */
export function pagination(page, totalPages, basePath, params = {}) {
    if (totalPages <= 1) return nothing;

    const queryParts = [];
    for (const [k, v] of Object.entries(params)) {
        if (k !== 'page' && v !== null && v !== undefined && v !== '') {
            queryParts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
        }
    }
    const extraQuery = queryParts.length > 0 ? '&' + queryParts.join('&') : '';

    function pageUrl(p) {
        return `${basePath}?page=${p}${extraQuery}`;
    }

    const pageNumbers = [];
    for (let p = 1; p <= totalPages; p++) {
        if (p === page) {
            pageNumbers.push(html`<button class="join-item btn btn-sm btn-active">${p}</button>`);
        } else if (p === 1 || p === totalPages || (p >= page - 2 && p <= page + 2)) {
            pageNumbers.push(html`<a href=${pageUrl(p)} class="join-item btn btn-sm">${p}</a>`);
        } else if (p === 2 || p === totalPages - 1) {
            pageNumbers.push(html`<button class="join-item btn btn-sm btn-disabled" disabled>...</button>`);
        }
    }

    return html`<div class="flex justify-center mt-6"><div class="join">
        ${page > 1
            ? html`<a href=${pageUrl(page - 1)} class="join-item btn btn-sm">Previous</a>`
            : html`<button class="join-item btn btn-sm btn-disabled" disabled>Previous</button>`}
        ${pageNumbers}
        ${page < totalPages
            ? html`<a href=${pageUrl(page + 1)} class="join-item btn btn-sm">Next</a>`
            : html`<button class="join-item btn btn-sm btn-disabled" disabled>Next</button>`}
    </div></div>`;
}

/**
 * Render a timezone indicator for page headers.
 * @returns {TemplateResult|nothing}
 */
export function timezoneIndicator() {
    const config = getConfig();
    const tz = config.timezone || 'UTC';
    return html`<span class="text-xs opacity-50 ml-2">(${tz})</span>`;
}

/**
 * Render receiver node icons with tooltips.
 * @param {Array} receivers
 * @returns {TemplateResult|nothing}
 */
export function receiverIcons(receivers) {
    if (!receivers || receivers.length === 0) return nothing;
    return html`${receivers.map(r => {
        const name = r.receiver_node_name || truncateKey(r.receiver_node_public_key || '', 8);
        const time = formatRelativeTime(r.received_at);
        const tooltip = time ? `${name} (${time})` : name;
        return html`<span class="cursor-help" title=${tooltip}>\u{1F4E1}</span>`;
    })}`;
}

// --- Form Helpers ---

/**
 * Create a submit handler for filter forms that uses SPA navigation.
 * Use as: @submit=${createFilterHandler('/nodes', navigate)}
 * @param {string} basePath - Base URL path for the page
 * @param {Function} navigate - Router navigate function
 * @returns {Function} Event handler
 */
export function createFilterHandler(basePath, navigate) {
    return (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const params = new URLSearchParams();
        for (const [k, v] of formData.entries()) {
            if (v) params.set(k, v);
        }
        const queryStr = params.toString();
        navigate(queryStr ? `${basePath}?${queryStr}` : basePath);
    };
}

/**
 * Auto-submit handler for select/checkbox elements.
 * Use as: @change=${autoSubmit}
 * @param {Event} e
 */
export function autoSubmit(e) {
    e.target.closest('form').requestSubmit();
}

/**
 * Submit form on Enter key in text inputs.
 * Use as: @keydown=${submitOnEnter}
 * @param {KeyboardEvent} e
 */
export function submitOnEnter(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        e.target.closest('form').requestSubmit();
    }
}
