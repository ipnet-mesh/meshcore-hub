/**
 * Auto-refresh utility for list pages.
 *
 * Reads `auto_refresh_seconds` from the app config. When the interval is > 0
 * it sets up a periodic timer that calls the provided `fetchAndRender` callback
 * and renders a pause/play toggle button into the given container element.
 */

import { html, litRender, getConfig, t } from './components.js';
import { iconRefresh } from './icons.js';

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
        const tooltip = paused ? t('auto_refresh.resume') : t('auto_refresh.pause');

        litRender(html`
            <label class="label cursor-pointer gap-2" title=${tooltip}>
                <span class="text-sm opacity-80 flex items-center gap-1">
                    ${iconRefresh('w-4 h-4')}
                    <span class="text-xs">${intervalSeconds}s</span>
                </span>
                <input type="checkbox"
                       class="toggle toggle-sm toggle-primary"
                       ?checked=${!paused} @change=${onToggle}>
            </label>
        `, toggleContainer);
    }

    function onToggle(e) {
        paused = !e.target.checked;
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
