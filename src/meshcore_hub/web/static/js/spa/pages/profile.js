import { apiGet, apiPut, isAbortError } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, t, errorAlert, successAlert,
    formatRelativeTime, formatDateTime,
} from '../components.js';

function renderAdoptedNode(node) {
    const displayName = node.name || node.public_key.slice(0, 12) + '...';
    const relTime = node.last_seen ? formatRelativeTime(node.last_seen) : '-';
    const fullTime = node.last_seen ? formatDateTime(node.last_seen) : '-';

    return html`<a href="/nodes/${node.public_key}" class="flex items-center justify-between gap-3 p-3 bg-base-200 rounded-lg hover:bg-base-300 transition-colors">
        <div class="flex-1 min-w-0">
            <div class="font-medium text-sm truncate">${displayName}</div>
            <div class="font-mono text-xs opacity-60 truncate">${node.public_key}</div>
        </div>
        <time class="text-xs opacity-60 whitespace-nowrap shrink-0" datetime=${node.last_seen || nothing} title=${fullTime} data-relative-time>${relTime}</time>
    </a>`;
}

function renderMemberSince(profile) {
    return profile.created_at
        ? html`<p class="text-sm opacity-60 mt-2">${t('user_profile.member_since', { date: formatDateTime(profile.created_at, { year: 'numeric', month: 'long', day: 'numeric' }) })}</p>`
        : nothing;
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

    return html`${renderMemberSince(profile)}${adoptedSection}`;
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
        <h2 class="card-title">
            ${profile.name || t('common.unnamed')}
            ${profile.callsign ? html`<span class="badge badge-neutral badge-sm">${profile.callsign}</span>` : nothing}
        </h2>
        ${renderRoleBadges(profile.roles)}
        ${profile.description ? html`<p class="text-sm opacity-80 mt-2">${profile.description}</p>` : nothing}
        ${profile.url ? html`<a href="${profile.url}" target="_blank" rel="noopener noreferrer" class="link link-primary text-sm mt-1 inline-block">${profile.url}</a>` : nothing}
        ${renderProfileDetails(profile, config)}
    </div>
</div>`, target);
}

export async function render(container, params, router) {
    const { signal } = params || {};
    const config = getConfig();

    if (params.id) {
        try {
            const profile = await apiGet(`/api/v1/user/profile/${params.id}`, {}, { signal });
            renderPublicProfile(profile, config, container);
        } catch (e) {
            if (isAbortError(e)) return;
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
        const profile = await apiGet('/api/v1/user/profile/me', {}, { signal });
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
                    <label class="flex items-center gap-3 py-1">
                        <span class="text-sm font-medium shrink-0 w-24">${t('user_profile.name_label')}</span>
                        <input type="text" name="name" class="input input-bordered flex-1"
                               value=${profile.name || ''}
                               placeholder=${t('user_profile.name_placeholder')} maxlength="255" />
                    </label>
                    <label class="flex items-center gap-3 py-1">
                        <span class="text-sm font-medium shrink-0 w-24">${t('user_profile.callsign_label')}</span>
                        <input type="text" name="callsign" class="input input-bordered flex-1"
                               value=${profile.callsign || ''}
                               placeholder=${t('user_profile.callsign_placeholder')} maxlength="20" />
                    </label>
                    <label class="flex items-center gap-3 py-1">
                        <span class="text-sm font-medium shrink-0 w-24">${t('user_profile.description_label')}</span>
                        <input type="text" name="description" class="input input-bordered flex-1"
                               value=${profile.description || ''}
                               placeholder=${t('user_profile.description_placeholder')} maxlength="500" />
                    </label>
                    <label class="flex items-center gap-3 py-1">
                        <span class="text-sm font-medium shrink-0 w-24">${t('user_profile.url_label')}</span>
                        <input type="url" name="url" class="input input-bordered flex-1"
                               value=${profile.url || ''}
                               placeholder=${t('user_profile.url_placeholder')} maxlength="2048" />
                    </label>
                    <button type="submit" class="btn btn-primary btn-sm">${t('user_profile.save_profile')}</button>
                </form>
                ${renderMemberSince(profile)}
            </div>
        </div>
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

        container.querySelector('#profile-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const body = {
                name: form.name.value.trim() || null,
                callsign: form.callsign.value.trim() || null,
                description: form.description.value.trim() || null,
                url: form.url.value.trim() || null,
            };
            try {
                await apiPut(profilePath, body);
                router.navigate('/profile?message=' + encodeURIComponent(t('user_profile.profile_updated')), true);
            } catch (err) {
                router.navigate('/profile?error=' + encodeURIComponent(err.message), true);
            }
        }, { signal: ac.signal });

        return () => ac.abort();

    } catch (e) {
        if (isAbortError(e)) return;
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
