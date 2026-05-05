# Tasks: DaisyUI v5 Form Class Migration + Homepage Hero Button Redesign

**Plan:** [plan.md](plan.md)
**Branch:** `chore/ui-fixes`

---

## 1. Fix `form-control` / `label-text` in `node-detail.js`

### 1a. Update JS validation error handlers (bottom-to-top)

- [ ] **Line 504** — Edit form API error: replace `innerHTML` with `textContent` + `classList.remove('hidden')`
- [ ] **Line 496** — Edit form error clear: replace `innerHTML = ''` with `textContent = ''` + `classList.add('hidden')`
- [ ] **Line 493** — Edit form validation error: replace `innerHTML` with `textContent` + `classList.remove('hidden')`
- [ ] **Line 476** — Edit modal error clear (on modal open): replace `innerHTML = ''` with `textContent = ''` + `classList.add('hidden')`
- [ ] **Line 449** — Add tag form error clear: replace `innerHTML = ''` with `textContent = ''` + `classList.add('hidden')`
- [ ] **Line 446** — Add tag form validation error: replace `innerHTML` with `textContent` + `classList.remove('hidden')`

### 1b. Replace template markup

- [ ] **Lines 50–61** — Tag Edit Modal: replace `form-control` divs with `fieldset`, replace `<label class="label"><span class="label-text">` with `<label class="fieldset-label">`, replace `<label class="label" id="tagEditError">` with `<div class="hidden text-xs text-error" id="tagEditError">`
- [ ] **Lines 228–233** — Add Tag Form: replace `form-control` divs with `fieldset`, replace `<label class="label" id="tagAddError">` with `<div class="hidden text-xs text-error" id="tagAddError">`

## 2. Fix `form-control` / `label-text` in `map.js`

- [ ] **Lines 198–238** — Map filters: replace all `form-control` divs with `fieldset`, replace `<label class="label py-1"><span class="label-text">` with `<label class="fieldset-label">`
- [ ] **Lines 234–238** — Checkbox filter: replace `form-control` with `fieldset`, keep `cursor-pointer gap-2` on label

## 3. Redesign homepage hero buttons in `home.js`

- [ ] Add `renderNavCard()` function after `renderRadioConfig()` (line 28), before `renderHeroSection()` (line 30)
- [ ] Update `renderHeroSection()` nav area: replace `btn btn-outline` links with `renderNavCard()` calls for all 6 features + custom pages

## 4. Remove `btn-outline` CSS overrides from `app.css`

- [ ] Remove `#app .btn-outline` rule (border-width + forced white hover)
- [ ] Remove `.btn-hero-members` rule (color custom properties)

## 5. Build and verify

- [ ] `npm run build`
- [ ] `pytest tests/test_web/ -v`
- [ ] `pre-commit run --all-files`
- [ ] Manual visual verification in browser (both dark and light themes):
  - Node detail page: tag add/edit forms render correctly, errors show/hide
  - Map page: filter controls render with proper spacing
  - Homepage: 6-9 nav cards render in responsive grid, hover animation works
  - Custom page cards: icons visible
  - All `btn-outline` buttons (login, 404, release, attribution, popup details) look correct with DaisyUI defaults
