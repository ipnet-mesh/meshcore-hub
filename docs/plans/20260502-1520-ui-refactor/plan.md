# UI Frontend Refactor — Inline SVGs & Template Extraction

**Date:** 2026-05-02
**Status:** Draft

## Overview

Refactor the SPA frontend to eliminate inline SVG markup and extract large lit-html templates into reusable functions. The codebase already has a well-structured `icons.js` module (25 lit-html icon functions) and a `components.js` module (shared UI functions), but they are inconsistently used — 13 inline SVG instances exist across the codebase, 7 of which duplicate existing icons. Additionally, two page files have monolithic render functions exceeding 100 lines, and three list pages duplicate a nearly identical filter card pattern.

No API changes. No CSS changes needed (CSS already uses `app.css` custom properties cleanly). No build changes. Pure JavaScript refactoring.

## Decisions

1. **All SVGs must use `icons.js` lit-html functions** — No raw `<svg>` strings anywhere. All icon functions accept a `cls` parameter for sizing, enabling consistent `class=${cls}` usage.

2. **New icon additions OK** — Add `iconSettings` (gear/cog), `iconLogout` (door-arrow), `iconPause`, `iconPlay` to `icons.js`. The pause/play icons use 20x20 viewBox with `fill` (Tailwind-style small icons, matching their usage context in the auto-refresh button). Consider prefix naming or a separate collection if future 20x20 icons accumulate.

3. **Convert `renderAuthSection()` to lit-html** — Currently uses `innerHTML =` with a 60-line raw HTML template string and three raw-string SVG helpers. Rewrite using lit-html `litRender()` and `html\`...\``, using `icons.js` functions for all SVGs.

4. **Extract filter form pattern and adopt in pages** — Three pages (nodes, ads, messages) share a nearly identical filter card. Extract a `renderFilterCard()` component into `components.js` that accepts field definitions, basePath, and a navigate function. Retrofit all three pages to use it.

5. **Extract stat card pattern** — `home.js` and `dashboard.js` duplicate the same stat-card template structure. Extract `renderStatCard()` into `components.js`.

6. **Extract modal dialogs from node-tags.js** — Five `<dialog>` modals (edit, move, delete, copy-all, delete-all) are defined inline across 127 lines. Extract each to a separate render function.

7. **Extract home.js hero + nav sections** — The 123-line monolithic `render()` function in `home.js` should be split into `renderHeroSection()`, `renderStatsPanel()`, and `renderActivityChart()`.

8. **No backend changes** — This is a pure frontend refactor. No Python, schema, or template changes.

## Terminology

| Term | Meaning |
|---|---|
| Lit-html | JavaScript tagged template library (`html\`...\``) used for all SPA rendering |
| `icons.js` | Module exporting icon functions that return lit-html `TemplateResult` with configurable CSS classes |
| `components.js` | Module exporting shared UI components (alerts, pagination, etc.) and utility functions |
| Raw HTML SVG | An SVG defined as a plain string (e.g., `'<svg>...</svg>'`) rather than via a lit-html `html\`...\`` template or `icons.js` function |
| Inline SVG | An `<svg>` element directly inside a lit-html `html\`...\`` template literal, not using an `icons.js` function |
| Filter card pattern | A `<div class="card shadow mb-6 panel-solid">` containing a filter form with selects, submit, and clear buttons |

## Current State

### File Size Overview

| File | Lines | Key Concern |
|---|---|---|
| `icons.js` | 107 | Complete; missing 4 icons |
| `components.js` | 667 | 3 alerts with duplicate inline SVGs; 3 raw-string SVG helpers; large `renderAuthSection` |
| `auto-refresh.js` | 87 | 2 inline SVGs (pause/play, 20x20 fill) |
| `home.js` | 209 | **123-line monolithic render()** |
| `dashboard.js` | 252 | 96-line render(); duplicate stat cards from home.js |
| `nodes.js` | 207 | Filter form pattern duplicate |
| `node-detail.js` | 358 | Well-factored with sub-renderers |
| `messages.js` | 375 | Filter form pattern duplicate; dedupe logic (62 lines, non-UI) |
| `advertisements.js` | 251 | Filter form pattern duplicate |
| `map.js` | 349 | 81-line filter+map+legend template |
| `members.js` | 92 | Clean |
| `profile.js` | 174 | Clean |
| `admin/index.js` | 65 | Clean |
| `admin/node-tags.js` | 526 | **5 inline SVGs (all duplicates); 127 lines of modal dialogs** |
| `app.js` | 195 | Clean |
| `router.js` | 163 | Clean |
| `api.js` | 114 | Clean |
| `i18n.js` | 76 | Clean |
| `charts.js` | 231 | Clean |

### Inline SVG Inventory — 13 Instances, 9 Unique Icons

#### Already exists in `icons.js` (9 instances, 5 unique)

| # | File | Line | SVG | Should Use |
|---|------|------|-----|------------|
| 1 | `components.js:errorAlert()` | 371 | X-circle | `iconError('stroke-current shrink-0 h-6 w-6')` |
| 2 | `components.js:infoAlert()` | 383 | Info circle-i | `iconInfo('stroke-current shrink-0 h-6 w-6')` |
| 3 | `components.js:successAlert()` | 395 | Check-circle | `iconSuccess('stroke-current shrink-0 h-6 w-6')` |
| 4 | `components.js:_svgUser()` | 596 | Person icon (raw string) | `iconUser('h-4 w-4')` — requires lit-html usage |
| 5 | `admin/node-tags.js` | 198 | Warning triangle | `iconAlert('stroke-current shrink-0 h-6 w-6')` |
| 6 | `admin/node-tags.js` | 216 | Warning triangle | `iconAlert(...)` |
| 7 | `admin/node-tags.js` | 246 | Info circle | `iconInfo('stroke-current shrink-0 h-6 w-6')` |
| 8 | `admin/node-tags.js` | 265 | Warning triangle | `iconAlert(...)` |
| 9 | `admin/node-tags.js` | 279 | Warning triangle | `iconAlert(...)` |

#### Missing from `icons.js` (4 instances, 4 unique)

| # | File | Line | SVG | New Function Name |
|---|------|------|-----|------------------|
| 1 | `components.js:_svgSettings()` | 600 | Gear/cog (24x24 stroke) | `iconSettings` |
| 2 | `components.js:_svgLogout()` | 604 | Door-arrow-out (24x24 stroke) | `iconLogout` |
| 3 | `auto-refresh.js` | 32 | Pause bars (20x20 fill) | `iconPause` |
| 4 | `auto-refresh.js` | 33 | Play triangle (20x20 fill) | `iconPlay` |

### Large Template Extraction Candidates

#### High Priority (100+ lines of monolithic rendering)

| File | Lines | Content |
|------|-------|---------|
| **`home.js`** | 69–191 (123 lines) | Hero/logo, nav buttons, stats panel, info card, activity chart — extract to `renderHeroSection`, `renderStatsPanel`, `renderActivityChart` |
| **`admin/node-tags.js`** | 149–275 (127 lines) | Five `<dialog>` modals (edit, move, delete, copy-all, delete-all) — extract each to separate render function |

#### Medium Priority (shared patterns)

| Pattern | Files | Description |
|---------|-------|-------------|
| **Filter card** | `nodes.js` (L128–170), `messages.js` (L309–336), `advertisements.js` (L182–213) | Nearly identical filter form in a card — extract to `renderFilterCard()` in `components.js` |
| **Stat card** | `home.js` (L111–142), `dashboard.js` (L141–169) | Same stat-card pattern (icon, title, value, description) — extract to `renderStatCard()` in `components.js` |
| **Chart cards** | `dashboard.js` (L172–214) | Chart containers with canvas elements — extract to `renderChartCard()` |

---

## Implementation

### Phase 1: Add Missing Icons to `icons.js`

**File:** `src/meshcore_hub/web/static/js/spa/icons.js`

Add 4 new icon functions at the end of the file (after L107):

```javascript
// Phase 1 additions:

export function iconSettings(cls = 'h-5 w-5') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>`;
}

export function iconLogout(cls = 'h-5 w-5') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" /></svg>`;
}

export function iconPause(cls = 'w-4 h-4') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} viewBox="0 0 20 20" fill="currentColor"><path d="M5.75 3a.75.75 0 0 0-.75.75v12.5c0 .414.336.75.75.75h1.5a.75.75 0 0 0 .75-.75V3.75A.75.75 0 0 0 7.25 3h-1.5ZM12.75 3a.75.75 0 0 0-.75.75v12.5c0 .414.336.75.75.75h1.5a.75.75 0 0 0 .75-.75V3.75a.75.75 0 0 0-.75-.75h-1.5Z" /></svg>`;
}

export function iconPlay(cls = 'w-4 h-4') {
    return html`<svg xmlns="http://www.w3.org/2000/svg" class=${cls} viewBox="0 0 20 20" fill="currentColor"><path d="M6.3 2.84A1.5 1.5 0 0 0 4 4.11v11.78a1.5 1.5 0 0 0 2.3 1.27l9.344-5.891a1.5 1.5 0 0 0 0-2.538L6.3 2.84Z" /></svg>`;
}
```

### Phase 2: Replace Inline SVGs in `components.js`

**File:** `src/meshcore_hub/web/static/js/spa/components.js`

#### 2.1 Update import from `icons.js`

Change line 11 from:
```javascript
import { iconAlert } from './icons.js';
```
to:
```javascript
import { iconAlert, iconError, iconInfo, iconSuccess, iconUser, iconSettings, iconLogout } from './icons.js';
```

#### 2.2 Replace inline SVGs in alert functions

**`errorAlert()` (L369–374)** — replace inline SVG on L371:
```javascript
// Before (L371):
<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
// After:
${iconError('stroke-current shrink-0 h-6 w-6')}
```

**`infoAlert()` (L381–386)** — replace inline SVG on L383:
```javascript
// Before (L383):
<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
// After:
${iconInfo('stroke-current shrink-0 h-6 w-6')}
```

**`successAlert()` (L393–398)** — replace inline SVG on L395:
```javascript
// Before (L395):
<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
// After:
${iconSuccess('stroke-current shrink-0 h-6 w-6')}
```

#### 2.3 Remove raw-string SVG helpers and convert `renderAuthSection()` to lit-html

Remove `_svgUser()` (L595–597), `_svgSettings()` (L599–601), `_svgLogout()` (L603–605).

Rewrite `renderAuthSection()` to use `litRender()` with `html\`...\`` instead of `innerHTML =`. The DaisyUI dropdown (CSS-based via `dropdown` class + `tabindex` attributes) works identically with lit-html rendered DOM since no JS event handlers are required. For the login case, use a standard `<a>` element. For the logged-in case, render the DaisyUI dropdown structure:

```javascript
export function renderAuthSection(container, config) {
    if (!container) return;
    if (!config.oidc_enabled) {
        litRender(nothing, container);
        return;
    }

    const user = config.user;
    if (!user) {
        litRender(html`
            <a href="/auth/login" class="btn btn-sm btn-outline">${t('auth.login')}</a>
        `, container);
        return;
    }

    const displayName = user.name || user.email || 'User';
    const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    const pictureHtml = user.picture
        ? html`<img src=${user.picture} alt=${displayName} class="w-8 h-8 rounded-full" />`
        : html`<span class="text-sm font-bold">${initials}</span>`;

    const roleBadges = (config.roles || []).map(r => {
        const key = `auth.role_${r}`;
        const label = t(key);
        const name = label !== key ? label : r;
        return html`<span class="badge badge-primary badge-xs">${name}</span>`;
    });

    const adminItem = hasRole('admin')
        ? html`<li><a href="/admin/">${iconSettings('h-4 w-4')} ${t('entities.admin')}</a></li>`
        : nothing;

    const profileItem = html`<li><a href="/profile">${iconUser('h-4 w-4')} ${t('links.profile')}</a></li>`;

    const debugId = config.debug && user.sub
        ? html`<span class="text-xs opacity-40 font-mono">${user.sub}</span>`
        : nothing;

    litRender(html`
        <div class="dropdown dropdown-end">
            <div tabindex="0" role="button" class="btn btn-ghost btn-circle btn-sm avatar">
                ${pictureHtml}
            </div>
            <ul tabindex="0" class="dropdown-content menu menu-sm z-[1] p-2 shadow bg-base-100 rounded-box w-52 mt-3">
                <li class="menu-title">
                    <div class="flex flex-col gap-1">
                        <span class="font-medium">${displayName}</span>
                        ${debugId}
                        ${roleBadges.length > 0 ? html`<div class="flex flex-wrap gap-1">${roleBadges}</div>` : nothing}
                    </div>
                </li>
                <hr class="my-1 opacity-20">
                ${adminItem}
                ${profileItem}
                <li><a href="/auth/logout">${iconLogout('h-4 w-4')} ${t('auth.logout')}</a></li>
            </ul>
        </div>
    `, container);
}
```

Key differences from the `innerHTML` version:
- Uses `litRender(..., container)` — clearing + rendering in one call (no manual `innerHTML = ''` needed)
- Uses lit-html conditionals (`nothing`, ternary) instead of string concatenation
- Uses `iconUser`, `iconSettings`, `iconLogout` from `icons.js` instead of raw SVG strings
- DaisyUI dropdown: identical DOM structure, CSS `:focus-within` behavior works the same with lit-html rendered content

### Phase 3: Replace Inline SVGs in `auto-refresh.js`

**File:** `src/meshcore_hub/web/static/js/spa/auto-refresh.js`

#### 3.1 Add import

Add at top of file:
```javascript
import { iconPause, iconPlay, iconInfo } from './icons.js';
```

#### 3.2 Replace inline SVGs

Lines 32–33 currently define inline SVG strings in lit-html templates. Replace with icon functions:

```javascript
// Before (L32-33):
const pauseIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4"><path d="M5.75 3a.75.75 0 0 0-.75.75v12.5c0 .414.336.75.75.75h1.5a.75.75 0 0 0 .75-.75V3.75A.75.75 0 0 0 7.25 3h-1.5ZM12.75 3a.75.75 0 0 0-.75.75v12.5c0 .414.336.75.75.75h1.5a.75.75 0 0 0 .75-.75V3.75a.75.75 0 0 0-.75-.75h-1.5Z" /></svg>`;
const playIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4"><path d="M6.3 2.84A1.5 1.5 0 0 0 4 4.11v11.78a1.5 1.5 0 0 0 2.3 1.27l9.344-5.891a1.5 1.5 0 0 0 0-2.538L6.3 2.84Z" /></svg>`;

// After:
const pauseIcon = iconPause('w-4 h-4');
const playIcon = iconPlay('w-4 h-4');
```

### Phase 4: Replace Inline SVGs in `admin/node-tags.js`

**File:** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`

#### 4.1 Update import

Add `iconAlert, iconInfo` to imports from `../../icons.js`.

#### 4.2 Replace 5 inline SVG instances

| Line | Replace with |
|------|-------------|
| 198 | `${iconAlert('stroke-current shrink-0 h-6 w-6')}` (in #moveModal alert) |
| 216 | `${iconAlert('stroke-current shrink-0 h-6 w-6')}` (in #deleteModal alert) |
| 246 | `${iconInfo('stroke-current shrink-0 h-6 w-6')}` (in #copyAllModal alert) |
| 265 | `${iconAlert('stroke-current shrink-0 h-6 w-6')}` (in #deleteAllModal alert) |
| 279 | `${iconAlert('stroke-current shrink-0 h-6 w-6')}` (node-not-found alert) |

Each instance is a full `<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path ... /></svg>` block that must be replaced with the corresponding icon function call inside the lit-html template.

### Phase 5: Extract Shared Components into `components.js`

**File:** `src/meshcore_hub/web/static/js/spa/components.js`

#### 5.1 Add `renderFilterCard()`

Extract the shared filter form pattern used by nodes, advertisements, and messages pages.

```javascript
/**
 * Render a filter card with configurable form fields, submit, and clear buttons.
 * @param {Object} options
 * @param {Array<Function>} options.fields - Array of render functions returning lit-html form controls
 * @param {string} options.basePath - Base URL path for the page
 * @param {Function} options.navigate - Router navigate function
 * @param {string} [options.submitLabel] - Text for submit button (default: "Filter")
 * @param {string} [options.clearLabel] - Text for clear button (default: "Clear")
 * @returns {TemplateResult}
 */
export function renderFilterCard({ fields, basePath, navigate, submitLabel, clearLabel }) {
    return html`
        <div class="card shadow mb-6 panel-solid">
            <div class="card-body py-4">
                <form @submit=${createFilterHandler(basePath, navigate)} class="flex gap-4 flex-wrap items-end">
                    ${fields.map(f => f())}
                    <div class="flex gap-2">
                        <button type="submit" class="btn btn-primary btn-sm">${submitLabel || t('common.filter')}</button>
                        <a href=${basePath} class="btn btn-ghost btn-sm">${clearLabel || t('common.clear')}</a>
                    </div>
                </form>
            </div>
        </div>
    `;
}
```

**Note:** Page-specific filter fields (select dropdowns, text inputs) are passed as render functions, keeping page-specific logic in the page files. The component is adopted immediately in all three pages (Phase 6).

#### 5.2 Add `renderStatCard()`

Extract the stat card pattern duplicated in `home.js` and `dashboard.js`:

```javascript
/**
 * Render a single stat card for dashboard/home pages.
 * @param {Object} options
 * @param {TemplateResult} options.icon - lit-html icon (from icons.js)
 * @param {string} options.color - CSS color value for the glow (e.g., pageColors.dashboard)
 * @param {string} options.title - Stat title (e.g., "Total Nodes")
 * @param {string|number} options.value - Stat value
 * @param {string} [options.description] - Optional stat description
 * @returns {TemplateResult}
 */
export function renderStatCard({ icon, color, title, value, description }) {
    return html`
        <div class="stat bg-base-200 rounded-box shadow panel-glow" style="--panel-color: ${color}">
            <div class="stat-figure">${icon}</div>
            <div class="stat-title">${title}</div>
            <div class="stat-value">${value}</div>
            ${description ? html`<div class="stat-desc">${description}</div>` : nothing}
        </div>`;
}
```

### Phase 6: Adopt `renderFilterCard()` in List Pages

**Files:** `nodes.js`, `messages.js`, `advertisements.js`

Retrofit all three list pages to use the extracted `renderFilterCard()` component from `components.js`. Each page defines its own filter fields as render functions and passes them to `renderFilterCard()`.

#### 6.1 `nodes.js`

**File:** `src/meshcore_hub/web/static/js/spa/pages/nodes.js`

The filter card (L128–170) contains a search text input, an `adv_type` select, and a conditional `adopted_by` select (shown when OIDC is enabled). Replace the inline filter card HTML with `renderFilterCard()`.

```javascript
import { renderFilterCard } from '../components.js';

// Inside fetchAndRenderData():
const filterHtml = renderFilterCard({
    fields: [
        () => html`
            <div class="form-control">
                <label class="label"><span class="label-text">${t('node_types.type')}</span></label>
                <select name="adv_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="" ...>${t('common.all')}</option>
                    ${advTypes.map(t => html`<option value=${t} ...>${t}</option>`)}
                </select>
            </div>`,
        () => html`
            <div class="form-control">
                <label class="label"><span class="label-text">${t('filters.search')}</span></label>
                <input type="text" name="search" value=${searchVal} class="input input-bordered input-sm w-40"
                       @keydown=${submitOnEnter} />
            </div>`,
    ],
    basePath: '/nodes',
    navigate: (url) => router.navigate(url, true),
});
```

#### 6.2 `advertisements.js`

**File:** `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`

The filter card (L179–236) contains a type select and search input. Same pattern as nodes — replace inline filter card with `renderFilterCard()`.

#### 6.3 `messages.js`

**File:** `src/meshcore_hub/web/static/js/spa/pages/messages.js`

The filter card (L306–360) contains a type select, channel direction select, and channel index select. Replace inline filter card with `renderFilterCard()`.

### Phase 7: Refactor `home.js` — Extract Sub-Renderers

**File:** `src/meshcore_hub/web/static/js/spa/pages/home.js`

The current `render()` function (L30–209) contains a single 123-line `litRender(html\`...\`)` call. Extract these sub-renderers:

#### 6.1 `renderHeroSection()`

Extract L72–77 (logo + site title + description):

```javascript
function renderHeroSection(config) {
    const logoSrc = window.__LOGO__ || '/static/images/logo.svg';
    return html`
        <div class="text-center mb-8">
            <img src=${logoSrc} alt=${config.network_name || 'MeshCore Hub'} class="mx-auto mb-4 w-24 h-24" />
            <h1 class="text-3xl font-bold mb-2">${config.network_name || 'MeshCore Hub'}</h1>
        </div>`;
}
```

#### 6.2 `renderStatsPanel()`

Extract L111–142 (stats cards — nodes, adverts, messages, with icons and values). Replace inline stat-card markup with `renderStatCard()` from Phase 5.2.

#### 6.3 `renderActivityChart()`

Extract L178–190 (the activity chart card with canvas element).

#### 6.4 Updated `render()`

After extraction, the `render()` function orchestrates the sub-renderers:
```javascript
export async function render(container, params, router) {
    const config = getConfig();
    // fetch data, then:
    litRender(html`
        <div class="py-6">
            ${renderHeroSection(config)}
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                ${renderStatsPanel(statsData)}
            </div>
            <!-- info card, etc. -->
            ${renderActivityChart()}
        </div>
    `, container);
}
```

### Phase 8: Refactor `admin/node-tags.js` — Extract Modal Dialogs

**File:** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js`

Extract the 5 `<dialog>` modals (L149–275, 127 lines) into separate render functions:

| Function | Lines | Dialog ID |
|----------|-------|-----------|
| `renderEditModal()` | L149–176 | `#editModal` |
| `renderMoveModal()` | L178–208 | `#moveModal` |
| `renderDeleteModal()` | L210–226 | `#deleteModal` |
| `renderCopyAllModal()` | L228–256 | `#copyAllModal` |
| `renderDeleteAllModal()` | L258–275 | `#deleteAllModal` |

Each function returns a lit-html `TemplateResult` containing the `<dialog>` element with its form. The modal JS logic (event listeners, `showModal()`, `close()`) stays in the page file.

Example extraction:
```javascript
function renderEditModal(tag) {
    return html`
        <dialog id="editModal" class="modal">
            <div class="modal-box">
                <h3 class="text-lg font-bold mb-4">${t('admin_node_tags.edit_tag')}</h3>
                <form method="dialog" @submit=${handleEditSubmit}>
                    <div class="form-control mb-4">
                        <label class="label">
                            <span class="label-text">${t('common.key')}</span>
                        </label>
                        <input type="text" name="key" class="input input-bordered w-full"
                               value=${tag.key} required maxlength="255" />
                    </div>
                    <!-- ... -->
                </form>
            </div>
        </dialog>`;
}
```

**Note:** Modal event handler references (e.g., `handleEditSubmit`) are closure-bound functions defined in the page's `render()` scope. These can be passed as parameters or kept as closures if the functions are defined before the render call.

### Phase 9: Update `dashboard.js` — Use `renderStatCard()`

**File:** `src/meshcore_hub/web/static/js/spa/pages/dashboard.js`

Update `render()` to use the extracted `renderStatCard()` component from `components.js`:

```javascript
import { renderStatCard } from '../components.js';
// ... existing imports
```

Replace the 3 inline stat cards (L141–169) with `renderStatCard()` calls.

Also extract `renderChartCards()` (L172–214) as a separate helper within the page to reduce nesting in the main `render()` call.

### Phase 10: Integration Verification

After all phases, verify no regressions:

#### 9.1 File-by-file checklist

- [ ] `icons.js` — 4 new functions appended, no existing functions modified
- [ ] `components.js` — 3 alert functions use icon imports, 3 raw-string helpers removed, `renderAuthSection()` uses icon imports, 2 new exported functions
- [ ] `auto-refresh.js` — 2 inline SVGs replaced, icon imports added
- [ ] `admin/node-tags.js` — 5 inline SVGs replaced, 5 modal functions extracted, existing behavior preserved
- [ ] `home.js` — 3 sub-renderers extracted, monolithic render split, `renderStatCard()` used
- [ ] `dashboard.js` — Inline stat cards replaced with `renderStatCard()`
- [ ] `nodes.js` — Filter card uses `renderFilterCard()`
- [ ] `messages.js` — Filter card uses `renderFilterCard()`
- [ ] `advertisements.js` — Filter card uses `renderFilterCard()`

#### 10.2 Build & verify

```bash
# Frontend build (verifies bundling, no JS import errors)
npm run build

# Run web tests (catches runtime issues in the SPA)
source .venv/bin/activate
pytest tests/test_web/ -v
```

#### 10.3 Manual verification areas

- All alert components render correctly (error, info, success, warning)
- Auth dropdown: login button visible when unauthenticated; user menu opens/closes when logged in; icons and role badges display correctly
- Auto-refresh toggle shows correct pause/play icons
- Admin node-tags page: modals open/close, submit, delete, copy-all still work
- Home page: hero, stats, activity chart render identically
- Dashboard: stat cards and charts render identically
- Nodes/Ads/Messages: filter forms function correctly, filters apply and clear as before

---

## File Change Summary

| # | File | Action | Phase | Description |
|---|------|--------|-------|-------------|
| 1 | `web/static/js/spa/icons.js` | Modify | 1 | Add `iconSettings`, `iconLogout`, `iconPause`, `iconPlay` |
| 2 | `web/static/js/spa/components.js` | Modify | 2, 5 | Replace 3 alert inline SVGs; remove 3 raw-string helpers; update `renderAuthSection()`; add `renderFilterCard()`, `renderStatCard()` |
| 3 | `web/static/js/spa/auto-refresh.js` | Modify | 3 | Replace 2 inline SVGs with `iconPause`/`iconPlay`; add imports |
| 4 | `web/static/js/spa/pages/admin/node-tags.js` | Modify | 4, 8 | Replace 5 inline SVGs; extract 5 modal render functions |
| 5 | `web/static/js/spa/pages/nodes.js` | Modify | 6 | Replace inline filter card with `renderFilterCard()` |
| 6 | `web/static/js/spa/pages/messages.js` | Modify | 6 | Replace inline filter card with `renderFilterCard()` |
| 7 | `web/static/js/spa/pages/advertisements.js` | Modify | 6 | Replace inline filter card with `renderFilterCard()` |
| 8 | `web/static/js/spa/pages/home.js` | Modify | 7 | Extract `renderHeroSection`, `renderStatsPanel`, `renderActivityChart`; use `renderStatCard()` |
| 9 | `web/static/js/spa/pages/dashboard.js` | Modify | 9 | Replace inline stat cards with `renderStatCard()`; extract `renderChartCards()` |
| 10 | `tests/test_web/` (relevant) | Verify | 10 | Ensure existing tests still pass; no new tests needed (pure refactor) |

---

## Execution Order

1. **Phase 1:** Add 4 missing icons to `icons.js`
2. **Phase 2:** Replace inline SVGs in `components.js` alerts + remove raw-string helpers
3. **Phase 3:** Replace inline SVGs in `auto-refresh.js`
4. **Phase 4:** Replace inline SVGs in `admin/node-tags.js`
5. **Phase 5:** Add `renderFilterCard()` and `renderStatCard()` to `components.js`
6. **Phase 6:** Adopt `renderFilterCard()` in `nodes.js`, `messages.js`, `advertisements.js`
7. **Phase 7:** Refactor `home.js` — extract sub-renderers, use `renderStatCard()`
8. **Phase 8:** Refactor `admin/node-tags.js` — extract modal dialogs
9. **Phase 9:** Refactor `dashboard.js` — use `renderStatCard()`, extract `renderChartCards()`
10. **Phase 10:** Build verification (`npm run build`), web test suite (`pytest tests/test_web/ -v`), manual smoke test

Phases 1–4 eliminate all inline SVGs. Phases 5–9 extract large templates and adopt shared components. Phase 10 validates.

---

## Out of Scope (Deferred)

| Item | Reason |
|------|--------|
| Messages dedup logic extraction | `messages.js` L109–170 (62 lines) is pure data processing, not UI rendering. Could be moved to a shared utility module but not part of this UI refactor. |
| CSS refactoring | `app.css` is already well-organized (388 lines with clear sections). No changes needed. |
