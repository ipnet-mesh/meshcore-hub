/**
 * MeshCore Hub SPA - Shared UI Components
 *
 * Reusable rendering functions using lit-html.
 */

import { html, nothing } from 'lit-html';
import { render } from 'lit-html';
import { unsafeHTML } from 'lit-html/directives/unsafe-html.js';
import { t } from './i18n.js';
import { iconAlert } from './icons.js';

// Re-export lit-html utilities for page modules
export { html, nothing, unsafeHTML };
export { render as litRender } from 'lit-html';
export { t } from './i18n.js';

/**
 * Get app config from the embedded window object.
 * @returns {Object} App configuration
 */
export function getConfig() {
    return window.__APP_CONFIG__ || {};
}

/**
 * Check if the current session has a specific role.
 * Returns true when OIDC is disabled (open access).
 * Translates symbolic role names (e.g. "admin") to actual IdP role names
 * via the role_names config mapping.
 * @param {string} roleName - Symbolic role to check
 * @returns {boolean}
 */
export function hasRole(roleName) {
    const config = getConfig();
    if (!config.oidc_enabled) return true;
    const actualRole = (config.role_names || {})[roleName] || roleName;
    return (config.roles || []).includes(actualRole);
}

/**
 * Build channel label map from app config.
 * Keys are numeric channel indexes and values are non-empty labels.
 *
 * @param {Object} [config]
 * @returns {Map<number, string>}
 */
export function getChannelLabelsMap(config = getConfig()) {
    return new Map(
        Object.entries(config.channel_labels || {})
            .map(([idx, label]) => [parseInt(idx, 10), typeof label === 'string' ? label.trim() : ''])
            .filter(([idx, label]) => Number.isInteger(idx) && label.length > 0),
    );
}

/**
 * Resolve a channel label from a numeric index.
 *
 * @param {number|string} channelIdx
 * @param {Map<number, string>} [channelLabels]
 * @returns {string|null}
 */
export function resolveChannelLabel(channelIdx, channelLabels = getChannelLabelsMap()) {
    const parsed = parseInt(String(channelIdx), 10);
    if (!Number.isInteger(parsed)) return null;
    return channelLabels.get(parsed) || null;
}

/**
 * Parse API datetime strings reliably.
 * MeshCore API often returns UTC timestamps without an explicit timezone suffix.
 * In that case, treat them as UTC by appending 'Z' before Date parsing.
 *
 * @param {string|null} isoString
 * @returns {Date|null}
 */
export function parseAppDate(isoString) {
    if (!isoString || typeof isoString !== 'string') return null;

    let value = isoString.trim();
    if (!value) return null;

    // Normalize "YYYY-MM-DD HH:MM:SS" to ISO separator.
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(value)) {
        value = value.replace(/\s+/, 'T');
    }

    // If no timezone suffix is present, treat as UTC.
    const hasTimePart = /T\d{2}:\d{2}/.test(value);
    const hasTimezoneSuffix = /(Z|[+-]\d{2}:\d{2}|[+-]\d{4})$/i.test(value);
    if (hasTimePart && !hasTimezoneSuffix) {
        value += 'Z';
    }

    const parsed = new Date(value);
    if (isNaN(parsed.getTime())) return null;
    return parsed;
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
function inferNodeType(value) {
    const normalized = (value || '').toLowerCase();
    if (!normalized) return null;
    if (normalized.includes('room')) return 'room';
    if (normalized.includes('repeater') || normalized.includes('relay')) return 'repeater';
    if (normalized.includes('companion') || normalized.includes('observer')) return 'companion';
    if (normalized.includes('chat')) return 'chat';
    return null;
}

export function typeEmoji(advType) {
    switch (inferNodeType(advType) || (advType || '').toLowerCase()) {
        case 'chat': return '\u{1F4AC}';     // 💬
        case 'repeater': return '\u{1F4E1}';  // 📡
        case 'companion': return '\u{1F4F1}'; // 📱
        case 'room': return '\u{1FAA7}';      // 🪧
        default: return '\u{1F4CD}';          // 📍
    }
}

/**
 * Extract the first emoji from a string.
 * Uses a regex pattern that matches emoji characters including compound emojis.
 * @param {string|null} str
 * @returns {string|null} First emoji found, or null if none
 */
export function extractFirstEmoji(str) {
    if (!str) return null;
    // Match emoji using Unicode ranges and zero-width joiners
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{231A}-\u{231B}\u{23E9}-\u{23FA}\u{25AA}-\u{25AB}\u{25B6}\u{25C0}\u{25FB}-\u{25FE}\u{2B50}\u{2B55}\u{3030}\u{303D}\u{3297}\u{3299}](?:\u{FE0F})?(?:\u{200D}[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}](?:\u{FE0F})?)*|\u{00A9}|\u{00AE}|\u{203C}|\u{2049}|\u{2122}|\u{2139}|\u{2194}-\u{2199}|\u{21A9}-\u{21AA}|\u{24C2}|\u{2934}-\u{2935}|\u{2B05}-\u{2B07}|\u{2B1B}-\u{2B1C}/u;
    const match = str.match(emojiRegex);
    return match ? match[0] : null;
}

/**
 * Get the display emoji for a node.
 * Prefers the first emoji from the node name, falls back to type emoji.
 * @param {string|null} nodeName - Node's display name
 * @param {string|null} advType - Advertisement type
 * @returns {string} Emoji character to display
 */
export function getNodeEmoji(nodeName, advType) {
    const nameEmoji = extractFirstEmoji(nodeName);
    if (nameEmoji) return nameEmoji;
    const inferred = inferNodeType(advType) || inferNodeType(nodeName);
    return typeEmoji(inferred || advType);
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
        const locale = config.datetime_locale || 'en-US';
        const date = parseAppDate(isoString);
        if (!date) return '-';
        const opts = options || {
            timeZone: tz,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false,
        };
        if (!opts.timeZone) opts.timeZone = tz;
        return date.toLocaleString(locale, opts);
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
        const locale = config.datetime_locale || 'en-US';
        const date = parseAppDate(isoString);
        if (!date) return '-';
        return date.toLocaleString(locale, {
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
    const date = parseAppDate(isoString);
    if (!date) return '';
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay > 0) return t('time.days_ago', { count: diffDay });
    if (diffHour > 0) return t('time.hours_ago', { count: diffHour });
    if (diffMin > 0) return t('time.minutes_ago', { count: diffMin });
    return t('time.less_than_minute');
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

/**
 * Copy text to clipboard with visual feedback.
 * Updates the target element to show "Copied!" temporarily.
 * Falls back to execCommand for browsers without Clipboard API.
 * @param {Event} e - Click event
 * @param {string} text - Text to copy to clipboard
 */
export function copyToClipboard(e, text) {
    e.preventDefault();
    e.stopPropagation();

    // Capture target element synchronously before async operations
    const targetElement = e.currentTarget;

    const showSuccess = (target) => {
        const originalText = target.textContent;
        target.textContent = 'Copied!';
        target.classList.add('text-success');
        setTimeout(() => {
            target.textContent = originalText;
            target.classList.remove('text-success');
        }, 1500);
    };

    // Try modern Clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showSuccess(targetElement);
        }).catch(err => {
            console.error('Clipboard API failed:', err);
            fallbackCopy(text, targetElement);
        });
    } else {
        // Fallback for older browsers or non-secure contexts
        fallbackCopy(text, targetElement);
    }

    function fallbackCopy(text, target) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand('copy');
            showSuccess(target);
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }
        document.body.removeChild(textArea);
    }
}

// --- UI Components (return lit-html TemplateResult) ---

/**
 * Render a node display with emoji, name, and optional description.
 * Used for consistent node representation across lists (nodes, advertisements, messages, etc.).
 *
 * @param {Object} options - Node display options
 * @param {string|null} options.name - Node display name (from tag or advertised name)
 * @param {string|null} options.description - Node description from tags
 * @param {string} options.publicKey - Node public key (for fallback display)
 * @param {string|null} options.advType - Advertisement type (chat, repeater, room)
 * @param {string} [options.size='base'] - Size variant: 'sm' (small lists) or 'base' (normal)
 * @returns {TemplateResult} lit-html template
 */
export function renderNodeDisplay({ name, description, publicKey, advType, size = 'base' }) {
    const displayName = name || null;
    const emoji = getNodeEmoji(name, advType);
    const emojiSize = size === 'sm' ? 'text-lg' : 'text-lg';
    const nameSize = size === 'sm' ? 'text-sm' : 'text-base';
    const descSize = size === 'sm' ? 'text-xs' : 'text-xs';

    const nameBlock = displayName
        ? html`<div class="font-medium ${nameSize} truncate">${displayName}</div>
               ${description ? html`<div class="${descSize} opacity-70 truncate">${description}</div>` : nothing}`
        : html`<div class="font-mono ${nameSize} truncate">${publicKey.slice(0, 16)}...</div>`;

    return html`
        <div class="flex items-center gap-2 min-w-0">
            <span class="${emojiSize} flex-shrink-0" title=${advType || t('node_types.unknown')}>${emoji}</span>
            <div class="min-w-0">
                ${nameBlock}
            </div>
        </div>`;
}

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
 * Render a warning badge with tooltip for transient API errors.
 * @param {string} message - Error message to display as tooltip
 * @returns {TemplateResult}
 */
export function warningBadge(message) {
    return html`<span class="tooltip tooltip-bottom" data-tip="${message}">
        <span class="badge badge-warning badge-sm">${iconAlert('h-4 w-4')}</span>
    </span>`;
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
            ? html`<a href=${pageUrl(page - 1)} class="join-item btn btn-sm">${t('common.previous')}</a>`
            : html`<button class="join-item btn btn-sm btn-disabled" disabled>${t('common.previous')}</button>`}
        ${pageNumbers}
        ${page < totalPages
            ? html`<a href=${pageUrl(page + 1)} class="join-item btn btn-sm">${t('common.next')}</a>`
            : html`<button class="join-item btn btn-sm btn-disabled" disabled>${t('common.next')}</button>`}
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
 * Render an observer count badge with tooltip listing observer names.
 * @param {Array} observers - Array of observer objects
 * @returns {TemplateResult|nothing}
 */
export function observerIcons(observers) {
    if (!observers || observers.length === 0) return nothing;
    const names = observers.map(o => o.tag_name || o.name || truncateKey(o.public_key, 8));
    const tooltip = names.join(', ');
    return html`<span class="observer-badge-group">\u{1F4E1}<span class="badge badge-sm badge-ghost cursor-help observer-badge" title=${tooltip}>${observers.length}</span></span>`;
}

/**
 * Render an expandable observer detail row.
 * Shows per-observer: name, SNR, path_len, observed_at.
 * @param {Array} observers - Array of observer objects
 * @param {Object} [eventProperties] - Event-level context (unused, for future use)
 * @returns {TemplateResult|nothing}
 */
export function observerDetailRow(observers, eventProperties, options = {}) {
    if (!observers || observers.length === 0) return nothing;
    const showPath = !options.hidePath;
    return html`
        <tr class="observer-detail hidden">
            <td colspan="100" class="p-0">
                <div class="observer-detail-content">
                    <table class="table table-xs w-full">
                        <thead>
                            <tr>
                                <th>Observer</th>
                                <th>${t('common.snr_db')}</th>
                                ${showPath ? html`<th>${t('common.hops')}</th>` : nothing}
                                <th>Received</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${observers.map(o => {
                                const displayName = o.tag_name || o.name || truncateKey(o.public_key, 12);
                                const snrDisplay = o.snr != null ? `${Number(o.snr).toFixed(1)}` : '\u2014';
                                const pathDisplay = o.path_len != null ? `${o.path_len}` : '\u2014';
                                const timeDisplay = formatRelativeTime(o.observed_at);
                                return html`
                                    <tr>
                                        <td>\u{1F4E1} <a href="/nodes/${o.public_key}" class="link link-hover">${displayName}</a></td>
                                        <td>${snrDisplay}</td>
                                        ${showPath ? html`<td>${pathDisplay}</td>` : nothing}
                                        <td><span title=${formatDateTime(o.observed_at)}>${timeDisplay}</span></td>
                                    </tr>
                                `;
                            })}
                        </tbody>
                    </table>
                </div>
            </td>
        </tr>
    `;
}

/**
 * Toggle observer detail row visibility when clicking an event row.
 * @param {Event} event - Click event
 */
export function toggleObserverDetail(event) {
    const row = event.currentTarget;
    const detailRow = row.nextElementSibling;
    if (detailRow && detailRow.classList.contains('observer-detail')) {
        detailRow.classList.toggle('hidden');
    }
}

export function toggleCardObserverDetail(event) {
    event.stopPropagation();
    event.preventDefault();
    const card = event.currentTarget.closest('.card');
    if (card) {
        const detail = card.querySelector('.observer-detail-card');
        if (detail) detail.classList.toggle('hidden');
    }
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

/**
 * Render the auth section in the navbar.
 * Shows a login button when not authenticated, or a user dropdown when logged in.
 * @param {HTMLElement} container - The #auth-section element
 * @param {Object} config - App configuration object
 */
function _svgUser() {
    return '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>';
}

function _svgSettings() {
    return '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>';
}

function _svgLogout() {
    return '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" /></svg>';
}

export function renderAuthSection(container, config) {
    if (!container) return;
    if (!config.oidc_enabled) {
        container.innerHTML = '';
        return;
    }

    const user = config.user;
    if (!user) {
        container.innerHTML = `
            <a href="/auth/login" class="btn btn-sm btn-outline">${t('auth.login')}</a>
        `;
        return;
    }

    const displayName = user.name || user.email || 'User';
    const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    const pictureHtml = user.picture
        ? `<img src="${user.picture}" alt="${displayName}" class="w-8 h-8 rounded-full" />`
        : `<span class="text-sm font-bold">${initials}</span>`;

    const roleBadges = (config.roles || [])
        .map(r => {
            const key = `auth.role_${r}`;
            const label = t(key);
            const name = label !== key ? label : r;
            return `<span class="badge badge-primary badge-xs">${name}</span>`;
        })
        .join('');

    const adminItem = hasRole('admin')
        ? `<li><a href="/admin/">${_svgSettings()} ${t('entities.admin')}</a></li>`
        : '';

    const profileItem = `<li><a href="/profile">${_svgUser()} ${t('links.profile')}</a></li>`;

    const debugId = config.debug && user.sub
        ? `<span class="text-xs opacity-40 font-mono">${user.sub}</span>`
        : '';

    container.innerHTML = `
        <div class="dropdown dropdown-end">
            <div tabindex="0" role="button" class="btn btn-ghost btn-circle btn-sm avatar">
                ${pictureHtml}
            </div>
            <ul tabindex="0" class="dropdown-content menu menu-sm z-[1] p-2 shadow bg-base-100 rounded-box w-52 mt-3">
                <li class="menu-title">
                    <div class="flex flex-col gap-1">
                        <span class="font-medium">${displayName}</span>
                        ${debugId}
                        ${roleBadges ? `<div class="flex flex-wrap gap-1">${roleBadges}</div>` : ''}
                    </div>
                </li>
                <hr class="my-1 opacity-20">
                ${adminItem}
                ${profileItem}
                <li><a href="/auth/logout">${_svgLogout()} ${t('auth.logout')}</a></li>
            </ul>
        </div>
    `;
}
