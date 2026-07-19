import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, errorAlert, pageColors, renderStatCard, t,
} from '../components.js';
import {
    iconDashboard, iconNodes, iconAdvertisements, iconMessages, iconPackets, iconMembers, iconMap,
    iconPage, iconInfo, iconChart, iconAntenna, iconUsers, iconChannel, iconPath,
    iconSettings, iconFrequency, iconBandwidth, iconSpreadingFactor, iconCodingRate, iconTxPower,
} from '../icons.js';

function renderRadioTiles(rc) {
    if (!rc) return nothing;
    const tiles = [
        { icon: iconSettings, label: t('links.profile'), value: rc.profile },
        { icon: iconFrequency, label: t('home.frequency'), value: rc.frequency },
        { icon: iconBandwidth, label: t('home.bandwidth'), value: rc.bandwidth },
        { icon: iconSpreadingFactor, label: t('home.spreading_factor'), value: rc.spreading_factor },
        { icon: iconCodingRate, label: t('home.coding_rate'), value: rc.coding_rate },
        { icon: iconTxPower, label: t('home.tx_power'), value: rc.tx_power },
    ];
    const visible = tiles.filter(t => t.value);
    if (visible.length === 0) return nothing;
    return html`
        <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
            ${visible.map(({ icon, label, value }) => html`
            <div class="flex flex-col items-center justify-center gap-1.5 p-3
                        border border-base-content/10 rounded-box text-center">
                <span class="radio-tile-icon w-6 h-6">${icon('w-full h-full')}</span>
                <span class="text-xs opacity-70 leading-tight">${label}</span>
                <span class="text-sm font-semibold leading-tight">${String(value)}</span>
            </div>`)}
        </div>`;
}

function renderNavCard({ href, icon, label, colorVar }) {
    return html`
        <a href="${href}" class="w-20 h-20 sm:w-[6.75rem] sm:h-[6.75rem]
            border border-base-content/20 rounded-box
            hover:scale-105 hover:border-base-content/40
            transition-all duration-200 ease-out
            flex flex-col items-center justify-center gap-2
            bg-base-200/50 hover:bg-base-200
            group">
            <span class="w-7 h-7 sm:w-9 sm:h-9 flex items-center justify-center"
                  style="${colorVar ? `color: var(${colorVar})` : ''}">
                ${icon}
            </span>
            <span class="text-xs sm:text-sm font-medium text-base-content">
                ${label}
            </span>
        </a>`;
}

function renderHeroSection({ networkName, logoUrl, logoInvertLight, networkCity, networkCountry, networkWelcomeText, features, customPages }) {
    const cityCountry = (networkCity && networkCountry)
        ? html`<p class="text-lg sm:text-2xl opacity-70 mt-2">${networkCity}, ${networkCountry}</p>`
        : nothing;

    const welcomeText = networkWelcomeText
        ? html`<p class="py-6 max-w-[90%] sm:max-w-[70%]">${networkWelcomeText}</p>`
        : html`<p class="py-6 max-w-[90%] sm:max-w-[70%]">
            ${t('home.welcome_default', { network_name: networkName })}
        </p>`;

    return html`
        <div class="flex flex-col items-center text-center flex-1">
            <div class="flex flex-col sm:flex-row items-center gap-4 sm:gap-8">
                <img src="${logoUrl}" alt="${networkName}" class="theme-logo ${logoInvertLight ? 'theme-logo--invert-light' : ''} h-24 w-24 sm:h-36 sm:w-36" />
                <div class="flex flex-col justify-center">
                    <h1 class="hero-title text-3xl sm:text-5xl lg:text-6xl font-black tracking-tight">${networkName}</h1>
                    ${cityCountry}
                </div>
            </div>
            <div class="flex-1 flex items-center justify-center w-full">
                ${welcomeText}
            </div>
            <div class="flex flex-wrap justify-center justify-items-center gap-2
                    sm:grid sm:grid-cols-4 min-[1536px]:grid-cols-8
                    sm:gap-3 min-[1536px]:gap-2">
                ${features.dashboard !== false ? renderNavCard({
                    href: '/dashboard',
                    icon: iconDashboard('w-full h-full'),
                    label: t('entities.dashboard'),
                    colorVar: '--color-dashboard',
                }) : nothing}
                ${features.nodes !== false ? renderNavCard({
                    href: '/nodes',
                    icon: iconNodes('w-full h-full'),
                    label: t('entities.nodes'),
                    colorVar: '--color-nodes',
                }) : nothing}
                ${features.advertisements !== false ? renderNavCard({
                    href: '/advertisements',
                    icon: iconAdvertisements('w-full h-full'),
                    label: t('entities.advertisements'),
                    colorVar: '--color-adverts',
                }) : nothing}
                ${features.routes !== false ? renderNavCard({
                    href: '/routes',
                    icon: iconPath('w-full h-full'),
                    label: t('entities.routes'),
                    colorVar: '--color-routes',
                }) : nothing}
                ${features.channels !== false ? renderNavCard({
                    href: '/channels',
                    icon: iconChannel('w-full h-full'),
                    label: t('entities.channels'),
                    colorVar: '--color-channels',
                }) : nothing}
                ${features.messages !== false ? renderNavCard({
                    href: '/messages',
                    icon: iconMessages('w-full h-full'),
                    label: t('entities.messages'),
                    colorVar: '--color-messages',
                }) : nothing}
                ${features.packets !== false ? renderNavCard({
                    href: '/packets',
                    icon: iconPackets('w-full h-full'),
                    label: t('entities.packets'),
                    colorVar: '--color-packets',
                }) : nothing}
                ${features.map !== false ? renderNavCard({
                    href: '/map',
                    icon: iconMap('w-full h-full'),
                    label: t('entities.map'),
                    colorVar: '--color-map',
                }) : nothing}
                ${features.members !== false ? renderNavCard({
                    href: '/members',
                    icon: iconMembers('w-full h-full'),
                    label: t('entities.members'),
                    colorVar: '--color-members',
                }) : nothing}
            </div>
            ${features.pages !== false && customPages.length > 0 ? html`
            <div class="flex flex-wrap justify-center gap-3 mt-4">
                ${customPages.slice(0, 3).map(page => html`
                <a href="${page.url}" class="btn btn-outline border-base-content/20">
                    ${iconPage('h-5 w-5 mr-2')}
                    ${page.title}
                </a>`)}
            </div>` : nothing}
        </div>`;
}

function renderStatsPanel({ features, stats }) {
    return html`
        <div class="flex flex-col gap-4">
            ${features.nodes !== false ? renderStatCard({
                icon: iconNodes('h-8 w-8'),
                color: pageColors.nodes,
                title: t('entities.nodes'),
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
            ${features.packets !== false ? renderStatCard({
                icon: iconPackets('h-8 w-8'),
                color: pageColors.packets,
                title: t('entities.packets'),
                value: stats.packets_7d,
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

function renderMembersPanel({ features, stats }) {
    if (features.members === false) return nothing;
    return html`
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">
                    ${iconMembers('h-6 w-6')}
                    ${t('entities.members')}
                </h2>
                <div class="grid grid-cols-1 gap-4 mt-2">
                    ${renderStatCard({
                        icon: iconAntenna('h-6 w-6'),
                        color: pageColors.members,
                        title: t('members_page.operators'),
                        value: stats.total_operators ?? 0,
                    })}
                    ${renderStatCard({
                        icon: iconUsers('h-6 w-6'),
                        color: pageColors.members,
                        title: t('members_page.members'),
                        value: stats.total_members ?? 0,
                    })}
                </div>
            </div>
        </div>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    try {
        const config = getConfig();
        const features = config.features || {};
        const networkName = config.network_name || 'MeshCore Network';
        const logoUrl = config.logo_url || '/static/img/logo.svg';
        const logoInvertLight = config.logo_invert_light !== false;
        const customPages = config.custom_pages || [];
        const rc = config.network_radio_config;

        const [stats, advertActivity, messageActivity] = await Promise.all([
            apiGet('/api/v1/dashboard/stats', {}, { signal }),
            apiGet('/api/v1/dashboard/activity', { days: 7 }, { signal }),
            apiGet('/api/v1/dashboard/message-activity', { days: 7 }, { signal }),
        ]);

        const showStats = features.nodes !== false || features.advertisements !== false || features.messages !== false || features.packets !== false;
        const showAdvertSeries = features.advertisements !== false;
        const showMessageSeries = features.messages !== false;
        const showActivityChart = showAdvertSeries || showMessageSeries;
        const showMembersPanel = features.members !== false;
        const showRadioPanel = features.radio_config !== false;

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
    <div class="flex flex-col ${showStats ? 'lg:col-span-2' : ''}">
        ${heroSection}
    </div>
    ${showStats ? statsPanel : nothing}
</div>

<div class="grid grid-cols-1 md:grid-cols-2 ${(showRadioPanel && showMembersPanel && showActivityChart) ? 'lg:grid-cols-3' : ''} gap-6 mt-6">
    ${showRadioPanel ? html`
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">
                ${iconInfo('h-6 w-6')}
                ${t('home.network_info')}
            </h2>
            <div class="mt-2">
                ${renderRadioTiles(rc)}
            </div>
        </div>
    </div>
    ` : nothing}

    ${renderMembersPanel({ features, stats })}

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
        if (isAbortError(e)) return;
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
