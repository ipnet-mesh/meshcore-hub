import { html, litRender, unsafeHTML, getConfig, errorAlert, t } from '../../components.js';
import { iconLock, iconUsers, iconTag } from '../../icons.js';

export async function render(container, params, router) {
    try {
        const config = getConfig();

        if (!config.admin_enabled) {
            litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    ${iconLock('h-16 w-16 opacity-30 mb-4')}
    <h1 class="text-3xl font-bold mb-2">${t('admin.access_denied')}</h1>
    <p class="opacity-70">${t('admin.admin_not_enabled')}</p>
    <p class="text-sm opacity-50 mt-2">${unsafeHTML(t('admin.admin_enable_hint'))}</p>
    <a href="/" class="btn btn-primary mt-6">${t('common.go_home')}</a>
</div>`, container);
            return;
        }

        if (!config.is_authenticated) {
            litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    ${iconLock('h-16 w-16 opacity-30 mb-4')}
    <h1 class="text-3xl font-bold mb-2">${t('admin.auth_required')}</h1>
    <p class="opacity-70">${t('admin.auth_required_description')}</p>
    <a href="/oauth2/start?rd=${encodeURIComponent(window.location.pathname)}" class="btn btn-primary mt-6">${t('common.sign_in')}</a>
</div>`, container);
            return;
        }

        litRender(html`
<div class="flex items-center justify-between mb-4">
    <div>
        <h1 class="text-3xl font-bold">${t('entities.admin')}</h1>
        <div class="text-sm breadcrumbs">
            <ul>
                <li><a href="/">${t('nav.home')}</a></li>
                <li>${t('nav.admin')}</li>
            </ul>
        </div>
    </div>
    <a href="/oauth2/sign_out" target="_blank" class="btn btn-outline btn-sm">${t('common.sign_out')}</a>
</div>

<div class="flex flex-wrap items-center gap-4 text-sm opacity-70 mb-6">
    <span class="flex items-center gap-1.5">
        ${t('admin.welcome')}
    </span>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    <a href="/a/members" class="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
        <div class="card-body">
            <h2 class="card-title">
                ${iconUsers('h-6 w-6')}
                ${t('admin.members_title')}
            </h2>
            <p>${t('admin.members_description')}</p>
        </div>
    </a>
    <a href="/a/node-tags" class="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
        <div class="card-body">
            <h2 class="card-title">
                ${iconTag('h-6 w-6')}
                ${t('admin.node_tags_title')}
            </h2>
            <p>${t('admin.node_tags_description')}</p>
        </div>
    </a>
</div>`, container);

    } catch (e) {
        litRender(errorAlert(e.message || t('common.failed_to_load_page')), container);
    }
}
