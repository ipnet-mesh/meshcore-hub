# Plan: Radio Info Tile Display — Homepage Network Info Panel Overhaul

**Date**: 2026-05-06
**Status**: Draft

---

## Summary

Replace the flat label:value list in the **Network Info** panel on the home page (`/`) with a **3×2 grid of compact tiles**. Each tile represents one radio configuration parameter and displays an icon, a label, and the value. The design uses subtle colour, rounded borders, and a clear visual hierarchy (icon → label → value).

---

## Current State

### UI

The Network Info panel at `home.js:204–215` renders radio config parameters as a simple two-column flex list inside a `card bg-base-100 shadow-xl`:

```
┌──────────────────────────────┐
│ ℹ Network Info               │
│                              │
│ Profile:        EU/UK Narrow │
│ Frequency:      869.618MHz   │
│ Bandwidth:      62.5kHz      │
│ Spreading Factor: 8          │
│ Coding Rate:    8            │
│ TX Power:       22dBm        │
└──────────────────────────────┘
```

The `renderRadioConfig()` function at `home.js:11–28` maps the 6 `RadioConfig` fields to a flat array of label+value pairs, rendered with `<div class="flex justify-between">` rows.

### Data Source

Radio config is injected server-side via `window.__APP_CONFIG__.network_radio_config` (not an API endpoint). The `RadioConfig` Pydantic model (`common/schemas/network.py`) parses a comma-delimited string into:
- `profile` (str) — e.g. `"EU/UK Narrow"`
- `frequency` (str) — e.g. `"869.618MHz"`
- `bandwidth` (str) — e.g. `"62.5kHz"`
- `spreading_factor` (int) — e.g. `8`
- `coding_rate` (int) — e.g. `8`
- `tx_power` (str) — e.g. `"22dBm"`

Any field can be `None`/`null` (partial configs are supported).

### Key Files

| File | Role |
|------|------|
| `src/meshcore_hub/web/static/js/spa/pages/home.js` | Home page render; `renderRadioConfig()` at lines 11–28; panel layout at lines 204–215 |
| `src/meshcore_hub/web/static/css/app.css` | Custom styles; color palette at lines 21–29; panel utilities at lines 88–113 |
| `src/meshcore_hub/web/static/js/spa/components.js` | Shared component imports; `t()`, `html`, `litRender`, `pageColors` |
| `src/meshcore_hub/web/static/js/spa/icons.js` | SVG icon functions (`iconAntenna`, `iconChart`, etc.) |
| `src/meshcore_hub/web/static/locales/en.json` | i18n keys: `links.profile`, `home.frequency`, `home.bandwidth`, `home.spreading_factor`, `home.coding_rate`, `home.tx_power`, `home.network_info` |
| `src/meshcore_hub/common/schemas/network.py` | `RadioConfig` Pydantic model (data structure validation) |
| `src/meshcore_hub/web/app.py` | Server-side config injection into `__APP_CONFIG__` (line 237–272) |

---

## Target State

### UI

Replace the flat label:value list with a **3-column × 2-row grid** of compact tiles. Each tile has this structure:

```
┌──────────────────────┐
│                      │
│        [icon]        │  ← higher-contrast colour
│                      │
│       Label          │  ← medium-contrast font (e.g. "Frequency")
│    869.618MHz        │  ← white (dark theme) / black (light theme)
│                      │
└──────────────────────┘
```

**6 tiles**: Profile, Frequency, Bandwidth, Spreading Factor, Coding Rate, TX Power.

**Grid layout**:

```
┌────────────┬────────────┬────────────┐
│  Profile   │ Frequency  │ Bandwidth  │
│  EU/UK...  │ 869.618MHz │  62.5kHz   │
├────────────┼────────────┼────────────┤
│ Spreading  │  Coding    │  TX Power  │
│  Factor 8  │   Rate 8   │  22dBm     │
└────────────┴────────────┴────────────┘
```

**Responsive behaviour**: On small screens (`md` breakpoint and below), collapse to 2 columns. No single-column fallback — 2 columns minimum ensures tiles remain compact even on phones.

**Missing fields**: If a radio parameter is `null`/`undefined`, the entire tile for that parameter is hidden (same as current behaviour where empty values are filtered out).

### Visual Design

| Element | Dark Theme | Light Theme |
|---------|-----------|-------------|
| **Tile background** | `transparent` (no fill) | Same |
| **Tile border** | `border border-base-content/10 rounded-box` | Same |
| **Icon colour** | `var(--color-radio)` — new cyan accent (`oklch(0.75 0.15 210)`) | `var(--color-radio)` — darker variant (`oklch(0.55 0.15 210)`) |
| **Label** | `opacity-70` on `text-base-content` (medium contrast) | Same |
| **Value** | `text-base-content` (white in dark, black in light) with `font-semibold` | Same |

Tiles use a transparent background — no fill, no `panel-glow`. The rounded border alone provides visual separation, keeping tiles compact and lightweight.

### Icon Selection

Create new SVG icon functions in `icons.js` for radio-specific concepts, OR reuse existing Heroicons:

| Parameter | Icon Concept | Source |
|-----------|-------------|--------|
| Profile | Cog/gear (settings profile) | Existing `iconSettings` or new cog variant |
| Frequency | Waveform/sine wave | New SVG — sine wave icon |
| Bandwidth | Sliders/adjust | New SVG — horizontal sliders |
| Spreading Factor | Arrows expanding outward | New SVG — expand arrows |
| Coding Rate | Shield with check | New SVG — shield-check |
| TX Power | Bolt/power | New SVG — bolt |

Each new icon follows the existing pattern: a function exporting a `lit-html` template with a `cls` parameter for CSS sizing, using Heroicons outline style (24×24 viewBox, `stroke="currentColor"` with `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"`).

---

## Implementation Plan

### 1. Add Radio Parameter Icons (`icons.js`)

Add 5–6 new icon functions in `icons.js`. Where an adequate existing icon exists, reuse it. For the rest, create new Heroicons-style SVG icons.

Icons needed (at minimum 5 — `iconSettings` already exists for Profile):
- `iconFrequency` — waveform/sine (new)
- `iconBandwidth` — horizontal sliders (new)
- `iconSpreadingFactor` — expand arrows (new)
- `iconCodingRate` — shield-check (new)
- `iconTxPower` — bolt/lightning (new)

### 2. Rewrite `renderRadioConfig()` → `renderRadioTiles()` (`home.js`)

Replace the current `renderRadioConfig()` function (lines 11–28) with a new `renderRadioTiles()` function that:

1. Maps each parameter to a tile definition: `{ icon, label, value }`
2. Filters out tiles with no value
3. Renders a CSS Grid (3 columns, responsive) of tiles
4. Each tile is a `<div>` with transparent background, rounded border, centered content

**Template structure (per tile)**:
```js
html`
<div class="flex flex-col items-center justify-center gap-1.5 p-3
            border border-base-content/10 rounded-box
            text-center">
    <span class="radio-tile-icon w-6 h-6">
        ${icon('w-full h-full')}
    </span>
    <span class="text-xs opacity-70 leading-tight">${label}</span>
    <span class="text-sm font-semibold leading-tight">${String(value)}</span>
</div>`
```

**Grid wrapper**: `grid grid-cols-2 md:grid-cols-3 gap-3`

**Panel container**: Replace `space-y-2` with the grid wrapper.

### 3. Update Icon Imports (`home.js`)

Add the new icon imports to the existing import block at line 6–9:

```js
import {
    iconDashboard, iconNodes, iconAdvertisements, iconMessages, iconMembers, iconMap,
    iconPage, iconInfo, iconChart, iconGlobe, iconGithub,
    iconSettings, iconFrequency, iconBandwidth, iconSpreadingFactor, iconCodingRate, iconTxPower,
} from '../icons.js';
```

### 4. Add Radio Tile CSS (`app.css`)

Add a new CSS rule for the radio tile icon colour:

```css
:root {
    --color-radio: oklch(0.75 0.15 210);     /* cyan — radio tile icons */
}
[data-theme="light"] {
    --color-radio: oklch(0.55 0.15 210);
}

.radio-tile-icon {
    color: var(--color-radio);
}
```

This adds a new `--color-radio` CSS custom property (cyan) with light-mode variant, following the existing palette convention in `app.css:21–40`. The `.radio-tile-icon` class applies it to tile icons.

### 5. i18n Updates (`en.json`)

The existing i18n keys are reused as-is:
- `links.profile` → label "Profile"
- `home.frequency` → label "Frequency"
- `home.bandwidth` → label "Bandwidth"
- `home.spreading_factor` → label "Spreading Factor"
- `home.coding_rate` → label "Coding Rate"
- `home.tx_power` → label "TX Power"

No new i18n keys required.

---

## Files Changed — Summary

| File | Change |
|------|--------|
| `src/meshcore_hub/web/static/js/spa/icons.js` | Add 5 new radio-specific SVG icon functions (`iconFrequency`, `iconBandwidth`, `iconSpreadingFactor`, `iconCodingRate`, `iconTxPower`) |
| `src/meshcore_hub/web/static/js/spa/pages/home.js` | Replace `renderRadioConfig()` with `renderRadioTiles()`; update panel template at lines 204–215 to use grid layout; add new icon imports to existing import block at lines 6–9 |
| `src/meshcore_hub/web/static/css/app.css` | Add `--color-radio` cyan CSS custom property (with light-mode variant) to colour palette section; add `.radio-tile-icon` class |

---

## Testing

### Visual Verification

1. Start the app with a radio config string: `NETWORK_RADIO_CONFIG="EU/UK Narrow,869.618MHz,62.5kHz,8,8,22dBm"`
2. Navigate to `/` (home page)
3. Verify:
   - 6 tiles display in a 3×2 grid on desktop
   - Tiles collapse to 2-column on tablet/mobile (no single-column fallback)
   - Each tile has an icon (coloured), label (medium contrast), and value (high contrast)
   - Tiles align properly at different viewport widths
4. Test with missing fields (e.g. `NETWORK_RADIO_CONFIG="EU/UK Narrow,,,,22dBm"`) — verify only 2 tiles render
5. Test with no radio config (empty/null) — verify the entire Network Info panel still renders gracefully (empty body or component not shown)

### Automated Tests

```bash
# Web-specific tests (render logic)
pytest tests/test_web/ -v

# Quality checks
pre-commit run --all-files
```

### Cross-Theme Testing

- Toggle between dark and light themes via the navbar theme switcher
- Verify icon colour adjusts per theme (via `var(--color-radio)` with light/dark variants in `app.css`)
- Verify label contrast and value contrast are appropriate on both themes

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| 6 tiles make panel taller than current list | The current list already shows up to 6 rows (one per param). A 3×2 grid is comparable in height. The tile format adds small icon spacing overhead but the grid layout is more space-efficient than 6 stacked rows. |
| Icons may not be immediately intuitive | Use standard metaphor: waveform for frequency, bolt for power, shield for coding rate. Labels are always present below icons. |
| New SVG icons bloat `icons.js` | Each icon function is ~5–7 lines. 5 new icons ≈ 30 lines. Acceptable. |
| Tile border colour may clash with theme | Use `border-base-content/10` which adapts to theme via DaisyUI. |
| Responsive layout may break at edge cases | Test at 320px, 375px, 768px, 1024px, 1440px widths. The `grid-cols-2 md:grid-cols-3` pattern keeps a minimum of 2 columns at all sizes, which works well for 6 tiles. |
