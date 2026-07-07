/**
 * MeshCore Hub SPA - Main Application Entry Point
 *
 * Initializes i18n, the router, registers all page routes,
 * and handles navigation.
 */

import { Router } from './router.js';
import { isAbortError } from './api.js';
import { html, litRender, getConfig, hasRole, renderAuthSection } from './components.js';
import { loadLocale, t } from './i18n.js';
import { iconHome, iconDashboard, iconNodes, iconAdvertisements, iconMessages, iconPackets, iconMap, iconMembers, iconPage, iconChannel } from './icons.js';

// Page modules (lazy-loaded)
const pages = {
    home: () => import('./pages/home.js'),
    dashboard: () => import('./pages/dashboard.js'),
    nodes: () => import('./pages/nodes.js'),
    nodeDetail: () => import('./pages/node-detail.js'),
    messages: () => import('./pages/messages.js'),
    advertisements: () => import('./pages/advertisements.js'),
    packets: () => import('./pages/packets.js'),
    packetDetail: () => import('./pages/packet-detail.js'),
    packetGroupDetail: () => import('./pages/packet-group-detail.js'),
    map: () => import('./pages/map.js'),
    members: () => import('./pages/members.js'),
    channels: () => import('./pages/channels.js'),
    customPage: () => import('./pages/custom-page.js'),
    notFound: () => import('./pages/not-found.js'),
    profile: () => import('./pages/profile.js'),
    maintenance: () => import('./pages/maintenance.js'),
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
            // Navigating away cancels in-flight requests — not a real error.
            if (isAbortError(e)) return;
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

// Maintenance mode: every route renders the maintenance page and no
// API-backed page module is ever loaded.
const maintenanceMode = config.system_maintenance === true;

// Register routes (conditionally based on feature flags)
if (maintenanceMode) {
    const maintenanceHandler = pageHandler(pages.maintenance);
    router.addRoute('/', maintenanceHandler);
    router.setNotFound(maintenanceHandler);
} else {
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
if (features.channels !== false) {
    router.addRoute('/channels', pageHandler(pages.channels));
}
if (features.messages !== false) {
    router.addRoute('/messages', pageHandler(pages.messages));
}
if (features.advertisements !== false) {
    router.addRoute('/advertisements', pageHandler(pages.advertisements));
}
if (features.packets !== false) {
    router.addRoute('/packets', pageHandler(pages.packets));
    router.addRoute('/packets/hash/:hash', pageHandler(pages.packetGroupDetail));
    router.addRoute('/packets/:id', pageHandler(pages.packetDetail));
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

// Profile route (only register when OIDC enabled)
if (config.oidc_enabled) {
    router.addRoute('/profile', pageHandler(pages.profile));
    router.addRoute('/profile/:id', pageHandler(pages.profile));
}

// 404 handler
router.setNotFound(pageHandler(pages.notFound));
}

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
    };

    // Add feature-dependent titles
    if (features.dashboard !== false) titles['/dashboard'] = composePageTitle('entities.dashboard');
    if (features.nodes !== false) titles['/nodes'] = composePageTitle('entities.nodes');
    if (features.channels !== false) titles['/channels'] = composePageTitle('entities.channels');
    if (features.messages !== false) titles['/messages'] = composePageTitle('entities.messages');
    if (features.advertisements !== false) titles['/advertisements'] = composePageTitle('entities.advertisements');
    if (features.packets !== false) titles['/packets'] = composePageTitle('entities.packets');
    if (features.map !== false) titles['/map'] = composePageTitle('entities.map');
    if (features.members !== false) titles['/members'] = composePageTitle('entities.members');
    titles['/profile'] = composePageTitle('links.profile');

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

/**
 * Render the mobile navigation dropdown.
 * Populates the #mobile-nav container with nav items based on config features.
 * @param {Object} config - App configuration object
 */
function renderMobileNav(config) {
    const container = document.getElementById('mobile-nav');
    if (!container) return;

    const features = config.features || {};
    const customPages = config.custom_pages || [];

    const items = [];

    items.push(html`<li><a href="/" data-nav-link>${iconHome('h-5 w-5')} ${t('entities.home')}</a></li>`);

    if (features.dashboard !== false) {
        items.push(html`<li><a href="/dashboard" data-nav-link>${iconDashboard('h-5 w-5 nav-icon-dashboard')} ${t('entities.dashboard')}</a></li>`);
    }
    if (features.nodes !== false) {
        items.push(html`<li><a href="/nodes" data-nav-link>${iconNodes('h-5 w-5 nav-icon-nodes')} ${t('entities.nodes')}</a></li>`);
    }
    if (features.advertisements !== false) {
        items.push(html`<li><a href="/advertisements" data-nav-link>${iconAdvertisements('h-5 w-5 nav-icon-adverts')} ${t('entities.advertisements')}</a></li>`);
    }
    if (features.channels !== false) {
        items.push(html`<li><a href="/channels" data-nav-link>${iconChannel('h-5 w-5')} ${t('entities.channels')}</a></li>`);
    }
    if (features.messages !== false) {
        items.push(html`<li><a href="/messages" data-nav-link>${iconMessages('h-5 w-5 nav-icon-messages')} ${t('entities.messages')}</a></li>`);
    }
    if (features.packets !== false) {
        items.push(html`<li><a href="/packets" data-nav-link>${iconPackets('h-5 w-5 nav-icon-packets')} ${t('entities.packets')}</a></li>`);
    }
    if (features.map !== false) {
        items.push(html`<li><a href="/map" data-nav-link>${iconMap('h-5 w-5 nav-icon-map')} ${t('entities.map')}</a></li>`);
    }
    if (features.members !== false) {
        items.push(html`<li><a href="/members" data-nav-link>${iconMembers('h-5 w-5 nav-icon-members')} ${t('entities.members')}</a></li>`);
    }

    if (features.pages !== false && customPages.length > 0) {
        for (const page of customPages) {
            items.push(html`<li><a href=${page.url} data-nav-link>${iconPage('h-5 w-5')} ${page.title}</a></li>`);
        }
    }

    litRender(html`${items}`, container);
}

// Load locale then start the router
const locale = localStorage.getItem('meshcore-locale') || config.locale || 'en';
await loadLocale(locale);

// Legacy cleanup: remove the old per-observer localStorage key so stale public
// keys are never misread as area codes by the new area-based filter.
try { localStorage.removeItem('meshcore-observers-disabled'); } catch {}

// Render auth section in navbar (after translations are loaded)
const authSection = document.getElementById('auth-section');
renderAuthSection(authSection, config);

// Render mobile nav (after translations are loaded)
renderMobileNav(config);

router.start();
