# Tasks - Mobile Navbar Restructure & Size Fixes

## Implementation Tasks

- [ ] **T1. Restructure `spa.html` navbar layout**
  - Remove the entire `<div class="dropdown">` block (lines 53-83) from `navbar-start`
  - Keep only the logo/name `<a>` link in `navbar-start`
  - Add new hamburger dropdown in `navbar-end`, after the OIDC `{% endif %}` (outside the conditional)
  - New hamburger shell: `<div class="dropdown dropdown-end lg:hidden">` with `<div tabindex="0" role="button" class="btn btn-ghost">` trigger (inline hamburger SVG or use `iconMenu` from icons.js via a data attribute)
  - Empty `<ul id="mobile-nav">` with classes `dropdown-content menu z-[1] p-2 shadow bg-base-100 rounded-box w-56 mt-3` (no `menu-sm`, width `w-56`)
  - Reference: `src/meshcore_hub/web/templates/spa.html` lines 52-129

- [ ] **T2. Create `renderMobileNav()` function in `app.js`**
  - Import icon functions from `icons.js`: `iconHome`, `iconDashboard`, `iconNodes`, `iconAdvertisements`, `iconMessages`, `iconMap`, `iconMembers`, `iconPage`
  - Read `config.features` and `config.custom_pages` from `window.__APP_CONFIG__`
  - Build `<li>` items using lit-html, matching the same feature-flag logic as the Jinja2 template
  - Use icon functions with `'h-5 w-5'` size class plus nav-icon color class (e.g., `nav-icon-dashboard`)
  - Set `data-nav-link` attributes on `<a>` elements for active-state highlighting
  - Render into the `#mobile-nav` container element
  - Include custom pages loop: iterate `config.custom_pages` (each has `slug`, `title`, `url`, `menu_order`), use `iconPage` for icon
  - Reference: `src/meshcore_hub/web/static/js/spa/app.js`, `src/meshcore_hub/web/static/js/spa/icons.js`

- [ ] **T3. Wire up `renderMobileNav()` in `app.js` initialization**
  - Call `renderMobileNav()` after `loadLocale()` and alongside `renderAuthSection()` (around line 177-181)
  - Pass config to the function
  - Reference: `src/meshcore_hub/web/static/js/spa/app.js` lines 176-183

- [ ] **T4. Update `renderAuthSection()` in `components.js`**
  - Change `<ul>` classes from `menu menu-sm` to `menu` (line 707)
  - Change dropdown width from `w-52` to `w-56` (line 707)
  - Change icon sizes from `h-4 w-4` to `h-5 w-5` in profile item (line 696) and logout item (line 717)
  - Reference: `src/meshcore_hub/web/static/js/spa/components.js` lines 696-720

- [ ] **T5. Add mobile dropdown CSS rules in `app.css`**
  - Add tap target sizing for mobile nav dropdown:
    ```css
    @media (max-width: 1023px) {
        .navbar .dropdown .menu li > a {
            padding-top: 0.625rem;
            padding-bottom: 0.625rem;
            font-size: 0.9375rem;
        }
    }
    ```
  - Reference: `src/meshcore_hub/web/static/css/app.css`

- [ ] **T6. Build and test**
  - `npm run build` — rebuild Tailwind + frontend assets
  - `pytest tests/test_web/` — targeted web tests
  - `pre-commit run --all-files` — quality checks
  - Visual verification: mobile viewport navbar order, dropdown sizes, desktop nav unchanged
