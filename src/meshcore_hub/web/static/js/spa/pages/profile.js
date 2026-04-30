import { apiGet, apiPut } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, t, errorAlert, successAlert,
    formatRelativeTime, formatDateTime,
} from '../components.js';

function renderAdoptedNode(node) {
    const displayName = node.name || node.public_key.slice(0, 12) + '...';
    const relTime = formatRelativeTime(node.adopted_at);
    const fullTime = formatDateTime(node.adopted_at);

    return html`<a href="/nodes/${node.public_key}" class="flex items-center justify-between gap-3 p-3 bg-base-200 rounded-lg hover:bg-base-300 transition-colors">
        <div class="flex-1 min-w-0">
            <div class="font-medium text-sm truncate">${displayName}</div>
            <div class="font-mono text-xs opacity-60 truncate">${node.public_key}</div>
        </div>
        <time class="text-xs opacity-60 whitespace-nowrap shrink-0" datetime=${node.adopted_at} title=${fullTime} data-relative-time>${relTime}</time>
    </a>`;
}

function renderRoleBadges(roles) {
    if (!roles || roles.length === 0) return nothing;
    return html`<div class="flex gap-2 mt-2">${roles.map(role => html`<span class="badge badge-primary badge-sm">${role}</span>`)}</div>`;
}

function hasOperatorOrAdmin(roles, config) {
    const roleNames = config.role_names || {};
    const operatorRole = roleNames.operator || 'operator';
    const adminRole = roleNames.admin || 'admin';
    return roles && (roles.includes(operatorRole) || roles.includes(adminRole));
}

function renderProfileDetails(profile, config) {
    const memberSince = profile.created_at
        ? html`<p class="text-sm opacity-60 mt-2">${t('user_profile.member_since', { date: formatDateTime(profile.created_at, { year: 'numeric', month: 'long', day: 'numeric' }) })}</p>`
        : nothing;

    const adoptedSection = hasOperatorOrAdmin(profile.roles, config)
        ? html`<div class="card bg-base-100 shadow-xl mt-6">
            <div class="card-body">
                <h2 class="card-title">${t('user_profile.adopted_nodes')}</h2>
                ${profile.nodes && profile.nodes.length > 0
                    ? html`<div class="space-y-2">${profile.nodes.map(n => renderAdoptedNode(n))}</div>`
                    : html`<p class="text-base-content/60 text-sm py-4">${t('user_profile.no_adopted_nodes')}</p>`}
            </div>
        </div>`
        : nothing;

    return html`${memberSince}${adoptedSection}`;
}

function renderPublicProfile(profile, config, target) {
    const isOwner = config.user && profile.user_id && config.user.sub === profile.user_id;

    litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('user_profile.title')}</h1>
    ${isOwner ? html`<a href="/profile" class="btn btn-primary btn-sm">${t('user_profile.edit_profile')}</a>` : nothing}
</div>

<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title">${profile.name || t('common.unnamed')}</h2>
        ${profile.callsign ? html`<span class="badge badge-neutral">${profile.callsign}</span>` : nothing}
        ${renderRoleBadges(profile.roles)}
        ${renderProfileDetails(profile, config)}
    </div>
</div>`, target);
}

export async function render(container, params, router) {
    const config = getConfig();

    if (params.id) {
        try {
            const profile = await apiGet(`/api/v1/user/profile/${params.id}`);
            renderPublicProfile(profile, config, container);
        } catch (e) {
            litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
        }
        return;
    }

    if (!config.oidc_enabled || !config.user) {
        litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    <h1 class="text-3xl font-bold mb-2">${t('user_profile.title')}</h1>
    <p class="opacity-70 mb-6">${t('user_profile.login_to_view')}</p>
    <a href="/auth/login" class="btn btn-primary">${t('auth.login')}</a>
</div>`, container);
        return;
    }

    try {
        const profile = await apiGet('/api/v1/user/profile/me');
        const profilePath = `/api/v1/user/profile/${profile.id}`;

        const flashMessage = (params.query && params.query.message) || '';
        const flashError = (params.query && params.query.error) || '';
        const flashHtml = flashMessage ? successAlert(flashMessage) : flashError ? errorAlert(flashError) : nothing;

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('user_profile.title')}</h1>
</div>

${flashHtml}

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

    <div>
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">${t('user_profile.your_profile')}</h2>
                ${renderRoleBadges(profile.roles)}
                <form id="profile-form" class="py-4 space-y-4">
                    <div class="form-control">
                        <label class="label"><span class="label-text">${t('user_profile.name_label')}</span></label>
                        <input type="text" name="name" class="input input-bordered"
                               value=${profile.name || ''}
                               placeholder=${t('user_profile.name_placeholder')} maxlength="255" />
                    </div>
                    <div class="form-control">
                        <label class="label"><span class="label-text">${t('user_profile.callsign_label')}</span></label>
                        <input type="text" name="callsign" class="input input-bordered"
                               value=${profile.callsign || ''}
                               placeholder=${t('user_profile.callsign_placeholder')} maxlength="20" />
                    </div>
                    <button type="submit" class="btn btn-primary btn-sm">${t('user_profile.save_profile')}</button>
                </form>
            </div>
        </div>
        ${renderProfileDetails(profile, config)}
    </div>

    ${hasOperatorOrAdmin(profile.roles, config) ? html`
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">${t('user_profile.adopted_nodes')}</h2>
            ${profile.nodes && profile.nodes.length > 0
                ? html`<div class="space-y-2">${profile.nodes.map(n => renderAdoptedNode(n))}</div>`
                : html`<p class="text-base-content/60 text-sm py-4">${t('user_profile.no_adopted_nodes')}</p>`}
        </div>
    </div>` : nothing}

</div>`, container);

        const ac = new AbortController();
        const signal = ac.signal;

        container.querySelector('#profile-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const body = {
                name: form.name.value.trim() || null,
                callsign: form.callsign.value.trim() || null,
            };
            try {
                await apiPut(profilePath, body);
                router.navigate('/profile?message=' + encodeURIComponent(t('user_profile.profile_updated')), true);
            } catch (err) {
                router.navigate('/profile?error=' + encodeURIComponent(err.message), true);
            }
        }, { signal });

        return () => ac.abort();

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
