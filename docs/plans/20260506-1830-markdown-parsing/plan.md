# Plan: Markdown Nested Lists & Map Collapsible Filters

Date: 2026-05-06

## Part A: Fix Markdown Prose Styling

### Problem

Two CSS issues in custom markdown pages:

1. **Excessive top spacing** — The first element inside `.prose` (typically an `<h1>`) gets both the DaisyUI `card-body` padding AND its own `margin-top: 1.5rem`, creating a large gap before content starts. The `.prose h1` rule at `app.css:166` applies `margin-top: 1.5rem` unconditionally.

2. **No nested list differentiation** — All list levels use the same bullet style (`disc`) because the `.prose` CSS in `app.css:199-215` only styles `ul`, `ol`, and `li` at a single level. Python-Markdown correctly generates nested `<ul>`/`<ol>` HTML — the issue is CSS-only.

### Changes

#### 1. Remove top margin on first prose child (`app.css`)

Add after the `.prose` block (after line 256, the closing brace):

```css
.prose > :first-child {
    margin-top: 0;
}
```

This eliminates the double-spacing (card-body padding + h1 margin-top) for the first element. Subsequent headings still get their normal `margin-top` for visual separation between sections.

**Specificity note:** `.prose > :first-child` and `.prose h1` have identical specificity (0-1-1). This rule works only because it appears later in the source. Avoid adding new heading styles after this rule — the top-margin override would silently break.

#### 2. Add nested list CSS to `app.css`

Add after the `.prose li` block (line 215):

```css
.prose ul ul { list-style-type: circle; }
.prose ul ul ul { list-style-type: square; }
.prose ol ol { list-style-type: lower-alpha; }
.prose ol ol ol { list-style-type: lower-roman; }
.prose ul ul, .prose ul ol,
.prose ol ul, .prose ol ol { margin-top: 0.25rem; margin-bottom: 0; }
```

This provides:
- Level 1: disc / decimal
- Level 2: circle / lower-alpha
- Level 3+: square / lower-roman

#### 3. Update `docs/content.md`

Add a "Supported Markdown Features" section documenting:
- Basic formatting (headings, bold, italic, links)
- Lists (ordered, unordered, nested)
- Tables (pipe-delimited)
- Code blocks (fenced with triple backticks, optional language)
- Table of contents (`[TOC]` marker)
- Images (require absolute paths to `/media/`)

### Files

| File | Change |
|------|--------|
| `src/meshcore_hub/web/static/css/app.css` | Add `:first-child` rule + nested list CSS rules |
| `docs/content.md` | Add markdown features section |
| `tests/test_web/test_pages.py` | Add test for nested list HTML output |

---

## Part B: Map Page Collapsible Filters

### Problem

The map page (`src/meshcore_hub/web/static/js/spa/pages/map.js:195-237`) uses a hardcoded non-collapsible filter card:

```html
<div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
```

Other list pages (nodes, messages, advertisements) use `renderFilterCard()` from `components.js:724-766` with `collapsible: true`, which renders as:

```html
<details class="collapse collapse-arrow bg-base-200 border-2 border-base-content/25 rounded-box mb-6">
```

The map page is inconsistent with the rest of the SPA.

### Approach

Wrap the map's existing filter controls in the same collapsible `<details>` DaisyUI pattern, but keep the map's custom client-side filter logic. Do **not** refactor to use `renderFilterCard()` — the map has unique behaviors (client-side filtering, show-labels toggle, member filter triggers API re-fetch) that don't fit the shared component's server-side form submission model.

### Changes

#### 1. Replace filter card HTML in `map.js`

Replace lines 195-237 (the hardcoded `<div class="card">`) with:

```html
<details class="collapse collapse-arrow bg-base-200 border-2 border-base-content/25 rounded-box mb-6"
         ?open=${isFilterOpen}>
    <summary class="collapse-title text-sm font-medium cursor-pointer">
        ${t('common.filters')}
    </summary>
    <div class="collapse-content pt-4">
        <div class="flex gap-4 flex-wrap items-end">
            <!-- existing filter controls unchanged -->
        </div>
    </div>
</details>
```

#### 2. Add collapsible state persistence

Before the `litRender()` call, add the same pattern used by other pages:

```javascript
const existingDetails = container.querySelector('details.collapse');
const isFilterOpen = existingDetails ? existingDetails.open : false;
```

**Behavior note:** On first visit (no prior DOM state), the filter starts **closed**. This is consistent with all other list pages (nodes, messages, advertisements), but is a change from the current map behavior where the filter card is always visible. Users who want to see filters will need to click to expand — same as every other page in the SPA.

**Re-render note:** State persistence works because `container.querySelector` inspects the pre-existing DOM before `litRender` replaces content. If the map ever re-renders on every pan/zoom (not just filter changes), the filter would collapse on each re-render. The current map only re-renders on filter changes, so this is not an issue.

#### 3. Preserve all existing filter logic

- `applyFilters()` / `applyFiltersCore()` — unchanged
- `@change=${applyFilters}` event handlers — unchanged
- `clearFiltersHandler()` — unchanged
- Show-labels checkbox — unchanged
- Member filter re-fetch logic — unchanged

### Files

| File | Change |
|------|--------|
| `src/meshcore_hub/web/static/js/spa/pages/map.js` | Replace filter card HTML with collapsible `<details>`, add state persistence |

---

## Testing

- `pytest tests/test_web/test_pages.py` — verify Python-Markdown generates nested `<ul>`/`<ol>` HTML for indented markdown (NOT CSS rendering)
- `pre-commit run --all-files` — quality checks
- Manual: create a test `.md` page with nested lists, verify visual rendering with different bullet/indentation levels
- Manual: load map page, verify filter section collapses/expands correctly, survives re-render after filter changes
