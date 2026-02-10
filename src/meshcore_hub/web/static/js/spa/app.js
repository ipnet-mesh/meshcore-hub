/**
 * MeshCore Hub SPA - Main Application Entry Point
 *
 * Initializes the router, registers all page routes, and handles navigation.
 */

import { Router } from './router.js';
import { getConfig } from './components.js';

// Page modules (lazy-loaded)
const pages = {
    home: () => import('./pages/home.js'),
    dashboard: () => import('./pages/dashboard.js'),
    nodes: () => import('./pages/nodes.js'),
    nodeDetail: () => import('./pages/node-detail.js'),
    messages: () => import('./pages/messages.js'),
    advertisements: () => import('./pages/advertisements.js'),
    map: () => import('./pages/map.js'),
    members: () => import('./pages/members.js'),
    customPage: () => import('./pages/custom-page.js'),
    notFound: () => import('./pages/not-found.js'),
    adminIndex: () => import('./pages/admin/index.js'),
    adminNodeTags: () => import('./pages/admin/node-tags.js'),
    adminMembers: () => import('./pages/admin/members.js'),
};

// Main app container
const appContainer = document.getElementById('app');
const router = new Router();

/**
 * Create a route handler that lazy-loads a page module and calls its render function.
 * @param {Function} loader - Module loader function
 * @returns {Function} Route handler
 */
function pageHandler(loader) {
    return async (params) => {
        try {
            const module = await loader();
            return await module.render(appContainer, params, router);
        } catch (e) {
            console.error('Page load error:', e);
            appContainer.innerHTML = `
                <div class="flex flex-col items-center justify-center py-20">
                    <h1 class="text-4xl font-bold mb-4">Error</h1>
                    <p class="text-lg opacity-70 mb-6">Failed to load page</p>
                    <p class="text-sm opacity-50 mb-6">${e.message || 'Unknown error'}</p>
                    <a href="/" class="btn btn-primary">Go Home</a>
                </div>`;
        }
    };
}

// Register routes
router.addRoute('/', pageHandler(pages.home));
router.addRoute('/dashboard', pageHandler(pages.dashboard));
router.addRoute('/nodes', pageHandler(pages.nodes));
router.addRoute('/nodes/:publicKey', pageHandler(pages.nodeDetail));
router.addRoute('/n/:prefix', async (params) => {
    // Short link redirect
    router.navigate(`/nodes/${params.prefix}`, true);
});
router.addRoute('/messages', pageHandler(pages.messages));
router.addRoute('/advertisements', pageHandler(pages.advertisements));
router.addRoute('/map', pageHandler(pages.map));
router.addRoute('/members', pageHandler(pages.members));
router.addRoute('/pages/:slug', pageHandler(pages.customPage));

// Admin routes
router.addRoute('/a', pageHandler(pages.adminIndex));
router.addRoute('/a/', pageHandler(pages.adminIndex));
router.addRoute('/a/node-tags', pageHandler(pages.adminNodeTags));
router.addRoute('/a/members', pageHandler(pages.adminMembers));

// 404 handler
router.setNotFound(pageHandler(pages.notFound));

/**
 * Update the active state of navigation links.
 * @param {string} pathname - Current URL path
 */
function updateNavActiveState(pathname) {
    document.querySelectorAll('[data-nav-link]').forEach(link => {
        const href = link.getAttribute('href');
        let isActive = false;

        if (href === '/') {
            isActive = pathname === '/';
        } else if (href === '/nodes') {
            isActive = pathname.startsWith('/nodes');
        } else {
            isActive = pathname === href || pathname.startsWith(href + '/');
        }

        if (isActive) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // Close mobile dropdown if open (DaisyUI dropdowns stay open while focused)
    if (document.activeElement?.closest('.dropdown')) {
        document.activeElement.blur();
    }
}

/**
 * Update the page title based on the current route.
 * @param {string} pathname
 */
function updatePageTitle(pathname) {
    const config = getConfig();
    const networkName = config.network_name || 'MeshCore Network';
    const titles = {
        '/': networkName,
        '/dashboard': `Dashboard - ${networkName}`,
        '/nodes': `Nodes - ${networkName}`,
        '/messages': `Messages - ${networkName}`,
        '/advertisements': `Advertisements - ${networkName}`,
        '/map': `Map - ${networkName}`,
        '/members': `Members - ${networkName}`,
        '/a': `Admin - ${networkName}`,
        '/a/': `Admin - ${networkName}`,
        '/a/node-tags': `Node Tags - Admin - ${networkName}`,
        '/a/members': `Members - Admin - ${networkName}`,
    };

    if (titles[pathname]) {
        document.title = titles[pathname];
    } else if (pathname.startsWith('/nodes/')) {
        document.title = `Node Detail - ${networkName}`;
    } else if (pathname.startsWith('/pages/')) {
        // Custom pages set their own title in the page module
        document.title = networkName;
    } else {
        document.title = networkName;
    }
}

// Set up navigation callback
router.onNavigate((pathname) => {
    updateNavActiveState(pathname);
    updatePageTitle(pathname);
});

// Start the router when DOM is ready
router.start();
