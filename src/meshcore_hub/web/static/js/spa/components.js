/**
 * MeshCore Hub SPA - Shared UI Components
 *
 * Reusable rendering functions using lit-html.
 */

import { html, nothing } from 'lit-html';
import { render } from 'lit-html';
import { unsafeHTML } from 'lit-html/directives/unsafe-html.js';
import { t } from './i18n.js';
import { iconAlert, iconError, iconInfo, iconSuccess, iconUser, iconSettings, iconLogout } from './icons.js';

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
    if (!config.oidc_enabled) return false;
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
        ${iconError('stroke-current shrink-0 h-6 w-6')}
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
        ${iconInfo('stroke-current shrink-0 h-6 w-6')}
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
        ${iconSuccess('stroke-current shrink-0 h-6 w-6')}
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
export function renderAuthSection(container, config) {
    if (!container) return;
    if (!config.oidc_enabled) {
        render(nothing, container);
        return;
    }

    const user = config.user;
    if (!user) {
        render(html`
            <a href="/auth/login" class="btn btn-sm btn-outline">${t('auth.login')}</a>
        `, container);
        return;
    }

    const displayName = user.name || user.email || 'User';
    const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    const pictureHtml = user.picture
        ? html`<img src=${user.picture} alt=${displayName} class="w-8 h-8 rounded-full" />`
        : html`<span class="text-sm font-bold">${initials}</span>`;

    const roleBadges = (config.roles || []).map(r => {
        const key = `auth.role_${r}`;
        const label = t(key);
        const name = label !== key ? label : r;
        return html`<span class="badge badge-primary badge-xs">${name}</span>`;
    });

    const adminItem = hasRole('admin')
        ? html`<li><a href="/admin/">${iconSettings('h-4 w-4')} ${t('entities.admin')}</a></li>`
        : nothing;

    const profileItem = html`<li><a href="/profile">${iconUser('h-4 w-4')} ${t('links.profile')}</a></li>`;

    const debugId = config.debug && user.sub
        ? html`<span class="text-xs opacity-40 font-mono">${user.sub}</span>`
        : nothing;

    render(html`
        <div class="dropdown dropdown-end">
            <div tabindex="0" role="button" class="btn btn-ghost btn-circle btn-sm avatar">
                ${pictureHtml}
            </div>
            <ul tabindex="0" class="dropdown-content menu menu-sm z-[1] p-2 shadow bg-base-100 rounded-box w-52 mt-3">
                <li class="menu-title">
                    <div class="flex flex-col gap-1">
                        <span class="font-medium">${displayName}</span>
                        ${debugId}
                        ${roleBadges.length > 0 ? html`<div class="flex flex-wrap gap-1">${roleBadges}</div>` : nothing}
                    </div>
                </li>
                <hr class="my-1 opacity-20">
                ${adminItem}
                ${profileItem}
                <li><a href="/auth/logout">${iconLogout('h-4 w-4')} ${t('auth.logout')}</a></li>
            </ul>
        </div>
    `, container);
}

/**
 * Render a filter card with configurable form fields, submit, and clear buttons.
 * @param {Array<Function>} options.fields - Array of render functions returning lit-html form controls
 * @param {string} options.basePath - Base URL path for the page (e.g., '/nodes')
 * @param {Function} options.navigate - Router navigate function
 * @param {string} [options.submitLabel] - Text for submit button (default: translated "Filter")
 * @param {string} [options.clearLabel] - Text for clear button (default: translated "Clear")
 * @returns {TemplateResult}
 */
export function renderFilterCard({ fields, basePath, navigate, submitLabel, clearLabel }) {
    return html`
        <div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
            <div class="card-body py-4">
                <form method="GET" action=${basePath} class="flex gap-4 flex-wrap items-end" @submit=${createFilterHandler(basePath, navigate)}>
                    ${fields.map(f => f())}
                    <div class="flex gap-2 w-full sm:w-auto">
                        <button type="submit" class="btn btn-primary btn-sm">${submitLabel || t('common.filter')}</button>
                        <a href=${basePath} class="btn btn-ghost btn-sm">${clearLabel || t('common.clear')}</a>
                    </div>
                </form>
            </div>
        </div>
    `;
}

/**
 * Render a single stat card for dashboard/home pages.
 * @param {TemplateResult} options.icon - lit-html icon (from icons.js)
 * @param {string} options.color - CSS color value for glow (e.g., pageColors.dashboard)
 * @param {string} options.title - Stat title
 * @param {string|number} options.value - Stat value
 * @param {string} [options.description] - Optional description
 * @returns {TemplateResult}
 */
export function renderStatCard({ icon, color, title, value, description }) {
    return html`
        <div class="stat bg-base-200 rounded-box shadow panel-glow" style="--panel-color: ${color}">
            <div class="stat-figure" style="color: ${color}">${icon}</div>
            <div class="stat-title">${title}</div>
            <div class="stat-value" style="color: ${color}">${value}</div>
            ${description ? html`<div class="stat-desc">${description}</div>` : nothing}
        </div>`;
}
