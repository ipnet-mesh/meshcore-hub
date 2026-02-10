/**
 * MeshCore Hub SPA - Client-Side Router
 *
 * Simple History API based router with parameterized routes.
 */

export class Router {
    constructor() {
        this._routes = [];
        this._notFoundHandler = null;
        this._currentCleanup = null;
        this._onNavigate = null;
    }

    /**
     * Register a route.
     * @param {string} path - URL pattern (e.g., '/nodes/:publicKey')
     * @param {Function} handler - async function(params) where params includes route params and query
     */
    addRoute(path, handler) {
        const paramNames = [];
        const regexStr = path
            .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')  // escape regex chars
            .replace(/:([a-zA-Z_]+)/g, (_, name) => {
                paramNames.push(name);
                return '([^/]+)';
            });
        this._routes.push({
            pattern: new RegExp('^' + regexStr + '$'),
            paramNames,
            handler,
            path,
        });
    }

    /**
     * Set the 404 handler.
     * @param {Function} handler - async function(params)
     */
    setNotFound(handler) {
        this._notFoundHandler = handler;
    }

    /**
     * Set a callback to run on every navigation (for updating navbar, etc.)
     * @param {Function} fn - function(pathname)
     */
    onNavigate(fn) {
        this._onNavigate = fn;
    }

    /**
     * Navigate to a URL.
     * @param {string} url - URL path with optional query string
     * @param {boolean} [replace=false] - Use replaceState instead of pushState
     */
    navigate(url, replace = false) {
        // Skip if already on this exact URL
        const current = window.location.pathname + window.location.search;
        if (url === current && !replace) return;

        if (replace) {
            history.replaceState(null, '', url);
        } else {
            history.pushState(null, '', url);
        }
        this._handleRoute();
    }

    /**
     * Match a pathname against registered routes.
     * @param {string} pathname
     * @returns {{ handler: Function, params: Object } | null}
     */
    _match(pathname) {
        for (const route of this._routes) {
            const match = pathname.match(route.pattern);
            if (match) {
                const params = {};
                route.paramNames.forEach((name, i) => {
                    params[name] = decodeURIComponent(match[i + 1]);
                });
                return { handler: route.handler, params };
            }
        }
        return null;
    }

    /**
     * Handle the current URL.
     */
    async _handleRoute() {
        // Clean up previous page
        if (this._currentCleanup) {
            try { this._currentCleanup(); } catch (e) { /* ignore */ }
            this._currentCleanup = null;
        }

        const pathname = window.location.pathname;
        const query = Object.fromEntries(new URLSearchParams(window.location.search));

        // Notify navigation listener
        if (this._onNavigate) {
            this._onNavigate(pathname);
        }

        // Show navbar loading indicator
        const loader = document.getElementById('nav-loading');
        if (loader) loader.classList.remove('hidden');

        try {
            const result = this._match(pathname);
            if (result) {
                const cleanup = await result.handler({ ...result.params, query });
                if (typeof cleanup === 'function') {
                    this._currentCleanup = cleanup;
                }
            } else if (this._notFoundHandler) {
                await this._notFoundHandler({ query });
            }
        } finally {
            if (loader) loader.classList.add('hidden');
        }

        // Scroll to top on navigation
        window.scrollTo(0, 0);
    }

    /**
     * Start the router - listen for events and handle initial route.
     */
    start() {
        // Handle browser back/forward
        window.addEventListener('popstate', () => this._handleRoute());

        // Intercept link clicks for SPA navigation
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[href]');
            if (!link) return;

            const href = link.getAttribute('href');

            // Skip external links, anchors, downloads, new tabs
            if (!href || !href.startsWith('/') || href.startsWith('//')) return;
            if (link.hasAttribute('download') || link.target === '_blank') return;

            // Skip non-SPA paths (static files, API, media, OAuth, SEO)
            if (href.startsWith('/static/') || href.startsWith('/media/') ||
                href.startsWith('/api/') || href.startsWith('/oauth2/') ||
                href.startsWith('/health') || href === '/robots.txt' ||
                href === '/sitemap.xml') return;

            // Skip mailto and tel links
            if (href.startsWith('mailto:') || href.startsWith('tel:')) return;

            e.preventDefault();
            this.navigate(href);
        });

        // Handle initial route
        this._handleRoute();
    }
}
