# React Migration Plan

Migration from lit-html (functional templates) to React 19 + TypeScript + Vite.

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Infrastructure (Vite, React shell, router, LitBridge, build pipeline, shared components) | **Complete** |
| 2 | Convert pages one-by-one from LitBridge to native React | **Complete** |
| 3 | Chart & map components (react-chartjs-2, react-leaflet) | **Complete** |
| 4 | Cleanup (remove lit-html, old spa/, LitBridge, @legacy alias) | **Complete** |
| 5 | Frontend CI + vitest unit/component tests + navbar → React (SPA shell) | **Complete** |

> **Phase 3 status:** All `window.Chart` / `window.L` / `window.QRCode` globals and the
> `charts.js` helper script are gone. Charts now use **react-chartjs-2** (typed builders in
> `spa-react/utils/charts.ts` + components in `spa-react/components/charts/Charts.tsx`),
> maps use **react-leaflet** (`MapPage.tsx`, `NodeDetail.tsx`), and QR codes use
> **react-qr-code** (`Channels.tsx`, `NodeDetail.tsx`). Chart.js, Leaflet (+ its CSS), and
> react-qr-code are bundled by Vite — the vendor `<script>`/`<link>` tags and the
> `build.js` vendor copy for leaflet/chart.js/qrcodejs were removed (fonts stay vendored).
> `spa-react/utils/charts.ts` imports `leaflet/dist/leaflet.css`; that CSS ships in the
> Vite bundle (`asset_app_css`), which is now loaded in `<head>` **before** `app.css` so the
> dark-mode map popup overrides in `app.css` still win.
>
> **Phase 2 status:** All 15 pages are converted to native React and wired into `App.tsx`.
> The old lit-html code in `spa/` is intentionally **kept** as the `spa.html` fallback
> (rendered only when the Vite bundle/manifest is absent) and is still referenced by
> 5 web tests. It will be removed in Phase 4, after those tests are updated.

## Architecture Decisions

- **TypeScript** strict mode, `@/` alias → `spa-react/` (the `@legacy/` alias was removed in Phase 4)
- **Vite 6** replaces esbuild; outputs to `static/dist/` with content-hashed filenames
- **Jinja2 shell preserved** — server renders navbar, SEO meta, config JSON; React owns `<main id="app">`
- **All pages native React** — LitBridge (the temporary wrapper for unconverted lit-html pages) was removed in Phase 4
- **react-i18next** loads same locale JSONs from `/static/locales/`; still exposes `window.t`
- **Vendor scripts removed** (Phase 3): chart.js, leaflet (+ CSS), and react-qr-code are bundled by Vite; only fonts remain vendored
- **DaisyUI + Tailwind v4** unchanged; `@source "../js/"` in input.css scans the spa-react/ source

## File Structure

```
vite.config.ts                          # Vite config (root=project, input=spa-react/index.html)
tsconfig.json                           # Strict TS, path alias @/ → spa-react/
build.js                                # Tailwind → vendor fonts copy → vite build → assets.json
package.json                            # React 19, react-router 7, react-i18next, react-chartjs-2,
                                        # react-leaflet, react-qr-code, chart.js, leaflet, vite, typescript

src/meshcore_hub/web/static/js/spa-react/
├── index.html                          # Vite HTML entry (not served; Jinja2 is the real shell)
├── main.tsx                            # Bootstrap: initI18n → render App, AuthSection, MobileNav
├── App.tsx                             # BrowserRouter, all routes, feature flags (native React pages)
├── vite-env.d.ts
├── types/config.ts                     # AppConfig interface, window.__APP_CONFIG__ + window.t declarations
├── context/AppConfigContext.tsx         # useAppConfig(), useFeatures(), hasRole(), channel labels
├── i18n/index.ts                       # initI18n() with i18next + language detector
├── hooks/
│   ├── useAutoRefresh.ts               # Timer-based refresh with pause/play
│   └── usePageTitle.ts                 # Set document.title from entity key
├── utils/
│   ├── api.ts                          # Typed apiGet<T>, apiPost, apiPut, apiDelete, apiPostForm
│   ├── format.ts                       # parseAppDate, formatDateTime, formatRelativeTime, emojis
│   ├── charts.ts                       # Chart.js config builders, ChartColors, averageRouteTier (imports chart.js/auto)
│   └── clipboard.ts                    # copyToClipboard with fallback
├── components/
│   ├── icons/index.tsx                 # 30+ SVG icon components (IconDashboard, IconNodes, etc.)
│   ├── charts/Charts.tsx              # react-chartjs-2 wrappers (ActivityChart, TrendLineChart, StackedBarChart, RoutesTrendChart, RouteDetailStrip)
│   ├── Alerts.tsx                      # Loading, ErrorAlert, InfoAlert, SuccessAlert, WarningBadge
│   ├── AuthSection.tsx                 # Navbar auth dropdown (login button or user menu)
│   ├── MobileNav.tsx                   # Mobile hamburger nav items
│   ├── ErrorBoundary.tsx              # React error boundary with fallback UI
│   ├── Pagination.tsx                 # URL-driven pagination (page param)
│   ├── StatCard.tsx                   # Dashboard stat card with icon/color
│   ├── NodeDisplay.tsx                # Node emoji + name + description
│   ├── FilterForm.tsx                 # FilterForm + FilterToggle (URL query driven)
│   ├── SortableTable.tsx             # SortableTableHeader + MobileSortSelect
│   ├── TimezoneIndicator.tsx         # Timezone abbreviation badge
│   ├── ObserverBadges.tsx            # Observer filter badges + localStorage helpers
│   ├── RouteTypeBadge.tsx            # Flood/Relay/Zero-hop badge
│   └── JsonTree.tsx                  # Expandable JSON viewer
└── pages/                             # All native React pages
    ├── Home.tsx, Dashboard.tsx, Nodes.tsx, NodeDetail.tsx, Advertisements.tsx,
    ├── Messages.tsx, Routes.tsx, Packets.tsx, PacketDetail.tsx, PacketGroupDetail.tsx,
    ├── Channels.tsx, MapPage.tsx, Members.tsx, Profile.tsx, CustomPage.tsx,
    └── NotFound.tsx, Maintenance.tsx
```

> The old `src/meshcore_hub/web/static/js/spa/` lit-html tree, `LitBridge.tsx`, and
> `legacy.d.ts` were deleted in Phase 4. There is no fallback bundle — the Vite build is required.

## Build Pipeline

```bash
npm run build
# 1. npx @tailwindcss/cli build (input.css → tailwind.css)
# 2. Copy vendor fonts (chart/map/QR libs are bundled by Vite, not vendored)
# 3. npx vite build (bundles React + chart.js + leaflet + react-qr-code → dist/assets/)
# 4. Remove stale dist/src/ artifact
# 5. Generate dist/assets.json (compatible format for Jinja2 template)
```

The Jinja2 template (`spa.html`) reads `assets.json` for the entry JS/CSS filenames:
```json
{ "app.js": "assets/index-XXXX.js", "app.css": "assets/index-XXXX.css", "vendor": {}, "locale_version": "..." }
```

Python (`app.py`) loads this manifest at startup and passes `asset_app_js` / `asset_app_css` to the template.
`asset_app_css` (which contains the bundled `leaflet.css`) is loaded in `<head>` before `app.css` so theme overrides win.

## Phase 2: Page Conversion

### Pattern for each page

1. Create `pages/PageName.tsx`:
   - Use `useSearchParams()` for filters/pagination/sort
   - Use typed `apiGet<T>()` with `useEffect` + `AbortController`
   - Replace lit-html `html\`...\`` with JSX
   - Use shared components (Pagination, FilterForm, StatCard, etc.)
   - Call `usePageTitle('entities.xxx')` for document title
2. In `App.tsx`: replace `<LitPage loader={() => import("@legacy/pages/xxx.js")} />` with `<PageName />`
3. Delete `src/meshcore_hub/web/static/js/spa/pages/xxx.js`
4. Run `npm run build` to verify bundle compiles
5. Run `pytest --no-cov tests/test_web/` to verify server tests still pass

### Conversion order (simplest → most complex)

| # | Page | File | Complexity | Notes |
|---|------|------|-----------|-------|
| 1 | NotFound | `not-found.js` | Done | Native React |
| 2 | Maintenance | `maintenance.js` | Done | Native React |
| 3 | Home | `home.js` | Done | Stats + nav cards + activity chart (still uses `window.createActivityChart`) |
| 4 | CustomPage | `custom-page.js` | Done | Fetches markdown HTML → `dangerouslySetInnerHTML` |
| 5 | Profile | `profile.js` | Done | Form + PUT + adopted nodes |
| 6 | Members | `members.js` | Done | Profile tiles grouped by role |
| 7 | Channels | `channels.js` | Done | Cards + admin CRUD modals + QR (`window.QRCode`) |
| 8 | Advertisements | `advertisements.js` | Done | Table + filters + auto-refresh + observer badges |
| 9 | Messages | `messages.js` | Done | Table + filters + auto-refresh + observer badges + dedupe |
| 10 | Routes | `routes.js` | Done | Cards + quality + history strips (`window.createRouteDetailStrip`) + admin CRUD |
| 11 | Nodes | `nodes.js` | Done | Table + filters + pagination + auto-refresh |
| 12 | NodeDetail | `node-detail.js` | Done | Map (`window.L`), QR, adopt/tags CRUD |
| 13 | Packets | `packets.js` | Done | Table + filters + auto-refresh |
| 14 | PacketDetail | `packet-detail.js` | Done | JSON tree + raw data |
| 15 | PacketGroupDetail | `packet-group-detail.js` | Done | Grouped receptions + path popover |
| 16 | Dashboard | `dashboard.js` | Done | Charts (`window.initDashboardCharts`), stat cards, route health |
| 17 | Map | `map.js` | Done | Leaflet map (`window.L`), markers, popups, filters |

### Key patterns in old pages → React equivalents

| Old pattern | React equivalent |
|-------------|-----------------|
| `render(container, params, router)` | Component with hooks |
| `params.query` | `useSearchParams()` |
| `params.signal` (AbortController) | `useEffect` cleanup + `AbortController` |
| `router.navigate(url)` | `useNavigate()(url)` |
| `litRender(html\`...\`, container)` | JSX return |
| `apiGet(path, params, { signal })` | `apiGet<T>(path, params, { signal })` |
| `getConfig()` | `useAppConfig()` |
| `t('key')` | `useTranslation().t('key')` or `window.t('key')` |
| `createAutoRefresh({ fetchAndRender, toggleContainer })` | `useAutoRefresh({ onRefresh })` |
| `pagination(page, totalPages, basePath, params)` | `<Pagination page={...} totalPages={...} basePath={...} />` |
| `renderFilterForm({ fields, basePath, navigate })` | `<FilterForm basePath={...}>...</FilterForm>` |
| `renderStatCard({ icon, color, title, value })` | `<StatCard icon={...} color={...} title={...} value={...} />` |
| `return () => { chart.destroy(); }` (cleanup) | `useEffect` return cleanup |
| `window.createActivityChart(...)` | `<ActivityChart>` / `buildActivityChart` (react-chartjs-2) |
| `window.L.map(...)` (Leaflet) | `<MapContainer>` + `useMap` controller (react-leaflet) |
| `window.QRCode(...)` | `<QRCode>` from `react-qr-code` |

## Phase 3: Charts & Maps — Complete

- **react-chartjs-2**: typed config builders in `utils/charts.ts` (`buildLineChart`,
  `buildActivityChart`, `buildStackedBar`, `buildRoutesTrend`, `buildRouteDetailStrip`,
  plus `ChartColors`, `averageRouteTier`, `routeQualityToTier`); React wrappers in
  `components/charts/Charts.tsx` (`ActivityChart`, `TrendLineChart`, `StackedBarChart`,
  `RoutesTrendChart`, `RouteDetailStrip`). `utils/charts.ts` imports `chart.js/auto` (registers
  everything) — replaces the old global `charts.js`.
- **react-leaflet**: `MapPage.tsx` rewritten with `<MapContainer>/<TileLayer>/<Marker>/<Popup>`
  + a `MapController` (useMap) for fit-bounds and a memoized marker list; `NodeDetail.tsx`
  static hero map with `divIcon` marker + `OffsetCenter` (useMap). Both `import "leaflet/dist/leaflet.css"`.
- **react-qr-code**: replaces `window.QRCode` in `Channels.tsx` and `NodeDetail.tsx`.
- Removed leaflet/chart.js/qrcodejs `@script`/`@link` tags and `charts.js` from `spa.html`;
  deleted `charts.js`; removed their copy steps from `build.js` (fonts still vendored).
- Moved the Vite CSS bundle (`asset_app_css`) into `<head>` **before** `app.css` so app.css's
  dark-mode Leaflet overrides win over the now-bundled leaflet.css.
- Updated `tests/test_web/test_caching.py` (charts.js-specific tests removed; generic JS-cache
  tests point at `spa/app.js`).

## Phase 4: Cleanup — Complete

- Removed `lit-html` **and** `qrcodejs` from package.json (both unused after Phases 2–3).
- Deleted `LitBridge.tsx`, `legacy.d.ts`, and the entire `src/meshcore_hub/web/static/js/spa/` tree.
- Removed the `@legacy` alias from `vite.config.ts` and `tsconfig.json`.
- Removed the lit-html fallback `{% else %}` branch from `spa.html` — the Vite build is now
  required (no fallback bundle).
- Updated the web tests that referenced the fallback: `test_home/advertisements/nodes/messages.py`
  now assert the React mount point (`id="app"`); `test_caching.py` JS-cache tests are header-only
  (static JS is bundled into `dist/`, absent in test env) and the dist-bundle test drops the
  fallback branch.
- (Vendor script tags / `charts.js` / `build.js` vendor copy were already removed in Phase 3.)
- Updated `AGENTS.md` with the React frontend conventions.

## Phase 5: Frontend CI, Tests & SPA Shell — Complete

- **Frontend CI job** (`.github/workflows/ci.yml`): `npm ci` → `tsc --noEmit` →
  `npm run test:frontend` → `npm run build` on every push/PR. Closes the gap where the
  ~9k lines of TSX had no CI coverage (pre-commit is Python-only).
- **vitest** (`vitest.config.ts`, jsdom env, `npm run test:frontend`):
  - `utils/charts.test.ts` — tier math (`routeQualityToTier`, `averageRouteTier`) and every
    chart builder (empty → null, dataset counts/labels/colors, stacked %, route-strip segments).
  - `utils/format.test.ts` — `parseAppDate`, `formatNumber`, `truncateKey`, `typeEmoji`,
    `extractFirstEmoji`, `getNodeEmoji`, `formatRelativeTime`.
  - `components/Navbar.test.tsx` — feature-gated nav links, custom pages, OIDC/maintenance
    auth gating (rendered with `MemoryRouter` + `AppConfigProvider`).
  - `components/Announcements.test.tsx` — system/network banner rendering, ordering, dismiss
    + sessionStorage persistence (covers behaviour that moved out of the Python suite).
- **Navbar → React (full SPA shell)**:
  - New `components/Navbar.tsx`, `components/ThemeToggle.tsx`, `components/Announcements.tsx`,
    and `hooks/useNavItems.tsx` (shared feature-gated nav list used by desktop + mobile).
  - `main.tsx` now renders a single root; `App.tsx` renders `<Navbar/>` + `<Announcements/>`
    above the routed `<main>`. Nav uses react-router `NavLink` (client-side nav + auto active
    class) — the imperative `data-nav-link` active-toggle and `#nav-loading` DOM bridge are gone.
  - `spa.html` slimmed to a thin shell: the Jinja2 navbar, banners, and vanilla theme-toggle
    script were removed; `<main id="app">` became a plain `<div id="app">` that React fills.
    SEO `<head>`, footer, and the early theme-init script stay server-rendered.
  - Backend: `_build_config_json` now exposes `system_announcement` / `network_announcement`
    (pre-rendered Markdown) for the React banners.
  - Python tests that asserted the server-rendered navbar/banners were rewritten to assert the
    embedded `__APP_CONFIG__` (new `get_app_config()` helper in `tests/test_web/conftest.py`);
    the flag→render path is now covered by the Navbar component test.

**Deliberately not done** (low ROI / high risk for this codebase): `@tanstack/react-query`
(conflicts with the deliberate `private, no-cache` + server-side Redis invalidation design and
is a 15-page refactor), Storybook (single-app component set), and Playwright E2E (needs the full
stack in CI; revisit if real browser coverage is wanted).

## Running & Testing

```bash
# Build frontend (produces static/dist/)
npm run build

# Run Python web tests (verifies Jinja2 template, proxy, caching)
source .venv/bin/activate
pytest --no-cov tests/test_web/

# Quality checks
pre-commit run --all-files

# Docker build (user does this manually)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core build
```

## Important Notes

- The old `spa/app.js` is NO LONGER LOADED. The Jinja2 template now loads the Vite-built React bundle.
- The Jinja2 template still renders the navbar, footer, banners, and theme toggle. Vendor chart/map/QR scripts are gone (bundled by Vite); only fonts remain vendored.
- `window.__APP_CONFIG__` is still injected by Jinja2 and read by React on bootstrap.
- The theme toggle in the navbar is still vanilla JS (in spa.html). React doesn't manage it.
- No more `window.Chart` / `window.L` / `window.QRCode` globals — charts, maps, and QR codes are bundled React components (Phase 3).
- Tailwind scans `static/js/` recursively — both `spa/` and `spa-react/` classes are included.
- The `dist/assets.json` format is unchanged from the esbuild era — Python code didn't need changes (its `vendor` map is now empty).
