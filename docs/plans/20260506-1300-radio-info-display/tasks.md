# Tasks: Radio Info Tile Display

**Plan**: [plan.md](plan.md)
**Date**: 2026-05-06

---

## Implementation

- [ ] 1. **Add 5 radio icon functions to `icons.js`**
  - `iconFrequency` — waveform/sine wave SVG
  - `iconBandwidth` — horizontal sliders SVG
  - `iconSpreadingFactor` — expanding arrows SVG
  - `iconCodingRate` — shield-with-check SVG
  - `iconTxPower` — bolt/lightning SVG
  - Each follows existing pattern: exported function with `(cls = 'h-5 w-5')` param, Heroicons outline style (24×24 viewBox, `stroke="currentColor"`, `stroke-width="2"`)

- [ ] 2. **Replace `renderRadioConfig()` with `renderRadioTiles()` in `home.js`**
  - Remove old `renderRadioConfig()` function (lines 11–28)
  - Add new `renderRadioTiles(rc)` that maps `RadioConfig` fields to tile definitions, filters nulls, returns a `grid grid-cols-2 md:grid-cols-3 gap-3` wrapper with tile `div`s
  - Each tile: icon (`radio-tile-icon w-6 h-6`), label (`text-xs opacity-70`), value (`text-sm font-semibold`)
  - Update panel container (line ~204): replace `space-y-2` with the grid wrapper

- [ ] 3. **Update icon imports in `home.js`**
  - Add `iconSettings`, `iconFrequency`, `iconBandwidth`, `iconSpreadingFactor`, `iconCodingRate`, `iconTxPower` to the import block (lines 6–9)

- [ ] 4. **Add `--color-radio` CSS to `app.css`**
  - Add `--color-radio: oklch(0.75 0.15 210)` to the existing `:root` block (dark theme)
  - Add `--color-radio: oklch(0.55 0.15 210)` to the existing `[data-theme="light"]` block
  - Add `.radio-tile-icon { color: var(--color-radio); }` rule

## Verification

- [ ] 5. **Run quality checks**
  - `pre-commit run --all-files`

- [ ] 6. **Run web tests**
  - `pytest tests/test_web/ -v`

- [ ] 7. **Manual visual check**
  - Start with `NETWORK_RADIO_CONFIG="EU/UK Narrow,869.618MHz,62.5kHz,8,8,22dBm"`
  - Verify 3×2 grid on desktop, 2-column on mobile
  - Verify icon colour (cyan) in both dark and light themes
  - Test with missing fields: `NETWORK_RADIO_CONFIG="EU/UK Narrow,,,,22dBm"` → 2 tiles
  - Test with no config: Network Info panel handles empty gracefully
