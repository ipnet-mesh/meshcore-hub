# Split NETWORK_RADIO_CONFIG into Individual Environment Variables

## Summary

Replace the single `NETWORK_RADIO_CONFIG` comma-delimited environment variable with six separate environment variables (`NETWORK_RADIO_PROFILE`, `NETWORK_RADIO_FREQUENCY`, `NETWORK_RADIO_BANDWIDTH`, `NETWORK_RADIO_SPREADING_FACTOR`, `NETWORK_RADIO_CODING_RATE`, `NETWORK_RADIO_TX_POWER`). Any unset variable defaults to the EU/UK Narrow profile values. The legacy `NETWORK_RADIO_CONFIG` variable and its `from_config_string` parsing are removed entirely.

Frequency, bandwidth, and TX power are stored as raw floats in configuration and on `app.state`. Formatting (appending `MHz`, `kHz`, `dBm`) is applied dynamically when building the frontend JSON config — administrators only configure bare numbers.

## Background & Motivation

Currently, radio configuration is specified via a single `NETWORK_RADIO_CONFIG` environment variable with a comma-delimited format:

```
NETWORK_RADIO_CONFIG=EU/UK Narrow,869.618MHz,62.5kHz,8,8,22dBm
```

This format confuses new administrators because:
- The positional format requires remembering which position maps to which parameter
- Comments explaining the format (e.g. `.env.example` line 424) are easy to overlook
- Editing one parameter requires careful comma-counting to avoid shifting values
- Empty values require placeholder commas (`EU/UK Narrow,,,,22dBm`)
- Unit suffixes (`MHz`, `kHz`, `dBm`) are mandatory but easy to forget or mistype

Every other `NETWORK_*` configuration variable is a single key-value pair. Radio config is the only one that uses positional parsing. Splitting it into separate variables and storing raw numbers (with automatic formatting) brings consistency and eliminates a common source of configuration error.

This is a **breaking change**: administrators using `NETWORK_RADIO_CONFIG` must migrate to the individual variables. The `docs/upgrading.md` guide must document the migration path.

**Relevant prior work**: The [radio info display plan](../20260506-1300-radio-info-display/plan.md) added the UI tile display for radio config. The UI tiles render `String(value)` from the JSON config, so as long as the JSON continues to contain formatted strings (e.g. `"869.618MHz"`), no frontend changes are needed.

## Goals

- Replace `NETWORK_RADIO_CONFIG` with six individual environment variables
- Default all unset variables to EU/UK Narrow profile values
- Store frequency, bandwidth, and TX power as raw floats; format units dynamically
- Remove the legacy `NETWORK_RADIO_CONFIG` variable and `from_config_string` parsing entirely
- Keep the frontend JSON contract unchanged (formatted strings) so the UI is unaffected
- Update all documentation and configuration examples

## Non-Goals

- Changing the frontend radio tile display or any UI behavior
- Adding validation for radio parameter values beyond type coercion
- Supporting multiple radio profiles or presets
- Backwards compatibility with `NETWORK_RADIO_CONFIG`

## Requirements

### Functional Requirements

- Six new environment variables are supported: `NETWORK_RADIO_PROFILE`, `NETWORK_RADIO_FREQUENCY`, `NETWORK_RADIO_BANDWIDTH`, `NETWORK_RADIO_SPREADING_FACTOR`, `NETWORK_RADIO_CODING_RATE`, `NETWORK_RADIO_TX_POWER`
- Each variable defaults to the EU/UK Narrow profile value when unset:
  - `NETWORK_RADIO_PROFILE` defaults to `"EU/UK Narrow"`
  - `NETWORK_RADIO_FREQUENCY` defaults to `869.618` (float, in MHz)
  - `NETWORK_RADIO_BANDWIDTH` defaults to `62.5` (float, in kHz)
  - `NETWORK_RADIO_SPREADING_FACTOR` defaults to `8`
  - `NETWORK_RADIO_CODING_RATE` defaults to `8`
  - `NETWORK_RADIO_TX_POWER` defaults to `22.0` (float, in dBm)
- Administrators configure raw numbers only — no unit suffixes:
  ```
  NETWORK_RADIO_FREQUENCY=869.618    # not "869.618MHz"
  NETWORK_RADIO_BANDWIDTH=62.5       # not "62.5kHz"
  NETWORK_RADIO_TX_POWER=22          # not "22dBm"
  ```
- Formatting is applied automatically in `_build_config_json()` when building the frontend JSON:
  - `frequency` float → `"NMHz"` string (e.g. `869.618` → `"869.618MHz"`)
  - `bandwidth` float → `"NkHz"` string (e.g. `62.5` → `"62.5kHz"`)
  - `tx_power` float → `"NdBm"` string (e.g. `22.0` → `"22dBm"`)
- The JSON output in `window.__APP_CONFIG__.network_radio_config` retains the same string format as today — the frontend requires no changes
- The Click CLI replaces `--network-radio-config` with six new `--network-radio-*` options (float types for frequency/bandwidth/tx_power)
- **Behavioral change**: Radio config is now "always on" — omitting all 6 vars shows EU/UK Narrow defaults rather than hiding the tiles. Previously, an empty `NETWORK_RADIO_CONFIG` meant no tiles displayed at all.

### Technical Requirements

- **Config** — Remove `network_radio_config` from `CommonSettings`; add six new fields:
  - `network_radio_profile: str` (default `"EU/UK Narrow"`)
  - `network_radio_frequency: float` (default `869.618`)
  - `network_radio_bandwidth: float` (default `62.5`)
  - `network_radio_spreading_factor: int` (default `8`)
  - `network_radio_coding_rate: int` (default `8`)
  - `network_radio_tx_power: float` (default `22.0`)
- **Schema** — Rewrite `RadioConfig` in `common/schemas/network.py`:
  - Remove `from_config_string` entirely
  - Change `frequency` and `bandwidth` from `Optional[str]` to `Optional[float]`
  - Change `tx_power` from `Optional[str]` to `Optional[float]`
  - Construct instances directly via `RadioConfig(profile=..., frequency=..., ...)` — no special class method needed
  - Add a `format_for_display()` method that returns a dict with formatted strings (e.g. `"869.618MHz"`), keeping the existing JSON contract
  - No changes needed to `schemas/__init__.py` — the `RadioConfig` export continues to work
- **CLI** — Remove `--network-radio-config`; add six new Click options (float types for freq/bw/power)
- **App** — Update `create_app()` and `_build_config_json()` to use individual float fields; call `format_for_display()` when building the JSON
- **Docker** — Remove `NETWORK_RADIO_CONFIG` from `docker-compose.yml`; add six new pass-throughs
- **Docs** — Update `.env.example`, `README.md`, `AGENTS.md`, `docs/upgrading.md`
- **Tests** — Add/update schema tests, config tests, and web test fixtures
- `pre-commit run --all-files` passes

## Implementation Plan

### Phase 1: Schema — RadioConfig Model

1. **Rewrite `RadioConfig`** (`common/schemas/network.py`):
   - Change field types: `frequency: Optional[float]`, `bandwidth: Optional[float]`, `tx_power: Optional[float]` (profile, spreading_factor, coding_rate unchanged)
    - Remove `from_config_string` class method entirely
    - Update docstring to describe individual-field construction (no longer comma-delimited)
    - Add `format_for_display()` instance method that returns a dict:
     ```python
     {
         "profile": self.profile,
         "frequency": f"{self.frequency}MHz" if self.frequency is not None else None,
         "bandwidth": f"{self.bandwidth}kHz" if self.bandwidth is not None else None,
         "spreading_factor": self.spreading_factor,
         "coding_rate": self.coding_rate,
         "tx_power": f"{self.tx_power}dBm" if self.tx_power is not None else None,
     }
     ```
   - Formatting uses Python's default float formatting (strips trailing zeros via `g` format or similar). For example: `22.0` → `"22dBm"`, not `"22.0dBm"`

### Phase 2: Config — Settings

2. **Replace `network_radio_config` in `CommonSettings`** (`common/config.py:337-339`):
   - Remove `network_radio_config: Optional[str]`
   - Add six new fields with EU/UK Narrow defaults:
     ```python
     network_radio_profile: str = Field(default="EU/UK Narrow", description="Radio profile name")
     network_radio_frequency: float = Field(default=869.618, description="Radio frequency (MHz)")
     network_radio_bandwidth: float = Field(default=62.5, description="Radio bandwidth (kHz)")
     network_radio_spreading_factor: int = Field(default=8, description="Radio spreading factor")
     network_radio_coding_rate: int = Field(default=8, description="Radio coding rate")
     network_radio_tx_power: float = Field(default=22.0, description="Radio TX power (dBm)")
     ```

### Phase 3: CLI and App Wiring

3. **Replace Click option** (`web/cli.py:64-69`):
   - Remove `--network-radio-config`
   - Add six new options: `--network-radio-profile` (str), `--network-radio-frequency` (float), `--network-radio-bandwidth` (float), `--network-radio-spreading-factor` (int), `--network-radio-coding-rate` (int), `--network-radio-tx-power` (float)
   - Update `web()` function signature and `create_app()` call

4. **Update `create_app()`** (`web/app.py:355-389`):
   - Replace `network_radio_config: str | None` with six individual parameters
   - Store individual fields on `app.state` (e.g. `app.state.network_radio_frequency`)

5. **Update `_build_config_json()`** (`web/app.py:256-277`):
    - Construct `RadioConfig` from individual `app.state.network_radio_*` fields via direct constructor: `RadioConfig(profile=..., frequency=..., ...)`
    - Use `format_for_display()` to build the dict (formatted strings for frequency/bandwidth/tx_power)
   - The JSON output structure remains identical — frontend unchanged

### Phase 4: Docker and Documentation

6. **Update `docker-compose.yml`**:
   - Remove `NETWORK_RADIO_CONFIG` pass-through (line 288)
   - Add six new environment variable pass-throughs

7. **Update `.env.example`** (lines 423-426):
   - Replace the `NETWORK_RADIO_CONFIG` block (lines 423-426) with:
     ```
     # Radio configuration (six individual variables — no unit suffixes needed)
     # Units (MHz, kHz, dBm) are applied automatically on display
     NETWORK_RADIO_PROFILE=EU/UK Narrow
     NETWORK_RADIO_FREQUENCY=869.618
     NETWORK_RADIO_BANDWIDTH=62.5
     NETWORK_RADIO_SPREADING_FACTOR=8
     NETWORK_RADIO_CODING_RATE=8
     NETWORK_RADIO_TX_POWER=22
     ```

8. **Update `README.md`** (`README.md:405`):
   - Replace the single `NETWORK_RADIO_CONFIG` row in the environment variable table with six rows:
     ```
     | `NETWORK_RADIO_PROFILE`        | `EU/UK Narrow`           | Radio profile name                                                                                      |
     | `NETWORK_RADIO_FREQUENCY`      | `869.618`                | Radio frequency in MHz (raw number, units applied on display)                                           |
     | `NETWORK_RADIO_BANDWIDTH`      | `62.5`                   | Radio bandwidth in kHz (raw number, units applied on display)                                           |
     | `NETWORK_RADIO_SPREADING_FACTOR` | `8`                    | Radio spreading factor                                                                                  |
     | `NETWORK_RADIO_CODING_RATE`    | `8`                      | Radio coding rate                                                                                       |
     | `NETWORK_RADIO_TX_POWER`       | `22`                     | Radio TX power in dBm (raw number, units applied on display)                                            |
     ```

   Update **`AGENTS.md`** (`AGENTS.md:678`):
   - Replace the single `NETWORK_RADIO_CONFIG` entry with six entries:
     ```
     - `NETWORK_RADIO_PROFILE` - Radio profile name (default: `EU/UK Narrow`)
     - `NETWORK_RADIO_FREQUENCY` - Radio frequency in MHz, raw number (default: `869.618`)
     - `NETWORK_RADIO_BANDWIDTH` - Radio bandwidth in kHz, raw number (default: `62.5`)
     - `NETWORK_RADIO_SPREADING_FACTOR` - Radio spreading factor (default: `8`)
     - `NETWORK_RADIO_CODING_RATE` - Radio coding rate (default: `8`)
     - `NETWORK_RADIO_TX_POWER` - Radio TX power in dBm, raw number (default: `22`)
     ```

9. **Update `docs/upgrading.md`**:
   - Add a new `## v0.12.0` heading at the top (before `## v0.11.0`), following the existing format pattern of bold descriptive title + explanation + migration example:
     ```markdown
     ## v0.12.0

     ### Radio Config Split Into Individual Environment Variables

     The single `NETWORK_RADIO_CONFIG` comma-delimited environment variable has been replaced with six individual variables. The legacy variable and its `from_config_string` parsing have been removed entirely. Each variable defaults to the EU/UK Narrow profile when unset.

     Frequency, bandwidth, and TX power are now configured as raw numbers without unit suffixes. Units (`MHz`, `kHz`, `dBm`) are applied automatically on display.

     **Migration example:**

     Before:
     ```
     NETWORK_RADIO_CONFIG=EU/UK Narrow,869.618MHz,62.5kHz,8,8,22dBm
     ```

     After:
     ```
     NETWORK_RADIO_PROFILE=EU/UK Narrow
     NETWORK_RADIO_FREQUENCY=869.618
     NETWORK_RADIO_BANDWIDTH=62.5
     NETWORK_RADIO_SPREADING_FACTOR=8
     NETWORK_RADIO_CODING_RATE=8
     NETWORK_RADIO_TX_POWER=22
     ```

     **Note:** Radio config is now "always on." If you previously omitted `NETWORK_RADIO_CONFIG` entirely (no radio tiles displayed), the EU/UK Narrow defaults will now be shown. To restore the previous behavior of hiding tiles entirely, set all six new variables to empty (but this is not recommended).
     ```

### Phase 5: Tests

10. **Add schema tests** (`tests/test_common/`):
    - Test `RadioConfig()` direct construction with all EU/UK Narrow defaults
    - Test `RadioConfig()` direct construction with custom float values (e.g. frequency=915.0, tx_power=30.0)
    - Test `format_for_display()` output: verify `"869.618MHz"`, `"62.5kHz"`, `"22dBm"` formatting
    - Test `format_for_display()` strips unnecessary decimal (e.g. `22.0` → `"22dBm"`, not `"22.0dBm"`)
    - Test `format_for_display()` with `None` values returns `None` for that field
    - Verify `from_config_string` no longer exists on the class

11. **Add/update config tests** (`tests/test_common/`):
    - Test `CommonSettings` defaults to EU/UK Narrow values for all six fields
    - Test `CommonSettings` reads individual `NETWORK_RADIO_*` env vars as correct types (float for freq/bw/power)
    - Test `CommonSettings` no longer has `network_radio_config` field
    - Test setting `NETWORK_RADIO_FREQUENCY=915.0` results in `settings.network_radio_frequency == 915.0`

12. **Update web test fixtures**:
    - `tests/test_web/conftest.py:331` — replace `network_radio_config="Test Radio Config"` with individual `network_radio_*` parameters (floats for freq/bw/power)
    - `tests/test_web/test_app.py:29` — same update
    - Verify all existing web tests still pass with new parameter names

13. **Run quality checks**:
    - `pytest tests/test_common/ tests/test_web/ -v`
    - `pre-commit run --all-files`

## Decisions

- **Settings location**: Individual fields remain in `CommonSettings` (consistent with current `network_radio_config` placement).
- **Float formatting**: Strip trailing zeros using Python `g` format (`f"{value:g}"`) — e.g. `22.0` → `"22dBm"`, `869.618` → `"869.618MHz"`.

## References

- [Radio Info Display Plan](../20260506-1300-radio-info-display/plan.md) — prior plan that created the UI tile display
- `src/meshcore_hub/common/schemas/network.py` — `RadioConfig` Pydantic model (to be rewritten)
- `src/meshcore_hub/common/config.py:337-339` — current `network_radio_config` field (to be replaced)
- `src/meshcore_hub/web/cli.py:64-69` — current Click option (to be replaced)
- `src/meshcore_hub/web/app.py:267` — current `from_config_string` call (to be replaced)
- `src/meshcore_hub/web/app.py:270-277` — current JSON dict building (to use `format_for_display()`)
- `src/meshcore_hub/web/static/js/spa/pages/home.js:12-34` — frontend `renderRadioTiles()` (unchanged)
- `tests/test_web/conftest.py:331` — test fixture using `network_radio_config`
- `tests/test_web/test_app.py:29` — test using `network_radio_config`

## Review

**Status**: Approved

**Reviewed**: 2026-06-07

### Resolutions

- **`from_settings` dropped**: Direct `RadioConfig()` constructor suffices — no transformation logic needed between settings and model.
- **Behavioral change documented**: Radio config is now "always on" with EU/UK Narrow defaults, unlike the previous design where empty config hid tiles entirely.
- **Docstring update**: `RadioConfig` docstring updated from comma-delimited format to individual-field construction.
- **schemas/__init__.py**: No changes needed — the existing `RadioConfig` export continues to work after the model rewrite.
- **No existing test breakage**: Grep confirmed zero test references to `from_config_string` or `RadioConfig` model. All tests for the new behavior are net-new.

### Remaining Action Items

- None
