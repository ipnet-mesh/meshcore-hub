import { apiGet } from '../api.js';
import { html, litRender, unsafeHTML, getConfig, errorAlert, t } from '../components.js';

export async function render(container, params, router) {
    try {
        const page = await apiGet('/spa/pages/' + encodeURIComponent(params.slug));

        const config = getConfig();
        const networkName = config.network_name || 'MeshCore Network';
        document.title = `${page.title} - ${networkName}`;

        litRender(html`
<div class="max-w-4xl mx-auto">
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body prose prose-lg max-w-none">
            ${unsafeHTML(page.content_html)}
        </div>
    </div>
</div>`, container);

    } catch (e) {
        if (e.message && e.message.includes('404')) {
            litRender(errorAlert(t('common.page_not_found')), container);
        } else {
            litRender(errorAlert(e.message || t('custom_page.failed_to_load')), container);
        }
    }
}
