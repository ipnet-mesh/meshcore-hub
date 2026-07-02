/**
 * Maintenance page.
 *
 * Rendered for every route when SYSTEM_MAINTENANCE is enabled. This page makes
 * NO backend API calls — the API service / database may be offline while the
 * web component stays up. Keep it dependency-free (no api.js import, no fetch).
 */
import { html, litRender, t, getConfig } from '../components.js';

export async function render(container, params, router) {
    const config = getConfig();
    const logoClass = config.logo_invert_light
        ? 'theme-logo theme-logo--invert-light'
        : 'theme-logo';

    litRender(html`
<div class="hero min-h-[70vh]">
    <div class="hero-content text-center">
        <div class="max-w-md flex flex-col items-center gap-4">
            <img src=${config.logo_url} alt=${config.network_name} class="${logoClass} h-16 w-16" />
            <h1 class="text-3xl font-bold">${config.network_name}</h1>
            <h2 class="text-xl font-semibold text-warning">${t('maintenance.title')}</h2>
            <p class="opacity-70">${t('maintenance.message')}</p>
        </div>
    </div>
</div>`, container);
}
