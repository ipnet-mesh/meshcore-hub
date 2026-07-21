# React Migration Plan

Migration from lit-html (functional templates) to React 19 + TypeScript + Vite.

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Infrastructure (Vite, React shell, router, LitBridge, build pipeline, shared components) | **Complete** |
| 2 | Convert pages one-by-one from LitBridge to native React | **Complete** |
| 3 | Chart & map components (react-chartjs-2, react-leaflet) | Not started |
| 4 | Cleanup (remove lit-html, old spa/, build.js esbuild remnants) | Not started |
| 5 | Optional enhancements (tests, react-query, Storybook) | Not started |

> **Phase 2 status:** All 15 pages are converted to native React and wired into `App.tsx`.
> The old lit-html code in `spa/` is intentionally **kept** as the `spa.html` fallback
> (rendered only when the Vite bundle/manifest is absent) and is still referenced by
> 5 web tests. It will be removed in Phase 4, after those tests are updated.
> Charts/maps still use `window.Chart`, `window.L`, `window.QRCode`, and the `charts.js`
> globals — these move to `react-chartjs-2` / `react-leaflet` in Phase 3.

## Architecture Decisions

- **TypeScript** strict mode, `@/` alias → `spa-react/`, `@legacy/` alias → `spa/`
- **Vite 6** replaces esbuild; outputs to `static/dist/` with content-hashed filenames
- **Jinja2 shell preserved** — server renders navbar, SEO meta, config JSON; React owns `<main id="app">`
- **LitBridge** wraps unconverted pages: dynamic import → `render(container, params, router)` → cleanup
- **react-i18next** loads same locale JSONs from `/static/locales/`; exposes `window.t` for legacy scripts
- **Vendor scripts kept** (leaflet, chart.js, qrcodejs as globals) until Phase 3 converts map/charts
- **DaisyUI + Tailwind v4** unchanged; `@source "../js/"` in input.css scans both spa/ and spa-react/

## File Structure

```
vite.config.ts                          # Vite config (root=project, input=spa-react/index.html)
tsconfig.json                           # Strict TS, path aliases
build.js                                # Tailwind → vendor copy → vite build → assets.json
package.json                            # React 19, react-router 7, react-i18next, vite, typescript

src/meshcore_hub/web/static/js/spa-react/
├── index.html                          # Vite HTML entry (not served; Jinja2 is the real shell)
├── main.tsx                            # Bootstrap: initI18n → render App, AuthSection, MobileNav
├── App.tsx                             # BrowserRouter, all routes, feature flags, LitBridge wiring
├── vite-env.d.ts
├── legacy.d.ts                         # TS declarations for @legacy/*.js modules
├── types/config.ts                     # AppConfig interface, window.__APP_CONFIG__ declaration
├── context/AppConfigContext.tsx         # useAppConfig(), useFeatures(), hasRole(), channel labels
├── i18n/index.ts                       # initI18n() with i18next + language detector
├── hooks/
│   ├── useAutoRefresh.ts               # Timer-based refresh with pause/play
│   └── usePageTitle.ts                 # Set document.title from entity key
├── utils/
│   ├── api.ts                          # Typed apiGet<T>, apiPost, apiPut, apiDelete, apiPostForm
│   ├── format.ts                       # parseAppDate, formatDateTime, formatRelativeTime, emojis
│   └── clipboard.ts                    # copyToClipboard with fallback
├── components/
│   ├── icons/index.tsx                 # 30+ SVG icon components (IconDashboard, IconNodes, etc.)
│   ├── Alerts.tsx                      # Loading, ErrorAlert, InfoAlert, SuccessAlert, WarningBadge
│   ├── AuthSection.tsx                 # Navbar auth dropdown (login button or user menu)
│   ├── MobileNav.tsx                   # Mobile hamburger nav items
│   ├── ErrorBoundary.tsx              # React error boundary with fallback UI
│   ├── LitBridge.tsx                  # Wraps old lit-html page modules in React lifecycle
│   ├── Pagination.tsx                 # URL-driven pagination (page param)
│   ├── StatCard.tsx                   # Dashboard stat card with icon/color
│   ├── NodeDisplay.tsx                # Node emoji + name + description
│   ├── FilterForm.tsx                 # FilterForm + FilterToggle (URL query driven)
│   ├── SortableTable.tsx             # SortableTableHeader + MobileSortSelect
│   ├── TimezoneIndicator.tsx         # Timezone abbreviation badge
│   ├── ObserverBadges.tsx            # Observer filter badges + localStorage helpers
│   ├── RouteTypeBadge.tsx            # Flood/Relay/Zero-hop badge
│   └── JsonTree.tsx                  # Expandable JSON viewer
└── pages/
    ├── NotFound.tsx                   # ✅ Converted (native React)
    └── Maintenance.tsx                # ✅ Converted (native React)

src/meshcore_hub/web/static/js/spa/    # OLD lit-html pages (still used via LitBridge)
├── app.js                             # Old entry (NO LONGER LOADED — replaced by spa-react/main.tsx)
├── router.js                          # Old router (replaced by react-router)
├── api.js                             # Old API client (replaced by utils/api.ts)
├── components.js                      # Old shared components (replaced by React components)
├── i18n.js                            # Old i18n (replaced by react-i18next)
├── icons.js                           # Old icons (replaced by components/icons/)
├── auto-refresh.js                    # Old auto-refresh (replaced by hooks/useAutoRefresh.ts)
├── json-tree.js                       # Old JSON tree (replaced by components/JsonTree.tsx)
└── pages/                             # Old page modules (loaded via LitBridge until converted)
    ├── home.js, dashboard.js, nodes.js, node-detail.js, ...
```

## Build Pipeline

```bash
npm run build
# 1. npx @tailwindcss/cli build (input.css → tailwind.css)
# 2. Copy vendor files (leaflet, chart.js, qrcodejs, fonts)
# 3. npx vite build (bundles React + legacy lit-html pages → dist/assets/)
# 4. Remove stale dist/src/ artifact
# 5. Generate dist/assets.json (compatible format for Jinja2 template)
```

The Jinja2 template (`spa.html`) reads `assets.json` for the entry JS filename:
```json
{ "app.js": "assets/index-XXXX.js", "vendor": {...}, "locale_version": "..." }
```

Python (`app.py`) loads this manifest at startup and passes `asset_app_js` / `asset_app_css` to the template.

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
| `window.createActivityChart(...)` | Keep as-is until Phase 3 (react-chartjs-2) |
| `window.L.map(...)` (Leaflet) | Keep as-is until Phase 3 (react-leaflet) |
| `window.QRCode(...)` | Keep as-is or use `react-qr-code` package |

## Phase 3: Charts & Maps

- Install `react-chartjs-2` (already in package.json) — create typed wrapper components
- Install `react-leaflet` (already in package.json) — create `<MeshMap>` component
- Port `charts.js` global functions into React chart components
- Remove leaflet/chart.js vendor `<script>` tags from `spa.html`
- Remove `charts.js` global script

## Phase 4: Cleanup

- Remove `lit-html` from package.json
- Delete `LitBridge.tsx`
- Delete entire `src/meshcore_hub/web/static/js/spa/` directory
- Remove `@legacy` alias from vite.config.ts and tsconfig.json
- Delete `legacy.d.ts`
- Remove vendor script tags from `spa.html` (leaflet, chart.js, qrcodejs, charts.js)
- Remove `build.js` vendor copy for leaflet/chart.js/qrcodejs (now bundled by Vite)
- Update `AGENTS.md` with new frontend conventions

## Phase 5: Optional Enhancements

- Add `vitest` + `@testing-library/react` for component tests
- Add Playwright for E2E browser tests
- Consider `@tanstack/react-query` for data fetching
- Consider moving navbar from Jinja2 to React (full SPA shell)
- Add Storybook for component development

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
- The Jinja2 template still renders the navbar, footer, banners, theme toggle, and vendor scripts.
- `window.__APP_CONFIG__` is still injected by Jinja2 and read by React on bootstrap.
- The theme toggle in the navbar is still vanilla JS (in spa.html). React doesn't manage it.
- Old lit-html pages loaded via LitBridge still use `window.Chart`, `window.L`, `window.QRCode` globals.
- Tailwind scans `static/js/` recursively — both `spa/` and `spa-react/` classes are included.
- The `dist/assets.json` format is unchanged from the esbuild era — Python code didn't need changes.
