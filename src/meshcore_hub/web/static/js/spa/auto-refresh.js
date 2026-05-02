/**
 * Auto-refresh utility for list pages.
 *
 * Reads `auto_refresh_seconds` from the app config. When the interval is > 0
 * it sets up a periodic timer that calls the provided `fetchAndRender` callback
 * and renders a pause/play toggle button into the given container element.
 */

import { html, litRender, getConfig, t } from './components.js';
import { iconPause, iconPlay, iconInfo } from './icons.js';

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
        const pauseIcon = iconPause('w-4 h-4');
        const playIcon = iconPlay('w-4 h-4');

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
