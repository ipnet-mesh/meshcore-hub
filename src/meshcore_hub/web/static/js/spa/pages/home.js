import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, errorAlert, pageColors, renderStatCard, t,
} from '../components.js';
import {
    iconDashboard, iconNodes, iconAdvertisements, iconMessages, iconMap,
    iconPage, iconInfo, iconChart, iconGlobe, iconGithub,
} from '../icons.js';

function renderRadioConfig(rc) {
    if (!rc) return nothing;
    const fields = [
        [t('links.profile'), rc.profile],
        [t('home.frequency'), rc.frequency],
        [t('home.bandwidth'), rc.bandwidth],
        [t('home.spreading_factor'), rc.spreading_factor],
        [t('home.coding_rate'), rc.coding_rate],
        [t('home.tx_power'), rc.tx_power],
    ];
    return fields
        .filter(([, v]) => v)
        .map(([label, value]) => html`
            <div class="flex justify-between">
                <span class="opacity-70">${label}:</span>
                <span class="font-mono">${String(value)}</span>
            </div>`);
}

function renderHeroSection({ networkName, logoUrl, logoInvertLight, networkCity, networkCountry, networkWelcomeText, features, customPages }) {
    const cityCountry = (networkCity && networkCountry)
        ? html`<p class="text-lg sm:text-2xl opacity-70 mt-2">${networkCity}, ${networkCountry}</p>`
        : nothing;

    const welcomeText = networkWelcomeText
        ? html`<p class="py-4 max-w-[70%]">${networkWelcomeText}</p>`
        : html`<p class="py-4 max-w-[70%]">
            ${t('home.welcome_default', { network_name: networkName })}
        </p>`;

    const customPageButtons = features.pages !== false
        ? customPages.slice(0, 3).map(page => html`
            <a href="${page.url}" class="btn btn-outline">
                ${iconPage('h-5 w-5 mr-2')}
                ${page.title}
            </a>`)
        : [];

    return html`
        <div class="flex flex-col items-center text-center">
            <div class="flex flex-col sm:flex-row items-center gap-4 sm:gap-8 mb-4">
                <img src="${logoUrl}" alt="${networkName}" class="theme-logo ${logoInvertLight ? 'theme-logo--invert-light' : ''} h-24 w-24 sm:h-36 sm:w-36" />
                <div class="flex flex-col justify-center">
                    <h1 class="hero-title text-3xl sm:text-5xl lg:text-6xl font-black tracking-tight">${networkName}</h1>
                    ${cityCountry}
                </div>
            </div>
            ${welcomeText}
            <div class="flex-1"></div>
            <div class="flex flex-wrap justify-center gap-3 mt-auto">
                ${features.dashboard !== false ? html`
                <a href="/dashboard" class="btn btn-outline btn-info">
                    ${iconDashboard('h-5 w-5 mr-2')}
                    ${t('entities.dashboard')}
                </a>` : nothing}
                ${features.nodes !== false ? html`
                <a href="/nodes" class="btn btn-outline btn-primary">
                    ${iconNodes('h-5 w-5 mr-2')}
                    ${t('entities.nodes')}
                </a>` : nothing}
                ${features.advertisements !== false ? html`
                <a href="/advertisements" class="btn btn-outline btn-secondary">
                    ${iconAdvertisements('h-5 w-5 mr-2')}
                    ${t('entities.advertisements')}
                </a>` : nothing}
                ${features.messages !== false ? html`
                <a href="/messages" class="btn btn-outline btn-accent">
                    ${iconMessages('h-5 w-5 mr-2')}
                    ${t('entities.messages')}
                </a>` : nothing}
                ${features.map !== false ? html`
                <a href="/map" class="btn btn-outline btn-warning">
                    ${iconMap('h-5 w-5 mr-2')}
                    ${t('entities.map')}
                </a>` : nothing}
                ${customPageButtons}
            </div>
        </div>`;
}

function renderStatsPanel({ features, stats }) {
    return html`
        <div class="flex flex-col gap-4">
            ${features.nodes !== false ? renderStatCard({
                icon: iconNodes('h-8 w-8'),
                color: pageColors.nodes,
                title: t('common.total_entity', { entity: t('entities.nodes') }),
                value: stats.total_nodes,
                description: t('home.all_discovered_nodes'),
            }) : nothing}
            ${features.advertisements !== false ? renderStatCard({
                icon: iconAdvertisements('h-8 w-8'),
                color: pageColors.adverts,
                title: t('entities.advertisements'),
                value: stats.advertisements_7d,
                description: t('time.last_7_days'),
            }) : nothing}
            ${features.messages !== false ? renderStatCard({
                icon: iconMessages('h-8 w-8'),
                color: pageColors.messages,
                title: t('entities.messages'),
                value: stats.messages_7d,
                description: t('time.last_7_days'),
            }) : nothing}
        </div>`;
}

function renderActivityChartCard({ showAdvertSeries, showMessageSeries }) {
    return html`
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">
                    ${iconChart('h-6 w-6')}
                    ${t('home.network_activity')}
                </h2>
                <p class="text-sm opacity-70 mb-2">${t('time.activity_per_day_last_7_days')}</p>
                <div class="h-48">
                    <canvas id="activityChart"></canvas>
                </div>
            </div>
        </div>`;
}

export async function render(container, params, router) {
    try {
        const config = getConfig();
        const features = config.features || {};
        const networkName = config.network_name || 'MeshCore Network';
        const logoUrl = config.logo_url || '/static/img/logo.svg';
        const logoInvertLight = config.logo_invert_light !== false;
        const customPages = config.custom_pages || [];
        const rc = config.network_radio_config;

        const [stats, advertActivity, messageActivity] = await Promise.all([
            apiGet('/api/v1/dashboard/stats'),
            apiGet('/api/v1/dashboard/activity', { days: 7 }),
            apiGet('/api/v1/dashboard/message-activity', { days: 7 }),
        ]);

        const showStats = features.nodes !== false || features.advertisements !== false || features.messages !== false;
        const showAdvertSeries = features.advertisements !== false;
        const showMessageSeries = features.messages !== false;
        const showActivityChart = showAdvertSeries || showMessageSeries;

        const heroSection = renderHeroSection({
            networkName, logoUrl, logoInvertLight,
            networkCity: config.network_city,
            networkCountry: config.network_country,
            networkWelcomeText: config.network_welcome_text,
            features, customPages,
        });

        const statsPanel = renderStatsPanel({ features, stats });

        const activityChartCard = renderActivityChartCard({ showAdvertSeries, showMessageSeries });

        litRender(html`
<div class="${showStats ? 'grid grid-cols-1 lg:grid-cols-3 gap-6' : ''} bg-base-100 rounded-box shadow-xl p-6">
    <div class="${showStats ? 'lg:col-span-2' : ''}">
        ${heroSection}
    </div>
    ${showStats ? statsPanel : nothing}
</div>

<div class="grid grid-cols-1 md:grid-cols-2 ${showActivityChart ? 'lg:grid-cols-3' : ''} gap-6 mt-6">
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">
                ${iconInfo('h-6 w-6')}
                ${t('home.network_info')}
            </h2>
            <div class="space-y-2">
                ${renderRadioConfig(rc)}
            </div>
        </div>
    </div>

    <div class="card bg-base-100 shadow-xl">
        <div class="card-body flex flex-col items-center justify-center">
            <p class="text-sm opacity-70 mb-4 text-center">${t('home.meshcore_attribution')}</p>
            <a href="https://meshcore.io/" target="_blank" rel="noopener noreferrer" class="hover:opacity-80 transition-opacity">
                <img src="/static/img/meshcore.svg" alt="MeshCore" class="theme-logo theme-logo--invert-light h-8" />
            </a>
            <p class="text-xs opacity-50 mt-4 text-center">Off-Grid, Open-Source Encrypted Messaging</p>
            <div class="flex gap-2 mt-4">
                <a href="https://meshcore.io/" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">
                    ${iconGlobe('h-4 w-4 mr-1')}
                    ${t('links.website')}
                </a>
                <a href="https://github.com/meshcore-dev/MeshCore" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">
                    ${iconGithub('h-4 w-4 mr-1')}
                    ${t('links.github')}
                </a>
            </div>
        </div>
    </div>

    ${showActivityChart ? activityChartCard : nothing}
</div>`, container);

        let chart = null;
        if (showActivityChart) {
            chart = window.createActivityChart(
                'activityChart',
                showAdvertSeries ? advertActivity : null,
                showMessageSeries ? messageActivity : null,
            );
        }

        return () => {
            if (chart) chart.destroy();
        };

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
