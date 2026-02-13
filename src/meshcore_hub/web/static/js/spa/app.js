/**
 * MeshCore Hub SPA - Main Application Entry Point
 *
 * Initializes i18n, the router, registers all page routes,
 * and handles navigation.
 */

import { Router } from './router.js';
import { getConfig } from './components.js';
import { loadLocale, t } from './i18n.js';

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

// Read feature flags from config
const config = getConfig();
const features = config.features || {};

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
                    <h1 class="text-4xl font-bold mb-4">${t('common.error')}</h1>
                    <p class="text-lg opacity-70 mb-6">${t('common.failed_to_load_page')}</p>
                    <p class="text-sm opacity-50 mb-6">${e.message || 'Unknown error'}</p>
                    <a href="/" class="btn btn-primary">${t('common.go_home')}</a>
                </div>`;
        }
    };
}

// Register routes (conditionally based on feature flags)
router.addRoute('/', pageHandler(pages.home));

if (features.dashboard !== false) {
    router.addRoute('/dashboard', pageHandler(pages.dashboard));
}
if (features.nodes !== false) {
    router.addRoute('/nodes', pageHandler(pages.nodes));
    router.addRoute('/nodes/:publicKey', pageHandler(pages.nodeDetail));
    router.addRoute('/n/:prefix', async (params) => {
        // Short link redirect
        router.navigate(`/nodes/${params.prefix}`, true);
    });
}
if (features.messages !== false) {
    router.addRoute('/messages', pageHandler(pages.messages));
}
if (features.advertisements !== false) {
    router.addRoute('/advertisements', pageHandler(pages.advertisements));
}
if (features.map !== false) {
    router.addRoute('/map', pageHandler(pages.map));
}
if (features.members !== false) {
    router.addRoute('/members', pageHandler(pages.members));
}
if (features.pages !== false) {
    router.addRoute('/pages/:slug', pageHandler(pages.customPage));
}

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
 * Compose a page title from entity name and network name.
 * @param {string} entityKey - Translation key for entity (e.g., 'entities.dashboard')
 * @returns {string}
 */
function composePageTitle(entityKey) {
    const networkName = config.network_name || 'MeshCore Network';
    const entity = t(entityKey);
    return `${entity} - ${networkName}`;
}

/**
 * Update the page title based on the current route.
 * @param {string} pathname
 */
function updatePageTitle(pathname) {
    const networkName = config.network_name || 'MeshCore Network';
    const titles = {
        '/': networkName,
        '/a': composePageTitle('entities.admin'),
        '/a/': composePageTitle('entities.admin'),
        '/a/node-tags': `${t('entities.tags')} - ${t('entities.admin')} - ${networkName}`,
        '/a/members': `${t('entities.members')} - ${t('entities.admin')} - ${networkName}`,
    };

    // Add feature-dependent titles
    if (features.dashboard !== false) titles['/dashboard'] = composePageTitle('entities.dashboard');
    if (features.nodes !== false) titles['/nodes'] = composePageTitle('entities.nodes');
    if (features.messages !== false) titles['/messages'] = composePageTitle('entities.messages');
    if (features.advertisements !== false) titles['/advertisements'] = composePageTitle('entities.advertisements');
    if (features.map !== false) titles['/map'] = composePageTitle('entities.map');
    if (features.members !== false) titles['/members'] = composePageTitle('entities.members');

    if (titles[pathname]) {
        document.title = titles[pathname];
    } else if (pathname.startsWith('/nodes/')) {
        document.title = composePageTitle('entities.node_detail');
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

// Load locale then start the router
const locale = localStorage.getItem('meshcore-locale') || config.locale || 'en';
await loadLocale(locale);
router.start();
