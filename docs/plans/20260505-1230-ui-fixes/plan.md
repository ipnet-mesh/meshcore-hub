# Plan: DaisyUI v5 Form Class Migration + Homepage Hero Button Redesign

**Date:** 2026-05-05
**Branch:** `chore/ui-fixes`

---

## Background

The project uses Tailwind CSS v4 + DaisyUI v5 via a CSS-first build (`@plugin "daisyui"` in `input.css`). DaisyUI v5 **removed** several component classes that existed in v4:

| DaisyUI v4 Class       | v5 Status       | v5 Replacement                           |
|------------------------|-----------------|------------------------------------------|
| `.form-control`        | Removed         | `.fieldset` or Tailwind-native flex/grid |
| `.label-text`          | Removed         | `.fieldset-label` provides muted text    |
| `.label-text-alt`      | Removed         | Tailwind-native (e.g. `text-xs text-error`) |
| `.label`               | Still exists    | —                                        |
| `.btn`, `.card`, etc.  | Still exist     | —                                        |

The `.form-control` and `.label-text` classes are used in production code (`node-detail.js`, `map.js`) but produce **no CSS output** in the built `tailwind.css` since DaisyUI v5 does not generate them. This causes forms to render without proper layout styling.

Separately, the homepage hero section uses `btn btn-outline` for navigation buttons. The user wants a redesigned, more compact card-based layout.

---

## Root Cause Analysis

DaisyUI CSS **is** included in the build — the `@plugin "daisyui"` directive in `input.css` correctly loads DaisyUI v5 and generates all currently-supported component classes. The issue is that `form-control` and `label-text` were **deprecated and removed in DaisyUI v5**. DaisyUI v5's plugin no longer defines these classes, so they don't appear in `tailwind.css`.

**Evidence:**
- `tailwind.css` (101KB minified) contains `.label`, `.btn`, `.card`, `.navbar`, `.modal`, `.badge`, `.alert`, `.table`, `.fieldset`, `.fieldset-label`, `.fieldset-legend` and all other v5 components
- `form-control` and `label-text` do **not** appear anywhere in the built CSS
- The DaisyUI v5 source (`node_modules/daisyui/components/`) has no `form-control` component; it was replaced by `fieldset`

---

## Task 1: Replace `form-control` / `label-text` / `label-text-alt` with DaisyUI v5 + Tailwind-native equivalents

### Error display strategy

**Decision:** Error containers use `<div class="hidden text-xs text-error">`. The `hidden` class is toggled by JS handlers using `classList.remove('hidden')` / `classList.add('hidden')`. Error text is set via `textContent`.

### Files affected

#### A. `src/meshcore_hub/web/static/js/spa/pages/node-detail.js`

**Location 1 — Tag Edit Modal template (lines 50–61):**

Current (broken):
```js
<div class="form-control mb-4">
    <label class="label"><span class="label-text">${t('common.value')}</span></label>
    <input type="text" id="tagEditValue" class="input input-bordered">
    <label class="label" id="tagEditError"></label>
</div>
<div class="form-control mb-4">
    <label class="label"><span class="label-text">${t('common.type')}</span></label>
    <select id="tagEditType" class="select select-bordered w-full">
```

Change to:
```js
<div class="fieldset mb-4">
    <label class="fieldset-label">${t('common.value')}</label>
    <input type="text" id="tagEditValue" class="input input-bordered w-full">
    <div class="hidden text-xs text-error" id="tagEditError"></div>
</div>
<div class="fieldset mb-4">
    <label class="fieldset-label">${t('common.type')}</label>
    <select id="tagEditType" class="select select-bordered w-full">
```

**Location 2 — Add Tag Form template (lines 228–233):**

Current (broken):
```js
<div class="form-control">
    <input type="text" name="key" class="input input-bordered input-sm" placeholder=${t('common.key')} required>
</div>
<div class="form-control">
    <input type="text" name="value" class="input input-bordered input-sm" placeholder=${t('common.value')}>
    <label class="label" id="tagAddError"></label>
</div>
```

Change to:
```js
<div class="fieldset">
    <input type="text" name="key" class="input input-bordered input-sm w-full" placeholder=${t('common.key')} required>
</div>
<div class="fieldset">
    <input type="text" name="value" class="input input-bordered input-sm w-full" placeholder=${t('common.value')}>
    <div class="hidden text-xs text-error" id="tagAddError"></div>
</div>
```

**Location 3 — JS validation error handlers:**

All error display logic changes from `innerHTML` with `label-text-alt` spans to `textContent` + `hidden` class toggling.

Line 446 — add tag form validation error:
```js
// Before:
if (errEl) errEl.innerHTML = `<span class="label-text-alt text-error">${validationError}</span>`;
// After:
if (errEl) { errEl.textContent = validationError; errEl.classList.remove('hidden'); }
```

Line 449 — add tag form error clear:
```js
// Before:
if (errEl) errEl.innerHTML = '';
// After:
if (errEl) { errEl.textContent = ''; errEl.classList.add('hidden'); }
```

Line 476 — edit modal error clear (on modal open):
```js
// Before:
if (errorLabel) errorLabel.innerHTML = '';
// After:
if (errorLabel) { errorLabel.textContent = ''; errorLabel.classList.add('hidden'); }
```

Line 493 — edit form validation error:
```js
// Before:
if (errorLabel) errorLabel.innerHTML = `<span class="label-text-alt text-error">${validationError}</span>`;
// After:
if (errorLabel) { errorLabel.textContent = validationError; errorLabel.classList.remove('hidden'); }
```

Line 496 — edit form error clear:
```js
// Before:
if (errorLabel) errorLabel.innerHTML = '';
// After:
if (errorLabel) { errorLabel.textContent = ''; errorLabel.classList.add('hidden'); }
```

Line 504 — edit form API error:
```js
// Before:
if (errorLabel) errorLabel.innerHTML = `<span class="label-text-alt text-error">${err.message}</span>`;
// After:
if (errorLabel) { errorLabel.textContent = err.message; errorLabel.classList.remove('hidden'); }
```

#### B. `src/meshcore_hub/web/static/js/spa/pages/map.js`

**Location — Map filters (lines 198–238):**

Each filter uses the pattern:
```js
<div class="form-control">
    <label class="label py-1">
        <span class="label-text">${t('common.show')}</span>
    </label>
    <select class="select select-bordered select-sm" @change=${applyFilters}>
```

Change all four filter blocks to use `fieldset`:
```js
<div class="fieldset">
    <label class="fieldset-label">${t('common.show')}</label>
    <select class="select select-bordered select-sm" @change=${applyFilters}>
```

For the checkbox filter (lines 234–238), which uses `label.cursor-pointer.gap-2.py-1` with an inline checkbox, keep the label structure but change to fieldset:
```js
<div class="fieldset">
    <label class="fieldset-label cursor-pointer gap-2">
        <span>${t('map.show_labels')}</span>
        <input type="checkbox" id="show-labels" class="checkbox checkbox-sm" @change=${updateLabelVisibility}>
    </label>
</div>
```

### Testing

- Visual verification: build frontend (`npm run build`), run the app, navigate to:
  - A node detail page → verify the inline tag editor form and modal render correctly
  - Trigger validation errors → verify error text appears and clears correctly
  - Map page → verify filter controls render with proper spacing
- Run targeted tests: `pytest tests/test_web/ -v`

---

## Task 2: Redesign Homepage Hero Navigation Buttons

### Current State

The hero section in `home.js:30-94` renders navigation buttons as DaisyUI `btn btn-outline` with horizontal icon+text layout:

```js
<a href="/dashboard" class="btn btn-outline btn-info">
    ${iconDashboard('h-5 w-5 mr-2')}
    ${t('entities.dashboard')}
</a>
```

These are arranged in a `flex flex-wrap justify-center gap-3` container.

### Target Design

Each nav item should be a **square-ish card** with:
1. **Border:** Low-contrast rounded border, respecting dark/light mode (`border border-base-content/20`)
2. **Icon:** Larger, centered in the box, using existing section colors (via CSS custom properties `--color-*`)
3. **Label:** Below the icon, high-contrast text (`text-base-content`)
4. **Hover:** Subtle scale-up animation (`hover:scale-105 transition-all duration-200`)

### Implementation Plan

#### A. Changes to `home.js` — `renderHeroSection()`

Replace the flex-wrap row of `btn btn-outline` links with a grid of card-link elements.

**Placement:** Add `renderNavCard()` as a module-level function in `home.js`, after `renderRadioConfig()` (line 28) and before `renderHeroSection()` (line 30).

**New render function for a single nav card:**

```js
function renderNavCard({ href, icon, label, colorVar }) {
    return html`
        <a href="${href}" class="w-28 h-28 sm:w-32 sm:h-32
            border border-base-content/20 rounded-box
            hover:scale-105 hover:border-base-content/40
            transition-all duration-200 ease-out
            flex flex-col items-center justify-center gap-2
            bg-base-200/50 hover:bg-base-200
            group">
            <span class="w-8 h-8 sm:w-10 sm:h-10 flex items-center justify-center"
                  style="color: var(${colorVar})">
                ${icon}
            </span>
            <span class="text-xs sm:text-sm font-medium text-base-content">
                ${label}
            </span>
        </a>`;
}
```

Note: `block` removed (overridden by `flex`); `group-hover:text-base-content` removed (no-op since already `text-base-content`).

**Color variable mappings** (matching existing section colors from `app.css`):

| Feature     | CSS Variable        | Notes |
|-------------|---------------------|-------|
| Dashboard   | `--color-dashboard` | cyan |
| Nodes       | `--color-nodes`     | violet |
| Adverts     | `--color-adverts`   | magenta |
| Messages    | `--color-messages`  | teal |
| Members     | `--color-members`   | orange |
| Map         | `--color-map`       | yellow |
| Custom Page | (none)              | Uses `base-content` (default text color) — no `colorVar` style attribute |

**Updated hero section nav area:**

```js
<div class="flex flex-wrap justify-center gap-3 sm:gap-4 mt-auto">
    ${features.dashboard !== false ? renderNavCard({
        href: '/dashboard',
        icon: iconDashboard('w-full h-full'),
        label: t('entities.dashboard'),
        colorVar: '--color-dashboard',
    }) : nothing}
    ${features.nodes !== false ? renderNavCard({
        href: '/nodes',
        icon: iconNodes('w-full h-full'),
        label: t('entities.nodes'),
        colorVar: '--color-nodes',
    }) : nothing}
    ${features.advertisements !== false ? renderNavCard({
        href: '/advertisements',
        icon: iconAdvertisements('w-full h-full'),
        label: t('entities.advertisements'),
        colorVar: '--color-adverts',
    }) : nothing}
    ${features.messages !== false ? renderNavCard({
        href: '/messages',
        icon: iconMessages('w-full h-full'),
        label: t('entities.messages'),
        colorVar: '--color-messages',
    }) : nothing}
    ${features.members !== false ? renderNavCard({
        href: '/members',
        icon: iconMembers('w-full h-full'),
        label: t('entities.members'),
        colorVar: '--color-members',
    }) : nothing}
    ${features.map !== false ? renderNavCard({
        href: '/map',
        icon: iconMap('w-full h-full'),
        label: t('entities.map'),
        colorVar: '--color-map',
    }) : nothing}
    ${features.pages !== false ? customPages.slice(0, 3).map(page => renderNavCard({
        href: page.url,
        icon: iconPage('w-full h-full'),
        label: page.title,
        colorVar: '',
    })) : nothing}
</div>
```

For custom pages: when `colorVar` is empty string, `style="color: var()"` is invalid CSS and the browser ignores it. The icon's `stroke="currentColor"` will inherit from the parent's `text-base-content`, which provides correct contrast in both themes. Alternatively, conditionally render the `style` attribute only when `colorVar` is truthy.

#### B. Changes to `app.css` — Remove btn-outline hero overrides

Remove these rules from `app.css` (lines 88–97):

```css
#app .btn-outline {
    border-width: 2px;
}
#app .btn-outline:hover {
    color: #fff !important;
}
.btn-hero-members {
    --btn-color: var(--color-members);
    --btn-border-color: var(--color-members);
}
```

**Complete inventory of `btn-outline` usages affected by this removal:**

| File | Line | Button | Visual change |
|------|------|--------|---------------|
| `home.js` | 62-87 | Hero nav buttons | Removed entirely (replaced by cards) |
| `home.js` | 201, 205 | Attribution "Website" / "GitHub" | Thinner border, no forced white on hover |
| `components.js` | 611 | Navbar "Login" button | Thinner border, no forced white on hover |
| `not-found.js` | 19 | "View Nodes" button | Thinner border, no forced white on hover |
| `node-detail.js` | 594 | "Release" button (adoption section) | Thinner border, no forced white on hover |
| `map.js` | 115 | Popup "View Details" link | Thinner border, no forced white on hover |

All affected buttons revert to DaisyUI v5's default `btn-outline` styling. **Verify visually** after removal — these buttons should look correct in both dark and light themes.

#### C. Icon size considerations

Icons in the current hero use `h-5 w-5 mr-2`. For the new cards, icons fill the container span (`w-8 h-8` on mobile, `sm:w-10 sm:h-10` on larger screens). Pass `'w-full h-full'` to each icon function so the SVG fills the span.

All icon functions in `icons.js` follow the pattern:
```js
function iconFoo(cls = 'h-5 w-5') {
    return html`<svg class=${cls} fill="none" viewBox="0 0 24 24" stroke="currentColor">...</svg>`;
}
```

Verified: `iconDashboard`, `iconNodes`, `iconAdvertisements`, `iconMessages`, `iconMembers`, `iconMap`, `iconPage` all accept `cls` and use `stroke="currentColor"`.

### Testing

- Build frontend: `npm run build`
- Visual check: all 6-9 nav cards render in a responsive grid
- Verify hover animation works (scale + border color transition)
- Verify dark/light mode: labels readable in both, icon colors from CSS vars
- Verify custom page cards: icons visible (should use `base-content` color)
- Check mobile layout: cards should wrap to 3-4 per row on small screens
- Verify all `btn-outline` buttons listed in the inventory above look correct with DaisyUI defaults
- Run `pytest tests/test_web/ -v`

---

## Implementation Order

Apply changes bottom-to-top within each file to avoid line number drift:

1. **Task 1** — Fix `form-control`/`label-text` in `node-detail.js` (JS handlers first, then template) and `map.js`
2. **Task 2** — Redesign homepage hero buttons in `home.js` (add `renderNavCard`, update `renderHeroSection`) + remove CSS from `app.css`
3. Build frontend: `npm run build`
4. Run tests: `pytest tests/test_web/ -v`
5. Run pre-commit: `pre-commit run --all-files`
6. Manual visual verification in browser

---

## Risks / Mitigations

| Risk | Mitigation |
|------|-----------|
| `.fieldset` has `font-size: 0.75rem` which cascades to children | Verify inputs/selects inside fieldset render at correct size; add `text-base` to inputs if needed |
| Custom page labels may overflow small cards | Use `truncate` class on label text |
| Map filter layout may shift with fieldset | Fieldset uses similar grid layout; verify visually |
| `style="color: var()"` on custom page icons is invalid CSS | Conditionally render `style` attribute only when `colorVar` is truthy, or accept browser ignoring it (falls back to `currentColor`) |
| Removing `#app .btn-outline` affects 6 non-hero buttons | All revert to DaisyUI defaults; verify visually in both themes |
