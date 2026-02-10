import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, errorAlert, pageColors,
} from '../components.js';
import {
    iconDashboard, iconNodes, iconAdvertisements, iconMessages, iconMap,
    iconPage, iconInfo, iconChart, iconGlobe, iconGithub,
} from '../icons.js';

function renderRadioConfig(rc) {
    if (!rc) return nothing;
    const fields = [
        ['Profile', rc.profile],
        ['Frequency', rc.frequency],
        ['Bandwidth', rc.bandwidth],
        ['Spreading Factor', rc.spreading_factor],
        ['Coding Rate', rc.coding_rate],
        ['TX Power', rc.tx_power],
    ];
    return fields
        .filter(([, v]) => v)
        .map(([label, value]) => html`
            <div class="flex justify-between">
                <span class="opacity-70">${label}:</span>
                <span class="font-mono">${String(value)}</span>
            </div>`);
}

export async function render(container, params, router) {
    try {
        const config = getConfig();
        const networkName = config.network_name || 'MeshCore Network';
        const logoUrl = config.logo_url || '/static/img/logo.svg';
        const customPages = config.custom_pages || [];
        const rc = config.network_radio_config;

        const [stats, advertActivity, messageActivity] = await Promise.all([
            apiGet('/api/v1/dashboard/stats'),
            apiGet('/api/v1/dashboard/activity', { days: 7 }),
            apiGet('/api/v1/dashboard/message-activity', { days: 7 }),
        ]);

        const cityCountry = (config.network_city && config.network_country)
            ? html`<p class="text-2xl opacity-70 mt-2">${config.network_city}, ${config.network_country}</p>`
            : nothing;

        const welcomeText = config.network_welcome_text
            ? html`<p class="py-4 max-w-[70%]">${config.network_welcome_text}</p>`
            : html`<p class="py-4 max-w-[70%]">
                Welcome to the ${networkName} mesh network dashboard.
                Monitor network activity, view connected nodes, and explore message history.
            </p>`;

        const customPageButtons = customPages.slice(0, 3).map(page => html`
            <a href="${page.url}" class="btn btn-outline btn-neutral">
                ${iconPage('h-5 w-5 mr-2')}
                ${page.title}
            </a>`);

        litRender(html`
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 bg-base-100 rounded-box p-6">
    <div class="lg:col-span-2 flex flex-col items-center text-center">
        <div class="flex items-center gap-8 mb-4">
            <img src="${logoUrl}" alt="${networkName}" class="h-36 w-36" />
            <div class="flex flex-col justify-center">
                <h1 class="text-6xl font-black tracking-tight">${networkName}</h1>
                ${cityCountry}
            </div>
        </div>
        ${welcomeText}
        <div class="flex-1"></div>
        <div class="flex flex-wrap justify-center gap-3 mt-auto">
            <a href="/dashboard" class="btn btn-outline btn-info">
                ${iconDashboard('h-5 w-5 mr-2')}
                Dashboard
            </a>
            <a href="/nodes" class="btn btn-outline btn-primary">
                ${iconNodes('h-5 w-5 mr-2')}
                Nodes
            </a>
            <a href="/advertisements" class="btn btn-outline btn-secondary">
                ${iconAdvertisements('h-5 w-5 mr-2')}
                Adverts
            </a>
            <a href="/messages" class="btn btn-outline btn-accent">
                ${iconMessages('h-5 w-5 mr-2')}
                Messages
            </a>
            <a href="/map" class="btn btn-outline btn-warning">
                ${iconMap('h-5 w-5 mr-2')}
                Map
            </a>
            ${customPageButtons}
        </div>
    </div>

    <div class="flex flex-col gap-4">
        <div class="stat bg-base-200 rounded-box">
            <div class="stat-figure" style="color: ${pageColors.nodes}">
                ${iconNodes('h-8 w-8')}
            </div>
            <div class="stat-title">Total Nodes</div>
            <div class="stat-value" style="color: ${pageColors.nodes}">${stats.total_nodes}</div>
            <div class="stat-desc">All discovered nodes</div>
        </div>

        <div class="stat bg-base-200 rounded-box">
            <div class="stat-figure" style="color: ${pageColors.adverts}">
                ${iconAdvertisements('h-8 w-8')}
            </div>
            <div class="stat-title">Advertisements</div>
            <div class="stat-value" style="color: ${pageColors.adverts}">${stats.advertisements_7d}</div>
            <div class="stat-desc">Last 7 days</div>
        </div>

        <div class="stat bg-base-200 rounded-box">
            <div class="stat-figure" style="color: ${pageColors.messages}">
                ${iconMessages('h-8 w-8')}
            </div>
            <div class="stat-title">Messages</div>
            <div class="stat-value" style="color: ${pageColors.messages}">${stats.messages_7d}</div>
            <div class="stat-desc">Last 7 days</div>
        </div>
    </div>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">
                ${iconInfo('h-6 w-6')}
                Network Info
            </h2>
            <div class="space-y-2">
                ${renderRadioConfig(rc)}
            </div>
        </div>
    </div>

    <div class="card bg-base-100 shadow-xl">
        <div class="card-body flex flex-col items-center justify-center">
            <p class="text-sm opacity-70 mb-4 text-center">Our local off-grid mesh network is made possible by</p>
            <a href="https://meshcore.co.uk/" target="_blank" rel="noopener noreferrer" class="hover:opacity-80 transition-opacity">
                <img src="/static/img/meshcore.svg" alt="MeshCore" class="h-8" />
            </a>
            <p class="text-xs opacity-50 mt-4 text-center">Connecting people and things, without using the internet</p>
            <div class="flex gap-2 mt-4">
                <a href="https://meshcore.co.uk/" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">
                    ${iconGlobe('h-4 w-4 mr-1')}
                    Website
                </a>
                <a href="https://github.com/meshcore-dev/MeshCore" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">
                    ${iconGithub('h-4 w-4 mr-1')}
                    GitHub
                </a>
            </div>
        </div>
    </div>

    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">
                ${iconChart('h-6 w-6')}
                Network Activity
            </h2>
            <p class="text-sm opacity-70 mb-2">Activity per day (last 7 days)</p>
            <div class="h-48">
                <canvas id="activityChart"></canvas>
            </div>
        </div>
    </div>
</div>`, container);

        const chart = window.createActivityChart('activityChart', advertActivity, messageActivity);

        return () => {
            if (chart) chart.destroy();
        };

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load home page'), container);
    }
}
