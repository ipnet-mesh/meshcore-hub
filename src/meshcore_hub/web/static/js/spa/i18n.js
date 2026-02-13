/**
 * MeshCore Hub SPA - Lightweight i18n Module
 *
 * Loads a JSON translation file and provides a t() lookup function.
 * Shares the same locale JSON files with the Python/Jinja2 server side.
 *
 * Usage:
 *   import { t, loadLocale } from './i18n.js';
 *   await loadLocale('en');
 *   t('entities.home');                        // "Home"
 *   t('common.total', { count: 42 });     // "42 total"
 */

let _translations = {};
let _locale = 'en';

/**
 * Load a locale JSON file from the server.
 * @param {string} locale - Language code (e.g. 'en')
 */
export async function loadLocale(locale) {
    try {
        const res = await fetch(`/static/locales/${locale}.json`);
        if (res.ok) {
            _translations = await res.json();
            _locale = locale;
        } else {
            console.warn(`Failed to load locale '${locale}', status ${res.status}`);
        }
    } catch (e) {
        console.warn(`Failed to load locale '${locale}':`, e);
    }
}

/**
 * Resolve a dot-separated key in the translations object.
 * @param {string} key
 * @returns {*}
 */
function resolve(key) {
    return key.split('.').reduce(
        (obj, k) => (obj && typeof obj === 'object' ? obj[k] : undefined),
        _translations,
    );
}

/**
 * Translate a key with optional {{var}} interpolation.
 * Falls back to the key itself if not found.
 * @param {string} key - Dot-separated translation key
 * @param {Object} [params={}] - Interpolation values
 * @returns {string}
 */
export function t(key, params = {}) {
    let val = resolve(key);

    if (typeof val !== 'string') return key;

    // Replace {{var}} placeholders
    if (Object.keys(params).length > 0) {
        val = val.replace(/\{\{(\w+)\}\}/g, (_, k) => (k in params ? String(params[k]) : ''));
    }

    return val;
}

/**
 * Get the currently loaded locale code.
 * @returns {string}
 */
export function getLocale() {
    return _locale;
}

// Also expose t() globally for non-module scripts (e.g. charts.js)
window.t = t;
