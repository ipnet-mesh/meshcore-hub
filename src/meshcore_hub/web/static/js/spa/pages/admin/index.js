import { html, litRender, getConfig, errorAlert } from '../../components.js';
import { iconLock, iconUsers, iconTag } from '../../icons.js';

export async function render(container, params, router) {
    try {
        const config = getConfig();

        if (!config.admin_enabled) {
            litRender(html`
<div class="flex flex-col items-center justify-center py-20">
    ${iconLock('h-16 w-16 opacity-30 mb-4')}
    <h1 class="text-3xl font-bold mb-2">Access Denied</h1>
    <p class="opacity-70">The admin interface is not enabled.</p>
    <p class="text-sm opacity-50 mt-2">Set <code>WEB_ADMIN_ENABLED=true</code> to enable admin features.</p>
    <a href="/" class="btn btn-primary mt-6">Go Home</a>
</div>`, container);
            return;
        }

        litRender(html`
<div class="flex items-center justify-between mb-4">
    <div>
        <h1 class="text-3xl font-bold">Admin</h1>
        <div class="text-sm breadcrumbs">
            <ul>
                <li><a href="/">Home</a></li>
                <li>Admin</li>
            </ul>
        </div>
    </div>
    <a href="/oauth2/sign_out" target="_blank" class="btn btn-outline btn-sm">Sign Out</a>
</div>

<div class="flex flex-wrap items-center gap-4 text-sm opacity-70 mb-6">
    <span class="flex items-center gap-1.5">
        Welcome to the admin panel.
    </span>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    <a href="/a/members" class="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
        <div class="card-body">
            <h2 class="card-title">
                ${iconUsers('h-6 w-6')}
                Members
            </h2>
            <p>Manage network members and operators.</p>
        </div>
    </a>
    <a href="/a/node-tags" class="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
        <div class="card-body">
            <h2 class="card-title">
                ${iconTag('h-6 w-6')}
                Node Tags
            </h2>
            <p>Manage custom tags and metadata for network nodes.</p>
        </div>
    </a>
</div>`, container);

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load admin page'), container);
    }
}
