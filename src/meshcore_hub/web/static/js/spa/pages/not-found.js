import { html, litRender } from '../components.js';
import { iconHome, iconNodes } from '../icons.js';

export async function render(container, params, router) {
    litRender(html`
<div class="hero min-h-[60vh]">
    <div class="hero-content text-center">
        <div class="max-w-md">
            <div class="text-9xl font-bold text-primary opacity-20">404</div>
            <h1 class="text-4xl font-bold -mt-8">Page Not Found</h1>
            <p class="py-6 text-base-content/70">
                The page you're looking for doesn't exist or has been moved.
            </p>
            <div class="flex gap-4 justify-center">
                <a href="/" class="btn btn-primary">
                    ${iconHome('h-5 w-5 mr-2')}
                    Go Home
                </a>
                <a href="/nodes" class="btn btn-outline">
                    ${iconNodes('h-5 w-5 mr-2')}
                    Browse Nodes
                </a>
            </div>
        </div>
    </div>
</div>`, container);
}
