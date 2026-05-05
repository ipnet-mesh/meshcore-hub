# UI Feedback - Mobile Navbar Restructure & Size Fixes

Date: 2026-05-05

## Problem

1. **Mobile navbar layout** — The hamburger menu currently sits in `navbar-start` (left side), leaving the mobile layout as: `[hamburger + logo/name] ... [spinner | theme | user]`. The desired order is: `[logo/name] ... [spinner | theme | user | hamburger]`.

2. **Dropdown menu sizes too small** — After the Tailwind v4 / DaisyUI v5 upgrade, the mobile navigation dropdown and user profile dropdown render with noticeably smaller text and icons, making tap targets difficult to hit.

3. **Duplicated inline SVGs** — The mobile nav dropdown in `spa.html` contains inline SVGs duplicated from the `icons.js` icon functions. These should use the existing JS icon functions to eliminate duplication.

## Files to Change

| File | Change |
|------|--------|
| `src/meshcore_hub/web/templates/spa.html` | Restructure navbar: move hamburger to `navbar-end`, remove inline SVGs from mobile dropdown, render mobile nav via JS instead |
| `src/meshcore_hub/web/static/js/spa/app.js` | Add mobile nav rendering (inject icon + link items into the mobile dropdown via JS) |
| `src/meshcore_hub/web/static/js/spa/components.js` | Increase user profile dropdown sizes (`menu-sm` → normal or custom, icon `h-4 w-4` → `h-5 w-5`) |
| `src/meshcore_hub/web/static/css/app.css` | Add CSS rules for increased mobile dropdown font size, icon size, and tap target padding |

## Step-by-step Plan

### Step 1: Restructure `spa.html` navbar layout

**Current structure:**
```
navbar-start:  [hamburger dropdown] [logo/name link]
navbar-center: [desktop nav menu]  (hidden on mobile)
navbar-end:    [spinner] [theme toggle] [auth section]
```

**Target structure:**
```
navbar-start:  [logo/name link]
navbar-center: [desktop nav menu]  (hidden on mobile)
navbar-end:    [spinner] [theme toggle] [auth section] [hamburger dropdown]
```

Changes in `spa.html`:
- **Remove** the entire `<div class="dropdown">` block (hamburger + mobile nav `<ul>`) from `navbar-start`.
- **Keep** only the logo/name `<a>` link in `navbar-start`.
- **Add** a new mobile dropdown in `navbar-end`, **after** the `{% endif %}` that closes the OIDC conditional. The hamburger must be outside the conditional so it always renders (OIDC on or off). Use `dropdown dropdown-end` so the menu aligns to the right edge.
- The new mobile dropdown container will be an **empty `<ul>`** populated by JS (see Step 2), with the hamburger trigger button as a `<div tabindex="0" role="button">`.
- Keep `lg:hidden` on the hamburger trigger so it only appears on mobile.

### Step 2: Render mobile nav items via JS (eliminate inline SVGs)

All the icon functions already exist in `icons.js`:
- `iconHome()`, `iconDashboard()`, `iconNodes()`, `iconAdvertisements()`, `iconMessages()`, `iconMap()`, `iconMembers()`, `iconPage()`

Create a new `renderMobileNav()` function (in `app.js` or `components.js`) that:
1. Reads feature flags (`config.features`) and custom pages (`config.custom_pages`) from `window.__APP_CONFIG__`.
2. Builds the nav `<li>` items using lit-html, using the JS icon functions with a CSS class for the nav-icon color.
3. Renders into the mobile nav `<ul>` container element.
4. Sets `data-nav-link` attributes on `<a>` elements for active-state highlighting. SPA click navigation is handled automatically by the Router's document-level click listener.

This eliminates ~20 duplicated inline SVGs from the Jinja2 template.

### Step 3: Increase mobile nav dropdown sizes

The mobile nav dropdown currently uses `menu menu-sm` with `h-4 w-4` icons and `w-52` width.

Changes:
- Remove `menu-sm` from the mobile nav dropdown `<ul>` (use default `menu` for standard sizing).
- Increase dropdown width from `w-52` to `w-56`.
- Nav icons in mobile dropdown: render at `h-5 w-5` (up from `h-4 w-4`) via the JS icon function class parameter.
- Add CSS rule in `app.css` for slightly larger tap targets:

```css
@media (max-width: 1023px) {
    .navbar .dropdown .menu li > a {
        padding-top: 0.625rem;
        padding-bottom: 0.625rem;
        font-size: 0.9375rem; /* 15px, up from ~13px with menu-sm */
    }
}
```

### Step 4: Increase user profile dropdown sizes

The user profile dropdown in `components.js` (`renderAuthSection`) uses `menu menu-sm` with `h-4 w-4` icons.

Changes in `renderAuthSection()`:
- Change dropdown `<ul>` from `menu menu-sm` to `menu` (or keep `menu-sm` with CSS override).
- Increase dropdown width from `w-52` to `w-56`.
- Change icon class in profile/logout items from `h-4 w-4` to `h-5 w-5`.
- Optionally increase the avatar button and initials text slightly.

Add CSS for the user profile dropdown tap targets (same rule as Step 3, or a targeted one):

```css
@media (max-width: 1023px) {
    #auth-section .dropdown .menu li > a {
        padding-top: 0.625rem;
        padding-bottom: 0.625rem;
        font-size: 0.9375rem;
    }
}
```

### Step 5: Verify and test

- Rebuild frontend assets: `npm run build`
- Run targeted tests: `pytest tests/test_web/`
- Run quality checks: `pre-commit run --all-files`
- Visual verification on mobile viewport (browser DevTools) for:
  - Navbar order: logo left, controls + hamburger right
  - Mobile nav dropdown: larger text/icons/tap targets
  - User profile dropdown: larger text/icons/tap targets
  - Desktop nav: unchanged behavior

## Risk / Considerations

- **Jinja2 → JS nav rendering**: Feature flags, custom pages, and i18n translations are all confirmed available in `window.__APP_CONFIG__` and the `t()` translation function. The JS renderer will produce identical nav items to the Jinja2 template.
- **Desktop nav unchanged**: The `navbar-center` desktop horizontal menu stays as-is with inline SVGs in the Jinja2 template (it works fine, is not affected by the Tailwind size issue, and is not mobile).

## Summary of Size Changes

| Element | Before | After |
|---------|--------|-------|
| Mobile nav menu class | `menu menu-sm` | `menu` (default) |
| Mobile nav icon size | `h-4 w-4` (16px) | `h-5 w-5` (20px) |
| Mobile nav dropdown width | `w-52` (13rem) | `w-56` (14rem) |
| Mobile nav item font size | ~13px (menu-sm) | ~15px (menu default) |
| User dropdown menu class | `menu menu-sm` | `menu` (default) |
| User dropdown icon size | `h-4 w-4` (16px) | `h-5 w-5` (20px) |
| User dropdown width | `w-52` (13rem) | `w-56` (14rem) |
