# Plan: System Announcement Banner + System Maintenance Mode

**Date:** 2026-06-14
**Status:** Draft

## Problem

Two new operator-only controls are needed, both driven by environment variables and applied at web-service startup (set var → restart `web` component):

1. **`SYSTEM_ANNOUNCEMENT`** — a second, higher-priority banner for important system-level notices (downtime, maintenance windows, alerts). It must:
   - Render across all pages, stacked **above** the existing network announcement banner and **below** the site navbar (order: navbar → system announcement → network announcement).
   - **Not** be dismissable (no close button, no `sessionStorage`/`localStorage`). It stays until the operator unsets the var and restarts.

2. **`SYSTEM_MAINTENANCE`** (boolean, default `false`) — a hard maintenance gate. When enabled, almost all site functionality is disabled so that **no API calls are made** (the API service / database may be offline while `web` stays up):
   - Navbar menu shows only **Home**; the OIDC user/profile menu is hidden.
   - The main content renders a friendly, translatable "Site Under Maintenance" page showing the site logo, site name, and the maintenance message — no dashboard widgets, counts, charts, or nav links.
   - The maintenance page **may** be an SPA-rendered page, but it must make **zero** backend API calls.

Both follow the existing `NETWORK_ANNOUNCEMENT` pattern (see `docs/plans/20260509-1150-flash-banner/plan.md`): config field → `app.state` → template context, wired through `web/cli.py`.

## Background / Current State

- The dashboard is a **server-rendered shell** (`web/templates/spa.html`) hosting a client-side SPA. The navbar and both banner slots live in the Jinja shell; `<main id="app">` is filled by the SPA.
- The existing network announcement: config field `network_announcement` (`common/config.py:412`), Markdown-rendered to HTML once at startup in `create_app()` (`web/app.py:528-538`), passed to the template via `spa_catchall()` context (`web/app.py:1182`), and rendered in `spa.html:114-124` with a dismiss button backed by `sessionStorage`.
- Navbar menu items are gated by `{% if features.x %}` (`spa.html:58-90`); mobile nav is built client-side in `app.js:renderMobileNav()` from `config.features`; the OIDC auth/profile menu renders into `#auth-section` (`spa.html:101-103`, `app.js:248-249`, `components.js:renderAuthSection`).
- Feature flags are assembled in two parallel places: `WebSettings.features` (`config.py:451-474`) and the dependency-override block in `create_app()` (`web/app.py:540-559`). The SPA reads `config.features` to register routes (`app.js:66-108`).
- Home page (`pages/home.js`) **does** call the API (`/api/v1/dashboard/*`), so maintenance mode cannot simply fall back to Home — every route, including `/`, must short-circuit to the maintenance page.
- `pages/not-found.js` is a clean model for a no-API SPA page (pure `litRender` + `t()`).

## Approach

### Part A — `SYSTEM_ANNOUNCEMENT` (non-dismissable banner)

Mirror the `NETWORK_ANNOUNCEMENT` mechanism exactly, minus the dismiss affordance, and render it **above** the network banner.

- New `WebSettings.system_announcement: Optional[str]` field (Markdown supported, same as network announcement).
- Render Markdown → HTML once at startup into `app.state.system_announcement`.
- Pass into the `spa_catchall()` template context.
- In `spa.html`, insert a new banner block immediately **before** the existing `network_announcement` block (so DOM order is navbar → system → network). Use a distinct, more urgent style (`alert-error`) to differentiate it from the amber `alert-warning` network banner. **No** close button and **no** `sessionStorage` script.

This is purely a template concern — like the network banner, it is **not** added to `_build_config_json()`.

### Part B — `SYSTEM_MAINTENANCE` (functionality gate)

A boolean that, when true, suppresses nav + auth UI server-side and forces the SPA to render a no-API maintenance page for every route.

**Server side (`spa.html` + `app.py`):**
- New `WebSettings.system_maintenance: bool = False` field.
- Store `app.state.system_maintenance`.
- When maintenance is on, force `effective_features` to all-`False` in `create_app()` so the server-rendered desktop nav (`{% if features.x %}`) collapses to just the static Home link automatically. (Home is hard-coded at `spa.html:60`, not feature-gated, so it remains.)
- Hide the OIDC auth/profile menu: gate `#auth-section` with `{% if oidc_enabled and not system_maintenance %}`.
- Add `system_maintenance` to **both** the template context (for the auth gate) and `_build_config_json()` (so the SPA knows to short-circuit).

**Client side (`app.js` + new `pages/maintenance.js`):**
- Early in `app.js`, if `config.system_maintenance` is truthy: register the maintenance page as the handler for `'/'`, set it as the not-found handler, and **skip** registering all other feature routes. This guarantees every navigation renders the maintenance page and no page module that calls the API is ever loaded.
- Skip `renderAuthSection()` and `renderMobileNav()` (or render an empty/Home-only mobile nav) when in maintenance mode, so no profile menu appears and the mobile menu has nothing API-dependent.
- New `pages/maintenance.js`: a pure `litRender` page (modeled on `not-found.js`) showing the logo (`config.logo_url`), site name (`config.network_name`), and the translatable maintenance message. **No imports from `api.js`, no `fetch`.**

The two layers are belt-and-suspenders: server forces nav/auth empty; client refuses to load any API-touching page module.

## New Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SYSTEM_ANNOUNCEMENT` | string (Markdown) | `None` (empty) | Non-dismissable system banner shown above the network announcement on every page. Empty = no banner. |
| `SYSTEM_MAINTENANCE` | bool | `false` | When true, disables site functionality: nav shows only Home, profile menu hidden, all pages render a maintenance notice, and no API calls are made. |

Both require a `web` service restart to take effect, consistent with all other `NETWORK_*`/`SYSTEM_*` settings.

## Scope of Changes

### 1. Configuration — `src/meshcore_hub/common/config.py`

Add fields to `WebSettings`. Place `system_announcement` near `network_announcement` (~line 415) and `system_maintenance` near the feature-flag section (~line 417):

```python
system_announcement: Optional[str] = Field(
    default=None,
    description="Markdown system announcement banner (non-dismissable, empty = none)",
)
system_maintenance: bool = Field(
    default=False,
    description="Enable maintenance mode: disables site functionality and API calls",
)
```

### 2. Web App — `src/meshcore_hub/web/app.py`

#### 2a. `create_app()` signature (~line 375)
Add `system_announcement: str | None = None` and `system_maintenance: bool | None = None` parameters (after `network_announcement`).

#### 2b. `create_app()` body — render system announcement (~after line 538)
Mirror the network-announcement block:

```python
raw_system_announcement = (
    system_announcement
    if system_announcement is not None
    else settings.system_announcement
)
if raw_system_announcement:
    import markdown
    app.state.system_announcement = markdown.markdown(raw_system_announcement)
else:
    app.state.system_announcement = None
```

#### 2c. `create_app()` body — maintenance state + feature suppression (~line 540-559)
```python
app.state.system_maintenance = (
    system_maintenance
    if system_maintenance is not None
    else settings.system_maintenance
)
```
Then, after `effective_features` is computed, if maintenance is on, force everything off so the server-rendered nav collapses:

```python
if app.state.system_maintenance:
    effective_features = {k: False for k in effective_features}
app.state.features = effective_features
```

#### 2d. `_build_config_json()` (~line 301-325)
Add `"system_maintenance": app.state.system_maintenance,` to the `config` dict so the SPA can short-circuit. (System announcement is **not** added — template-only.)

#### 2e. `spa_catchall()` template context (~line 1173-1193)
Add:
```python
"system_announcement": request.app.state.system_announcement,
"system_maintenance": request.app.state.system_maintenance,
```

### 3. SPA Template — `src/meshcore_hub/web/templates/spa.html`

#### 3a. System banner — insert **before** the network banner block (before current line 114)
```html
{% if system_announcement %}
<div id="system-banner" class="alert alert-error rounded-none py-2 px-4 text-center text-sm">
    <div class="flash-banner-content">{{ system_announcement | safe }}</div>
</div>
{% endif %}
```
No close button, no script — non-dismissable. The existing `network_announcement` block stays directly below, preserving order: navbar → system → network.

#### 3b. Hide auth/profile menu in maintenance (line 101)
```html
{% if oidc_enabled and not system_maintenance %}
<div id="auth-section"></div>
{% endif %}
```

Desktop nav menu items need no change — they are already `{% if features.x %}` gated and collapse to Home once features are forced off in 2c.

### 4. SPA App — `src/meshcore_hub/web/static/js/spa/app.js`

After `const features = ...` (~line 39), branch on maintenance before route registration:

```js
if (config.system_maintenance) {
    const maintenanceHandler = pageHandler(pages.maintenance);
    router.addRoute('/', maintenanceHandler);
    router.setNotFound(maintenanceHandler);
    await loadLocale(localStorage.getItem('meshcore-locale') || config.locale || 'en');
    // No auth section, no mobile nav (nothing API-dependent)
    router.start();
} else {
    // ... existing route registration, auth/mobile nav render, router.start()
}
```

Add `maintenance: () => import('./pages/maintenance.js'),` to the `pages` map (~line 15-31). Keep the existing non-maintenance path intact (the simplest structure is an early `if (config.system_maintenance) { ...; } else { <all existing setup> }`, or an early return-style guard wrapped appropriately for the top-level `await`).

### 5. New Page — `src/meshcore_hub/web/static/js/spa/pages/maintenance.js`

Modeled on `not-found.js`. **No `api.js` import, no fetch.**

```js
import { html, litRender, t, getConfig } from '../components.js';

export async function render(container, params, router) {
    const config = getConfig();
    litRender(html`
<div class="hero min-h-[70vh]">
    <div class="hero-content text-center">
        <div class="max-w-md flex flex-col items-center gap-4">
            <img src=${config.logo_url} alt=${config.network_name}
                 class="theme-logo${config.logo_invert_light ? ' theme-logo--invert-light' : ''} h-16 w-16" />
            <h1 class="text-3xl font-bold">${config.network_name}</h1>
            <h2 class="text-xl font-semibold text-warning">${t('maintenance.title')}</h2>
            <p class="text-base-content/70">${t('maintenance.message')}</p>
        </div>
    </div>
</div>`, container);
}
```

(Confirm `getConfig` is exported from `components.js` — it is imported in `app.js:10`.)

### 6. i18n — `src/meshcore_hub/web/static/locales/en.json` and `nl.json`

Add a `maintenance` top-level section to both locale files:

```json
"maintenance": {
  "title": "Site Under Maintenance",
  "message": "We're performing scheduled maintenance and will be back shortly. Thank you for your patience."
}
```

(Provide a Dutch translation for `nl.json`.) If the server-rendered shell needs a maintenance string (it does not in this design — the message is SPA-rendered), the Python-side `t()` helper / locale loader would also need the key; not required here.

### 7. Web CLI — `src/meshcore_hub/web/cli.py`

Mirror `--network-announcement` (~line 140-146):

```python
@click.option("--system-announcement", type=str, default=None,
              envvar="SYSTEM_ANNOUNCEMENT",
              help="Markdown system announcement banner (non-dismissable)")
@click.option("--system-maintenance", is_flag=True, default=False,
              envvar="SYSTEM_MAINTENANCE",
              help="Enable maintenance mode (disables site functionality)")
```

Add `system_announcement: str | None,` and `system_maintenance: bool,` to the `web()` signature (~line 175) and pass both through to `create_app()` (~line 274).

Note: `is_flag` env parsing — Click coerces `SYSTEM_MAINTENANCE` truthy strings via `envvar`. Verify boolean env coercion ("true"/"1") behaves as expected; if not, read it via the settings object instead (settings already parses the bool through pydantic), i.e. pass `system_maintenance=None` default and let `create_app()` fall back to `settings.system_maintenance`.

### 8. CSS — `src/meshcore_hub/web/static/css/app.css`

The system banner reuses `.flash-banner-content` styling. Optionally add `#system-banner` to the existing flash-banner fl/centering rule so links/code render consistently. Minimal/no new CSS expected.

### 9. Documentation

| File | Change |
|------|--------|
| `.env.example` | Add `SYSTEM_ANNOUNCEMENT=` (after `NETWORK_ANNOUNCEMENT`, with comment) and `SYSTEM_MAINTENANCE=false` (near feature flags, with comment) |
| `AGENTS.md` | Add both vars to the Environment Variables table |
| `README.md` | If it documents `NETWORK_ANNOUNCEMENT`, add the two new vars alongside |

## Files Changed (Summary)

| File | Change |
|------|--------|
| `src/meshcore_hub/common/config.py` | Add `system_announcement`, `system_maintenance` fields |
| `src/meshcore_hub/web/app.py` | New params, render system announcement, maintenance state, force features off, config JSON + template context |
| `src/meshcore_hub/web/templates/spa.html` | System banner above network banner; gate auth section on maintenance |
| `src/meshcore_hub/web/static/js/spa/app.js` | Maintenance short-circuit: single route + not-found = maintenance page, skip auth/mobile nav |
| `src/meshcore_hub/web/static/js/spa/pages/maintenance.js` | **New** no-API maintenance page |
| `src/meshcore_hub/web/static/locales/en.json`, `nl.json` | New `maintenance` translation block |
| `src/meshcore_hub/web/cli.py` | `--system-announcement`, `--system-maintenance` options + wiring |
| `src/meshcore_hub/web/static/css/app.css` | Optional `#system-banner` styling |
| `.env.example`, `AGENTS.md`, `README.md` | Document new vars |

## Tests to Add/Update

| Test File | Change |
|-----------|--------|
| `tests/test_common/test_config.py` | `system_announcement` defaults to `None`; `system_maintenance` defaults to `False`; bool parses from env |
| `tests/test_web/test_app.py` | System banner HTML present when `system_announcement` set, absent when `None`; rendered **above** network banner (assert ordering in HTML); **no** dismiss button / `sessionStorage` script in the system block |
| `tests/test_web/test_app.py` | Markdown rendered (`**bold**` → `<strong>`); raw `<script>` does not execute |
| `tests/test_web/test_app.py` | When `system_maintenance=True`: `#auth-section` absent; desktop nav contains only Home (no dashboard/nodes/etc links); `config_json` contains `"system_maintenance": true` |
| `tests/test_web/test_app.py` | When `system_maintenance=False`: nav + auth render as today (regression) |

(Frontend SPA behavior — route short-circuit, no-API page — is verified by code review + manual check, matching the repo's existing JS test posture. Note in PR that the maintenance page imports nothing from `api.js`.)

## Edge Cases

- **Both banners set:** system (error/red) on top, network (warning/amber) below — verified by DOM order. Both visible simultaneously.
- **System announcement empty / whitespace:** no banner (Jinja `{% if %}` falsy).
- **Operator-controlled HTML in system announcement:** same trust model as network announcement — operator env var, Markdown lib doesn't execute JS.
- **Maintenance + announcements:** banners still render in maintenance mode (operator likely wants the maintenance notice visible as a banner too). Confirm this is desired; the design keeps banners independent of the maintenance gate.
- **Maintenance + OIDC:** profile menu hidden; no `/auth/user` call needed for rendering. Existing auth routes still exist server-side but are not exercised by the maintenance SPA path.
- **Deep-link during maintenance** (e.g. `/dashboard`): SPA not-found handler → maintenance page; no API page module loaded.
- **Restart required:** both vars read at startup into `app.state`; consistent with all other settings.

## Out of Scope

- Scheduling / auto start-end times for either feature (operator toggles var + restart).
- Admin UI to edit announcement or toggle maintenance live.
- Multiple severity levels for the system banner (single error-style banner).
- Blocking the API service itself or returning 503 from API routes — maintenance is a `web`-layer UX gate only; the operator stops the API/DB separately.
- Per-user/role maintenance bypass.

## Implementation Order

1. `config.py`: add both fields.
2. `app.py`: params, system-announcement render, maintenance state, feature suppression, config JSON, template context.
3. `spa.html`: system banner block (above network), auth-section gate.
4. `pages/maintenance.js`: new no-API page.
5. `app.js`: maintenance short-circuit + `pages.maintenance` entry.
6. i18n: `maintenance` block in `en.json` + `nl.json`.
7. `cli.py`: options + wiring (verify bool env coercion).
8. `app.css`: optional `#system-banner` styling.
9. Tests (config + web).
10. Docs (`.env.example`, `AGENTS.md`, `README.md`).
11. Run `pre-commit run --all-files` and `pytest tests/test_web/ tests/test_common/`; manually verify banner stacking and that maintenance mode issues no network requests (browser devtools).
