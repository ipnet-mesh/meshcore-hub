import { html, litRender, t } from '../components.js';
import { iconHome, iconNodes } from '../icons.js';

export async function render(container, params, router) {
    litRender(html`
<div class="hero min-h-[60vh]">
    <div class="hero-content text-center">
        <div class="max-w-md">
            <div class="text-9xl font-bold text-primary opacity-20">404</div>
            <h1 class="text-4xl font-bold -mt-8">${t('common.page_not_found')}</h1>
            <p class="py-6 text-base-content/70">
                ${t('not_found.description')}
            </p>
            <div class="flex gap-4 justify-center">
                <a href="/" class="btn btn-primary">
                    ${iconHome('h-5 w-5 mr-2')}
                    ${t('common.go_home')}
                </a>
                <a href="/nodes" class="btn btn-outline">
                    ${iconNodes('h-5 w-5 mr-2')}
                    ${t('common.view_entity', { entity: t('entities.nodes') })}
                </a>
            </div>
        </div>
    </div>
</div>`, container);
}
