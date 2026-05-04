import { apiGet } from '../api.js';
import { html, litRender, nothing, t, errorAlert, getConfig } from '../components.js';
import { iconAntenna, iconUsers } from '../icons.js';

function renderProfileTile(profile, router) {
    const callsignBadge = profile.callsign
        ? html`<span class="badge badge-neutral badge-sm">${profile.callsign}</span>`
        : nothing;

    const roleBadges = profile.roles && profile.roles.length > 0
        ? html`<div class="flex flex-wrap gap-1 mt-1">${profile.roles.map(role =>
            html`<span class="badge badge-primary badge-sm">${role}</span>`
        )}</div>`
        : nothing;

    const nodeCountLabel = profile.node_count > 0
        ? html`<span class="text-sm opacity-60">${t('members_page.node_count', { count: profile.node_count })}</span>`
        : nothing;

    const nodeBadges = profile.adopted_nodes && profile.adopted_nodes.length > 0
        ? html`<div class="flex flex-wrap gap-1 mt-2">${profile.adopted_nodes.map(node => {
            const label = node.name || node.public_key.slice(0, 12) + '...';
            const handleClick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                router.navigate('/nodes/' + node.public_key);
            };
            return html`<span class="badge badge-secondary badge-sm cursor-pointer" @click=${handleClick}>${label}</span>`;
        })}</div>`
        : nothing;

    const descriptionText = profile.description
        ? html`<p class="text-sm opacity-70 mt-1 truncate">${profile.description}</p>`
        : nothing;

    const urlLink = profile.url
        ? html`<span class="link link-accent text-xs mt-1 inline-block truncate cursor-pointer" @click=${(e) => { e.preventDefault(); e.stopPropagation(); window.open(profile.url, '_blank', 'noopener,noreferrer'); }}>${profile.url}</span>`
        : nothing;

    return html`<a href="/profile/${profile.id}" class="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
        <div class="card-body">
            <h2 class="card-title">
                ${profile.name || t('common.unnamed')}
                ${callsignBadge}
            </h2>
            ${roleBadges}
            ${descriptionText}
            ${urlLink}
            ${nodeCountLabel}
            ${nodeBadges}
        </div>
    </a>`;
}

function renderGroup(title, profiles, icon, router) {
    if (profiles.length === 0) return nothing;
    return html`
<h2 class="text-2xl font-bold mt-8 mb-4 flex items-center gap-2">
    ${icon}${title}
</h2>
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    ${profiles.sort((a, b) => (a.name || '').localeCompare(b.name || '')).map(p => renderProfileTile(p, router))}
</div>`;
}

export async function render(container, params, router) {
    try {
        const config = getConfig();
        const roleNames = config.role_names || {};
        const operatorRole = roleNames.operator || 'operator';
        const memberRole = roleNames.member || 'member';

        const resp = await apiGet('/api/v1/user/profiles', { limit: 500 });
        const profiles = resp.items || [];

        if (profiles.length === 0) {
            litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.members')}</h1>
</div>

<div class="text-center py-12 opacity-70">
    <p class="text-lg">${t('members_page.empty_state')}</p>
    <p class="text-sm mt-2">${t('members_page.empty_description')}</p>
</div>`, container);
            return;
        }

        const operators = profiles.filter(p => p.roles && p.roles.includes(operatorRole));
        const members = profiles.filter(p =>
            p.roles && p.roles.includes(memberRole) && !p.roles.includes(operatorRole)
        );

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.members')}</h1>
    <span class="badge badge-lg">${t('common.count_entity', { count: profiles.length, entity: t('entities.members').toLowerCase() })}</span>
</div>

${renderGroup(t('members_page.operators'), operators, html`<span class="text-primary">${iconAntenna('h-6 w-6')}</span>`, router)}
${renderGroup(t('members_page.members'), members, html`<span class="text-secondary">${iconUsers('h-6 w-6')}</span>`, router)}
`, container);

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
