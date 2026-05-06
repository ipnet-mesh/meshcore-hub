# Tasks: Markdown Nested Lists & Map Collapsible Filters

## Part A: Fix Markdown Prose Styling

- [ ] Add `.prose > :first-child { margin-top: 0; }` to `app.css` after the `.prose` block (after line 256)
- [ ] Add nested list CSS rules to `app.css` after the `.prose li` block (line 215)
- [ ] Update `docs/content.md` with "Supported Markdown Features" section
- [ ] Add nested list HTML output test to `tests/test_web/test_pages.py`
- [ ] Run `pytest tests/test_web/test_pages.py`
- [ ] Run `pre-commit run --all-files`

## Part B: Map Page Collapsible Filters

- [ ] Add `isFilterOpen` state persistence logic before `litRender()` in `map.js`
- [ ] Replace hardcoded `<div class="card">` filter card (lines 195-237) with collapsible `<details>` in `map.js`
- [ ] Verify all existing filter logic preserved (`applyFilters`, `clearFiltersHandler`, show-labels, member filter)
- [ ] Manual: load map page, verify filter collapses/expands, survives re-render after filter changes
