# Plan: Members Widget on Homepage + MeshCore Logo in Footer

**Date**: 2026-05-06
**Status**: Draft

---

## Summary

Two changes to the homepage and footer:

1. **Members Widget** — Replace the MeshCore logo/links card on the homepage with a new panel containing two stat tiles showing **operator count** and **member count**, derived from role data in the `UserProfile` table.

2. **MeshCore Logo in Footer** — Move the existing MeshCore logo and project links from the homepage card into the footer bar. The footer becomes a two-column layout: MeshCore branding left-aligned, existing IPNet/MeshCore Hub info right-aligned. On mobile, MeshCore content stacks above the Hub info.

---

## Current State

### Homepage — MeshCore Attribution Card

At `home.js:222–241`, a full-width card in the second row of the grid shows:

```
┌──────────────────────────────────────┐
│                                      │
│     "Off-Grid, Open-Source           │
│      Encrypted Messaging"            │
│                                      │
│          [MeshCore Logo]             │
│                                      │
│   [Website btn]  [GitHub btn]        │
│                                      │
└──────────────────────────────────────┘
```

This card occupies one slot in the `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` bottom row alongside the Network Info card and Activity Chart card.

### Homepage — Stats Panel

At `home.js:126–151`, the right column of the hero area shows three stat cards: Total Nodes, Advertisements (7d), Messages (7d). There are **no member/operator counts**.

### Dashboard Stats API

`GET /api/v1/dashboard/stats` (`dashboard.py:24–180`) returns `DashboardStats` (`messages.py:244–269`) with node, message, and advertisement counts. **No member/profile counts** are included.

### Footer

`spa.html:112–140` — A `footer-center` footer showing:
- Network name + city/country
- Contact links (email, discord, github, youtube)
- "Powered by MeshCore Hub {version}"

All content is center-aligned. No MeshCore branding present.

### UserProfile Model

`user_profile.py:14–74` — `roles` field is a `Text` column containing comma-separated role strings (e.g. `"operator,member"`). The `role_list` property parses these into a `list[str]`.

### Members Page — Role Grouping Logic

`members.js:69–92` — Fetches `/api/v1/user/profiles?limit=500`, then groups:
- **Operators**: profiles where `roles` includes the operator role name
- **Members**: profiles where `roles` includes the member role name AND excludes operators

### Key Files

| File | Role |
|------|------|
| `src/meshcore_hub/web/static/js/spa/pages/home.js` | Homepage layout; MeshCore card at lines 222–241; stats panel at lines 126–151 |
| `src/meshcore_hub/web/static/js/spa/pages/members.js` | Members page; role grouping logic at lines 69–92 |
| `src/meshcore_hub/web/templates/spa.html` | Footer at lines 112–140 |
| `src/meshcore_hub/web/static/css/app.css` | Color palette, panel glow, footer styles |
| `src/meshcore_hub/web/static/js/spa/components.js` | `renderStatCard()`, `pageColors`, `t()` |
| `src/meshcore_hub/web/static/js/spa/icons.js` | SVG icon functions |
| `src/meshcore_hub/api/routes/dashboard.py` | Dashboard stats endpoint at line 24 |
| `src/meshcore_hub/common/schemas/messages.py` | `DashboardStats` schema at line 244 |
| `src/meshcore_hub/common/models/user_profile.py` | `UserProfile` model with `roles` field |
| `src/meshcore_hub/web/static/locales/en.json` | i18n strings |

---

## Target State

### 1. Homepage — Replace MeshCore Card with Members Widget

The MeshCore attribution card (currently `home.js:222–241`) is replaced with a **Members panel** containing two stat tiles:

```
┌──────────────────────────────────────┐
│  👥 Members                          │
│                                      │
│  ┌──────────────┐ ┌──────────────┐   │
│  │    [icon]    │ │    [icon]    │   │
│  │  Operators   │ │   Members    │   │
│  │      3       │ │      12      │   │
│  └──────────────┘ └──────────────┘   │
│                                      │
└──────────────────────────────────────┘
```

Each tile uses the existing `renderStatCard()` component (or a simplified variant) with the `--color-members` accent. The tiles show:
- **Operators**: count of `UserProfile` rows where `roles` contains the operator role
- **Members**: count of `UserProfile` rows where `roles` contains the member role AND excludes operators

When OIDC is disabled (no `user_profiles` table populated), the panel shows "0" for both counts (graceful degradation — no error).

### 2. Footer — Two-Column Layout with MeshCore Branding

The footer changes from a centered single-column to a **horizontal two-column layout**:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [MeshCore Logo]  Website · GitHub           IPNet Network  │
│                                     City, Country            │
│                                     email | discord | github │
│                                     Powered by MeshCore Hub  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Desktop (`lg+`)**:
- **Left side**: Small MeshCore logo + plain text links ("Website" and "GitHub")
- **Right side**: Existing footer content (network name, contacts, powered-by)

**Mobile (< `lg`)**:
- MeshCore content stacks on top
- Hub/network content below
- Both center-aligned (matching current mobile behaviour)

**MeshCore logo changes**:
- Smaller than the homepage version: `h-5` (20px) instead of `h-8`
- Links are plain `<a>` text links with `link link-hover` class — not `btn btn-outline btn-sm` buttons
- Separator between links is a middot (`·`)

---

## Implementation Plan

### Step 1: Add Member Counts to Dashboard Stats API

**Files**: `dashboard.py`, `messages.py`

#### 1a. Extend `DashboardStats` schema

Add two optional fields to `DashboardStats` in `messages.py:244`:

```python
total_operators: int = Field(default=0, description="Number of operator-role users")
total_members: int = Field(default=0, description="Number of member-role users (excluding operators)")
```

Both default to `0` so the response is backward-compatible when OIDC is disabled or the table is empty.

#### 1b. Add count queries to `get_stats()`

In `dashboard.py:24`, add queries after the existing stats:

```python
from meshcore_hub.common.models import UserProfile
from meshcore_hub.common.config import Settings

settings = Settings()
operator_role = settings.oidc_role_operator
member_role = settings.oidc_role_member

# Count operators (roles contains operator role)
total_operators = (
    session.execute(
        select(func.count())
        .select_from(UserProfile)
        .where(UserProfile.roles.contains(operator_role))
    ).scalar()
    or 0
)

# Count members (roles contains member role AND does NOT contain operator role)
total_members = (
    session.execute(
        select(func.count())
        .select_from(UserProfile)
        .where(
            UserProfile.roles.contains(member_role),
            ~UserProfile.roles.contains(operator_role),
        )
    ).scalar()
    or 0
)
```

Include `total_operators` and `total_members` in the returned `DashboardStats` instance.

**Note**: The `roles` column is comma-separated text. Using `contains()` is a SQLite `LIKE` substring match — the same pattern already used in `metrics.py:309` for `UserProfile.roles.contains(role)`. This is acceptable for the small dataset sizes expected.

### Step 2: Replace MeshCore Card with Members Panel in Homepage

**File**: `home.js`

#### 2a. Add new `renderMembersPanel()` function

Create a new function that renders two stat tiles for operators and members:

```javascript
function renderMembersPanel({ features, stats }) {
    if (features.members === false) return nothing;
    return html`
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">
                    ${iconMembers('h-6 w-6')}
                    ${t('entities.members')}
                </h2>
                <div class="grid grid-cols-2 gap-4 mt-2">
                    ${renderStatCard({
                        icon: iconAntenna('h-6 w-6'),
                        color: pageColors.members,
                        title: t('members_page.operators'),
                        value: stats.total_operators ?? 0,
                    })}
                    ${renderStatCard({
                        icon: iconUsers('h-6 w-6'),
                        color: pageColors.members,
                        title: t('members_page.members'),
                        value: stats.total_members ?? 0,
                    })}
                </div>
            </div>
        </div>`;
}
```

#### 2b. Replace the MeshCore attribution card and update grid condition

In the `render()` function's template (lines 210–244):

1. Replace the inline MeshCore card HTML (lines 223–241) with:
   ```javascript
   ${renderMembersPanel({ features, stats })}
   ```

2. Update the grid class at line 210. Currently the `lg:grid-cols-3` condition only checks `showActivityChart`. Since the Members panel is now feature-gated (was always-present MeshCore card), the 3-column layout should only apply when BOTH the Members panel AND the Activity Chart are visible:
   ```javascript
   const showMembersPanel = features.members !== false;
   <div class="grid grid-cols-1 md:grid-cols-2 ${showMembersPanel && showActivityChart ? 'lg:grid-cols-3' : ''} gap-6 mt-6">
   ```

#### 2c. Update imports

- **Add**: `iconAntenna` and `iconUsers` to the import from `icons.js`
- **Remove**: `iconGlobe` and `iconGithub` from the import (only used by the now-removed MeshCore card)

### Step 3: Move MeshCore Branding to Footer

**File**: `spa.html`

#### 3a. Restructure footer markup

Replace the current footer (lines 112–140) with a two-column layout:

```html
<footer class="footer p-4 bg-base-100 text-base-content mt-auto">
    <!-- Left: MeshCore branding (stacks on top on mobile) -->
    <div class="flex flex-col items-center lg:items-start gap-1 order-2 lg:order-1">
        <div class="flex items-center gap-2">
            <a href="https://meshcore.io/" target="_blank" rel="noopener noreferrer" class="hover:opacity-80 transition-opacity">
                <img src="/static/img/meshcore.svg" alt="MeshCore" class="theme-logo theme-logo--invert-light h-5" />
            </a>
            <span class="text-xs opacity-50">Off-Grid, Open-Source Encrypted Messaging</span>
        </div>
        <div class="flex gap-2 text-xs">
            <a href="https://meshcore.io/" target="_blank" rel="noopener noreferrer" class="link link-hover opacity-70">{{ t('links.website') }}</a>
            <span class="opacity-30">·</span>
            <a href="https://github.com/meshcore-dev/MeshCore" target="_blank" rel="noopener noreferrer" class="link link-hover opacity-70">{{ t('links.github') }}</a>
        </div>
    </div>

    <!-- Right: Network info + Hub attribution -->
    <div class="flex flex-col items-center lg:items-end gap-1 order-1 lg:order-2">
        <p>
            {{ network_name }}
            {% if network_city and network_country %}
            — {{ network_city }}, {{ network_country }}
            {% endif %}
        </p>
        <p class="text-sm opacity-70">
            {% if network_contact_email %}
            <a href="mailto:{{ network_contact_email }}" class="link link-hover">{{ network_contact_email }}</a>
            {% endif %}
            {% if network_contact_email and network_contact_discord %} | {% endif %}
            {% if network_contact_discord %}
            <a href="{{ network_contact_discord }}" target="_blank" rel="noopener noreferrer" class="link link-hover">{{ t('links.discord') }}</a>
            {% endif %}
            {% if (network_contact_email or network_contact_discord) and network_contact_github %} | {% endif %}
            {% if network_contact_github %}
            <a href="{{ network_contact_github }}" target="_blank" rel="noopener noreferrer" class="link link-hover">{{ t('links.github') }}</a>
            {% endif %}
            {% if (network_contact_email or network_contact_discord or network_contact_github) and network_contact_youtube %} | {% endif %}
            {% if network_contact_youtube %}
            <a href="{{ network_contact_youtube }}" target="_blank" rel="noopener noreferrer" class="link link-hover">{{ t('links.youtube') }}</a>
            {% endif %}
        </p>
        <p class="text-xs opacity-50 mt-1">{{ t('footer.powered_by') }} <a href="https://github.com/ipnet-mesh/meshcore-hub" target="_blank" rel="noopener noreferrer" class="link link-hover">MeshCore Hub</a> {{ version }}</p>
    </div>
</footer>
```

**Key changes**:
- `footer-center` → `footer` (remove center alignment to allow two columns)
- DaisyUI `footer` class provides `flex flex-wrap` which enables the two-column layout
- `order-2 lg:order-1` / `order-1 lg:order-2` ensures MeshCore stacks on top on mobile
- Logo is `h-5` (smaller than the `h-8` from the homepage card)
- Links are plain `<a class="link link-hover">` — no buttons

#### 3b. Add footer CSS (if needed)

The DaisyUI `footer` component already provides flex-wrap layout. Minimal custom CSS should be needed. If the default spacing needs adjustment, add to `app.css`:

```css
/* Footer two-column layout */
footer.footer {
    justify-content: space-between;
    align-items: center;
}
```

### Step 4: i18n Updates

**File**: `en.json` (and check `nl.json` for the same key)

No new keys required — reuse existing:
- `entities.members` = "Members"
- `members_page.operators` = "Operators"
- `members_page.members` = "Members"
- `links.website` = "Website"
- `links.github` = "GitHub"
- `footer.powered_by` = "Powered by"

Remove orphaned key (no longer referenced after MeshCore card removal):
- `home.meshcore_attribution` = "Our local off-grid mesh network is made possible by"

### Step 5: Update `docs/i18n.md`

Remove the `home.meshcore_attribution` key from the i18n reference if documented.

---

## Files Changed — Summary

| File | Change |
|------|--------|
| `src/meshcore_hub/common/schemas/messages.py` | Add `total_operators` and `total_members` fields to `DashboardStats` |
| `src/meshcore_hub/api/routes/dashboard.py` | Add UserProfile count queries for operators and members; import `UserProfile` model and `Settings` |
| `src/meshcore_hub/web/static/js/spa/pages/home.js` | Replace MeshCore card with `renderMembersPanel()`; add `iconAntenna`/`iconUsers` imports; remove `iconGlobe`/`iconGithub` imports; update grid `lg:grid-cols-3` condition |
| `src/meshcore_hub/web/templates/spa.html` | Restructure footer into two-column layout with MeshCore branding left, network/hub info right |
| `src/meshcore_hub/web/static/css/app.css` | Add footer layout styles if DaisyUI defaults insufficient |
| `src/meshcore_hub/web/static/locales/en.json` | Remove orphaned `home.meshcore_attribution` key |

---

## Testing

### Visual Verification

1. Start the app with OIDC enabled and seeded user profiles
2. Navigate to `/` (home page):
   - Verify the MeshCore card is gone
   - Verify the Members panel shows with operator and member counts
   - Verify counts match the `/members` page grouping
3. Scroll to footer:
   - Verify MeshCore logo (small) and text links appear left-aligned
   - Verify network info and "Powered by" appear right-aligned
   - Resize to mobile width — verify MeshCore stacks above network info, both center-aligned
4. Test with OIDC disabled — verify Members panel shows "0" for both counts (no error)

### API Verification

```bash
curl -s http://localhost:8000/api/v1/dashboard/stats -H "Authorization: Bearer $API_READ_KEY" | jq '.total_operators, .total_members'
```

### Automated Tests

```bash
# API tests (dashboard stats changes)
pytest tests/test_api/ -v

# Web tests (homepage rendering)
pytest tests/test_web/ -v

# Quality checks
pre-commit run --all-files
```

### Cross-Theme Testing

- Toggle between dark and light themes
- Verify footer MeshCore logo inverts correctly in light mode (existing `theme-logo--invert-light` class)
- Verify Members panel tiles use `--color-members` accent in both themes

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `UserProfile.roles.contains()` is a substring match — role "member" could match "nonmember" | In practice, roles are standard OIDC values (`admin`, `operator`, `member`). The comma-separated format (`"operator,member"`) prevents false positives since `contains("member")` matches the whole token. For extra safety, could use `LIKE '%,member,%' OR roles LIKE 'member,%' OR roles LIKE '%,member' OR roles = 'member'`, but this is over-engineering for the current data model. |
| Footer two-column layout may not look balanced with minimal network info | The `justify-between` flex layout with center-aligned fallback on mobile adapts well. If the left side is too sparse, the tagline text fills the space. |
| Dashboard stats endpoint re-reads Settings for role names | `Settings` is a Pydantic BaseSettings class — instantiation is cheap and reads from env vars. Alternatively, pass role names via dependency injection from the app lifespan. For now, direct instantiation is acceptable. |
| Removing the MeshCore card reduces attribution visibility | Moving it to the footer (present on every page, not just home) increases overall visibility. The footer is persistent across all routes. |
