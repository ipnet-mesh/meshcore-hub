# UI Frontend Refactor — Inline SVGs & Template Extraction — Task Checklist

**Plan:** `docs/plans/20260502-1520-ui-refactor/plan.md`
**Status:** Not Started

---

## Phase 1: Add Missing Icons to `icons.js`

- [ ] **1.1** `src/meshcore_hub/web/static/js/spa/icons.js` — Add `iconSettings(gear/cog, 24x24 stroke)` function after `iconAntenna`
- [ ] **1.2** `src/meshcore_hub/web/static/js/spa/icons.js` — Add `iconLogout(door-arrow-out, 24x24 stroke)` function
- [ ] **1.3** `src/meshcore_hub/web/static/js/spa/icons.js` — Add `iconPause(pause bars, 20x20 fill)` function
- [ ] **1.4** `src/meshcore_hub/web/static/js/spa/icons.js` — Add `iconPlay(play triangle, 20x20 fill)` function
- [ ] **1.5** Verify SVG paths for iconPause/iconPlay match the existing inline SVGs in `auto-refresh.js` L32–33 (paths: `M5.75 3a.75...` for pause, `M6.3 2.84A1.5...` for play)

## Phase 2: Replace Inline SVGs in `components.js`

- [ ] **2.1** `src/meshcore_hub/web/static/js/spa/components.js` — Update `icons.js` import (L11): add `iconError, iconInfo, iconSuccess, iconUser, iconSettings, iconLogout`
- [ ] **2.2** `src/meshcore_hub/web/static/js/spa/components.js` — Replace inline SVG in `errorAlert()` (L371) with `${iconError('stroke-current shrink-0 h-6 w-6')}`
- [ ] **2.3** `src/meshcore_hub/web/static/js/spa/components.js` — Replace inline SVG in `infoAlert()` (L383) with `${iconInfo('stroke-current shrink-0 h-6 w-6')}`
- [ ] **2.4** `src/meshcore_hub/web/static/js/spa/components.js` — Replace inline SVG in `successAlert()` (L395) with `${iconSuccess('stroke-current shrink-0 h-6 w-6')}`
- [ ] **2.5** `src/meshcore_hub/web/static/js/spa/components.js` — Remove `_svgUser()` (L595–597), `_svgSettings()` (L599–601), `_svgLogout()` (L603–605) raw-string SVG helpers
- [ ] **2.6** `src/meshcore_hub/web/static/js/spa/components.js` — Rewrite `renderAuthSection()` (L607–667) to use `litRender()` with `html\`...\`` instead of `innerHTML =`; use `iconUser`, `iconSettings`, `iconLogout` from `icons.js`; use `nothing` for empty state; use ternary for `adminItem`/`debugId` conditionals
- [ ] **2.7** Manually verify auth dropdown opens/closes correctly (CSS `:focus-within` behavior should be unchanged)

## Phase 3: Replace Inline SVGs in `auto-refresh.js`

- [ ] **3.1** `src/meshcore_hub/web/static/js/spa/auto-refresh.js` — Add `import { iconPause, iconPlay, iconInfo } from './icons.js';` at top
- [ ] **3.2** `src/meshcore_hub/web/static/js/spa/auto-refresh.js` — Replace inline pause SVG (L32) with `iconPause('w-4 h-4')`
- [ ] **3.3** `src/meshcore_hub/web/static/js/spa/auto-refresh.js` — Replace inline play SVG (L33) with `iconPlay('w-4 h-4')`

## Phase 4: Replace Inline SVGs in `admin/node-tags.js`

- [ ] **4.1** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Add `iconAlert, iconInfo` to imports from `../../icons.js`
- [ ] **4.2** Replace inline SVG L198 (moveModal warning) with `${iconAlert('stroke-current shrink-0 h-6 w-6')}`
- [ ] **4.3** Replace inline SVG L216 (deleteModal warning) with `${iconAlert('stroke-current shrink-0 h-6 w-6')}`
- [ ] **4.4** Replace inline SVG L246 (copyAllModal info) with `${iconInfo('stroke-current shrink-0 h-6 w-6')}`
- [ ] **4.5** Replace inline SVG L265 (deleteAllModal warning) with `${iconAlert('stroke-current shrink-0 h-6 w-6')}`
- [ ] **4.6** Replace inline SVG L279 (node-not-found warning) with `${iconAlert('stroke-current shrink-0 h-6 w-6')}`

## Phase 5: Extract Shared Components into `components.js`

- [ ] **5.1** `src/meshcore_hub/web/static/js/spa/components.js` — Add `renderFilterCard({ fields, basePath, navigate, submitLabel, clearLabel })` exported function — renders a `.card.panel-solid` wrapper with a form, field render functions, and submit/clear buttons
- [ ] **5.2** `src/meshcore_hub/web/static/js/spa/components.js` — Add `renderStatCard({ icon, color, title, value, description })` exported function — renders a `.stat.panel-glow` card with icon figure, title, value, and optional description

## Phase 6: Adopt `renderFilterCard()` in List Pages

- [ ] **6.1** `src/meshcore_hub/web/static/js/spa/pages/nodes.js` — Import `renderFilterCard`; replace inline filter card HTML (L125–171) with `renderFilterCard()` call passing 3 field render fns (search input, adv_type select, adopted_by select conditional), `basePath: '/nodes'`, and `navigate`
- [ ] **6.2** `src/meshcore_hub/web/static/js/spa/pages/messages.js` — Import `renderFilterCard`; replace inline filter card HTML (L306–337) with `renderFilterCard()` call passing 2 field render fns (message_type select, channel_idx select), `basePath: '/messages'`, and `navigate`
- [ ] **6.3** `src/meshcore_hub/web/static/js/spa/pages/advertisements.js` — Import `renderFilterCard`; replace inline filter card HTML (L179–214) with `renderFilterCard()` call passing 3 field render fns (search input, nodesFilter fragment, adopted_by select conditional), `basePath: '/advertisements'`, and `navigate`

## Phase 7: Refactor `home.js` — Extract Sub-Renderers

- [ ] **7.1** `src/meshcore_hub/web/static/js/spa/pages/home.js` — Extract `renderHeroSection(config)` function from L70–108 (logo, network name, city/country, welcome text, nav buttons)
- [ ] **7.2** `src/meshcore_hub/web/static/js/spa/pages/home.js` — Extract `renderStatsPanel(stats)` function from L111–142 (3 stat cards using `renderStatCard()` from Phase 5.2)
- [ ] **7.3** `src/meshcore_hub/web/static/js/spa/pages/home.js` — Extract `renderActivityChart()` function from L178–190 (activity chart card with canvas element)
- [ ] **7.4** `src/meshcore_hub/web/static/js/spa/pages/home.js` — Update `render()` to orchestrate sub-renderers: call `renderHeroSection()`, `renderStatsPanel()`, and `renderActivityChart()` as lit-html interpolations

## Phase 8: Refactor `admin/node-tags.js` — Extract Modal Dialogs

- [ ] **8.1** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Extract `renderEditModal()` from L149–176 (#editModal dialog)
- [ ] **8.2** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Extract `renderMoveModal()` from L178–208 (#moveModal dialog)
- [ ] **8.3** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Extract `renderDeleteModal()` from L210–226 (#deleteModal dialog)
- [ ] **8.4** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Extract `renderCopyAllModal()` from L228–256 (#copyAllModal dialog)
- [ ] **8.5** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Extract `renderDeleteAllModal()` from L258–275 (#deleteAllModal dialog)
- [ ] **8.6** `src/meshcore_hub/web/static/js/spa/pages/admin/node-tags.js` — Update `render()` to reference extracted modal functions; ensure event handler references (e.g., `handleEditSubmit`) remain accessible via closure or parameters

## Phase 9: Update `dashboard.js` — Use `renderStatCard()`

- [ ] **9.1** `src/meshcore_hub/web/static/js/spa/pages/dashboard.js` — Import `renderStatCard` from `../components.js`
- [ ] **9.2** `src/meshcore_hub/web/static/js/spa/pages/dashboard.js` — Replace 3 inline stat cards (L141–169) with `renderStatCard()` calls, each providing icon, color, title, value, and description
- [ ] **9.3** `src/meshcore_hub/web/static/js/spa/pages/dashboard.js` — Extract `renderChartCards()` helper from L172–214 (3 conditional chart card containers)

## Phase 10: Integration Verification

- [ ] **10.1** Run `npm run build` — verify no JS import errors
- [ ] **10.2** Run `source .venv/bin/activate && pytest tests/test_web/ -v` — verify existing web tests still pass
- [ ] **10.3** Run `source .venv/bin/activate && pre-commit run --all-files` — verify lint, type check, and format
- [ ] **10.4** Manual smoke test — verify alerts render correctly (error, info, success, warning)
- [ ] **10.5** Manual smoke test — verify auth dropdown (login button when unauthenticated; user menu opens/closes when logged in; icons and role badges display)
- [ ] **10.6** Manual smoke test — verify auto-refresh toggle shows correct pause/play icons
- [ ] **10.7** Manual smoke test — verify admin node-tags page modals open/close, submit, delete, copy-all still work
- [ ] **10.8** Manual smoke test — verify home page hero, stats, activity chart render identically
- [ ] **10.9** Manual smoke test — verify dashboard stat cards and charts render identically
- [ ] **10.10** Manual smoke test — verify nodes/ads/messages filter forms function correctly (filters apply, clear works)

---

## File Change Summary

| # | File | Action | Phase(s) |
|---|------|--------|----------|
| 1 | `web/static/js/spa/icons.js` | Modify | 1 |
| 2 | `web/static/js/spa/components.js` | Modify | 2, 5 |
| 3 | `web/static/js/spa/auto-refresh.js` | Modify | 3 |
| 4 | `web/static/js/spa/pages/admin/node-tags.js` | Modify | 4, 8 |
| 5 | `web/static/js/spa/pages/nodes.js` | Modify | 6 |
| 6 | `web/static/js/spa/pages/messages.js` | Modify | 6 |
| 7 | `web/static/js/spa/pages/advertisements.js` | Modify | 6 |
| 8 | `web/static/js/spa/pages/home.js` | Modify | 7 |
| 9 | `web/static/js/spa/pages/dashboard.js` | Modify | 9 |
| 10 | `tests/test_web/` | Verify | 10 |
