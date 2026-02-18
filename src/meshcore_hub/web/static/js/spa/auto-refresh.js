/**
 * Auto-refresh utility for list pages.
 *
 * Reads `auto_refresh_seconds` from the app config. When the interval is > 0
 * it sets up a periodic timer that calls the provided `fetchAndRender` callback
 * and renders a pause/play toggle button into the given container element.
 */

import { html, litRender, getConfig, t } from './components.js';

/**
 * Create an auto-refresh controller.
 *
 * @param {Object} options
 * @param {Function} options.fetchAndRender - Async function that fetches data and re-renders the page.
 * @param {HTMLElement} options.toggleContainer - Element to render the pause/play toggle into.
 * @returns {{ cleanup: Function }} cleanup function to stop the timer.
 */
export function createAutoRefresh({ fetchAndRender, toggleContainer }) {
    const config = getConfig();
    const intervalSeconds = config.auto_refresh_seconds || 0;

    if (!intervalSeconds || !toggleContainer) {
        return { cleanup() {} };
    }

    let paused = false;
    let isPending = false;
    let timerId = null;

    function renderToggle() {
        const pauseIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4"><path d="M5.75 3a.75.75 0 0 0-.75.75v12.5c0 .414.336.75.75.75h1.5a.75.75 0 0 0 .75-.75V3.75A.75.75 0 0 0 7.25 3h-1.5ZM12.75 3a.75.75 0 0 0-.75.75v12.5c0 .414.336.75.75.75h1.5a.75.75 0 0 0 .75-.75V3.75a.75.75 0 0 0-.75-.75h-1.5Z"/></svg>`;
        const playIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4"><path d="M6.3 2.84A1.5 1.5 0 0 0 4 4.11v11.78a1.5 1.5 0 0 0 2.3 1.27l9.344-5.891a1.5 1.5 0 0 0 0-2.538L6.3 2.84Z"/></svg>`;

        const tooltip = paused ? t('auto_refresh.resume') : t('auto_refresh.pause');
        const icon = paused ? playIcon : pauseIcon;

        litRender(html`
            <button class="btn btn-ghost btn-xs gap-1 opacity-60 hover:opacity-100"
                    title=${tooltip}
                    @click=${onToggle}>
                ${icon}
                <span class="text-xs">${intervalSeconds}s</span>
            </button>
        `, toggleContainer);
    }

    function onToggle() {
        paused = !paused;
        if (paused) {
            clearInterval(timerId);
            timerId = null;
        } else {
            startTimer();
        }
        renderToggle();
    }

    async function tick() {
        if (isPending || paused) return;
        isPending = true;
        try {
            await fetchAndRender();
        } catch (_e) {
            // Errors are handled inside fetchAndRender; don't stop the timer.
        } finally {
            isPending = false;
        }
    }

    function startTimer() {
        timerId = setInterval(tick, intervalSeconds * 1000);
    }

    // Initial render and start
    renderToggle();
    startTimer();

    return {
        cleanup() {
            if (timerId) {
                clearInterval(timerId);
                timerId = null;
            }
        },
    };
}
