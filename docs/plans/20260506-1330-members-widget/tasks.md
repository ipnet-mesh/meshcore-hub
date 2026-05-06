# Task List: Members Widget on Homepage + MeshCore Logo in Footer

**Plan**: [plan.md](./plan.md)

---

## Tasks

### 1. Extend `DashboardStats` schema

- [ ] Add `total_operators: int = Field(default=0, ...)` and `total_members: int = Field(default=0, ...)` to `DashboardStats` in `src/meshcore_hub/common/schemas/messages.py:244`

### 2. Add member count queries to dashboard endpoint

- [ ] In `src/meshcore_hub/api/routes/dashboard.py`, import `UserProfile` from `meshcore_hub.common.models` and `Settings` from `meshcore_hub.common.config`
- [ ] In `get_stats()`, add two count queries: operators (`roles.contains(operator_role)`) and members (`roles.contains(member_role) AND ~roles.contains(operator_role)`)
- [ ] Pass `total_operators` and `total_members` to the `DashboardStats()` return at line 203

### 3. Replace MeshCore card with Members panel in `home.js`

- [ ] Add `showMembersPanel = features.members !== false` variable (after `showActivityChart` at line 188)
- [ ] Create `renderMembersPanel({ features, stats })` function with two `renderStatCard()` tiles (operators/members)
- [ ] Replace the inline MeshCore card HTML (lines 223–241) with `${renderMembersPanel({ features, stats })}`
- [ ] Update grid class (line 210): change `${showActivityChart ? 'lg:grid-cols-3' : ''}` to `${showMembersPanel && showActivityChart ? 'lg:grid-cols-3' : ''}`
- [ ] Update imports: add `iconAntenna`, `iconUsers`; remove `iconGlobe`, `iconGithub`

### 4. Restructure footer in `spa.html`

- [ ] Replace `footer footer-center` (line 113) with two-column layout: left side = MeshCore branding (logo `h-5` + text links), right side = existing network/hub info
- [ ] Use `order-2 lg:order-1` / `order-1 lg:order-2` for mobile stacking (MeshCore on top)

### 5. Add footer CSS

- [ ] Add `footer.footer { justify-content: space-between; align-items: center; }` to `src/meshcore_hub/web/static/css/app.css`

### 6. Remove orphaned i18n key

- [ ] Remove `home.meshcore_attribution` from `src/meshcore_hub/web/static/locales/en.json`
- [ ] Remove `home.meshcore_attribution` from `src/meshcore_hub/web/static/locales/nl.json`

### 7. Update i18n docs

- [ ] Remove `meshcore_attribution` entry from `docs/i18n.md:247`

### 8. Test

- [ ] Run `pytest tests/test_api/ -v` (dashboard stats changes)
- [ ] Run `pytest tests/test_web/ -v` (homepage rendering)
- [ ] Run `pre-commit run --all-files`
- [ ] Visual: verify Members panel renders with correct counts, footer shows two-column layout, mobile stacks correctly, OIDC-disabled shows zeros
