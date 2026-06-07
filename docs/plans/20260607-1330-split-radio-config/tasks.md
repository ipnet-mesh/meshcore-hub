# Tasks: Split NETWORK_RADIO_CONFIG into Individual Environment Variables

> Generated from `plan.md` on 2026-06-07

## Schema — RadioConfig Model

- [x] 1. Rewrite `RadioConfig` model in `common/schemas/network.py`
  - [x] 1.1 Change `frequency` field type from `Optional[str]` to `Optional[float]`
  - [x] 1.2 Change `bandwidth` field type from `Optional[str]` to `Optional[float]`
  - [x] 1.3 Change `tx_power` field type from `Optional[str]` to `Optional[float]`
  - [x] 1.4 Remove `from_config_string` class method entirely
  - [x] 1.5 Update docstring to describe individual-field construction (no longer comma-delimited)
  - [x] 1.6 Add `format_for_display()` instance method returning formatted dict
    - [x] 1.6.1 `frequency` → `f"{value:g}MHz"` (e.g. `869.618` → `"869.618MHz"`, `22.0` → `"22MHz"`)
    - [x] 1.6.2 `bandwidth` → `f"{value:g}kHz"` (e.g. `62.5` → `"62.5kHz"`)
    - [x] 1.6.3 `tx_power` → `f"{value:g}dBm"` (e.g. `22.0` → `"22dBm"`, `30.0` → `"30dBm"`)
    - [x] 1.6.4 `None` values return `None` for that field (no unit suffix)
    - [x] 1.6.5 Profile, spreading_factor, coding_rate returned as-is

## Config — Settings

- [x] 2. Replace `network_radio_config` in `WebSettings` (`common/config.py:337-354`)
  - [x] 2.1 Remove `network_radio_config: Optional[str]` field
  - [x] 2.2 Add `network_radio_profile: str = Field(default="EU/UK Narrow")`
  - [x] 2.3 Add `network_radio_frequency: float = Field(default=869.618)`
  - [x] 2.4 Add `network_radio_bandwidth: float = Field(default=62.5)`
  - [x] 2.5 Add `network_radio_spreading_factor: int = Field(default=8)`
  - [x] 2.6 Add `network_radio_coding_rate: int = Field(default=8)`
  - [x] 2.7 Add `network_radio_tx_power: float = Field(default=22.0)`

## CLI and App Wiring

- [x] 3. Replace Click option in `web/cli.py`
  - [x] 3.1 Remove `--network-radio-config` option
  - [x] 3.2 Add `--network-radio-profile` (str, default `"EU/UK Narrow"`)
  - [x] 3.3 Add `--network-radio-frequency` (float, default `869.618`)
  - [x] 3.4 Add `--network-radio-bandwidth` (float, default `62.5`)
  - [x] 3.5 Add `--network-radio-spreading-factor` (int, default `8`)
  - [x] 3.6 Add `--network-radio-coding-rate` (int, default `8`)
  - [x] 3.7 Add `--network-radio-tx-power` (float, default `22.0`)
  - [x] 3.8 Update `web()` function signature and `create_app()` call with six params

- [x] 4. Update `create_app()` signature in `web/app.py`
  - [x] 4.1 Replace `network_radio_config: str | None` with six individual parameters
  - [x] 4.2 Store individual fields on `app.state` (e.g. `app.state.network_radio_frequency`)
  - [x] 4.3 Update `app.state` assignments

- [x] 5. Update `_build_config_json()` in `web/app.py`
  - [x] 5.1 Construct `RadioConfig` from individual `app.state.network_radio_*` fields via direct constructor
  - [x] 5.2 Call `format_for_display()` to get dict with formatted strings
  - [x] 5.3 Assign result to `network_radio_config` key in JSON output

## Docker and Documentation

- [x] 6. Update `docker-compose.yml`
  - [x] 6.1 Remove `NETWORK_RADIO_CONFIG` pass-through
  - [x] 6.2 Add six new environment variable pass-throughs with defaults

- [x] 7. Update `.env.example`
  - [x] 7.1 Replace old `NETWORK_RADIO_CONFIG` block with six new variables
  - [x] 7.2 Ensure comment notes that units are applied automatically on display

- [x] 8. Update `README.md` environment variable table
  - [x] 8.1 Replace single `NETWORK_RADIO_CONFIG` row with six rows
  - [x] 8.2 Each row notes "raw number, units applied on display" for freq/bw/power

- [x] 9. Update `AGENTS.md` environment variable reference
  - [x] 9.1 Replace single `NETWORK_RADIO_CONFIG` entry with six entries with defaults

- [x] 10. Update `docs/upgrading.md`
  - [x] 10.1 Add new `## v0.12.0` heading at top (before `## v0.11.0`)
  - [x] 10.2 Document the breaking change with bold descriptive title and explanation
  - [x] 10.3 Include migration example (before/after env var format)
  - [x] 10.4 Note behavioral change: radio config now "always on" with defaults

## Tests

- [x] 11. Add `RadioConfig` schema tests in `tests/test_common/`
  - [x] 11.1 Test direct construction with all EU/UK Narrow defaults
  - [x] 11.2 Test direct construction with custom float values (e.g. frequency=915.0, tx_power=30.0)
  - [x] 11.3 Test `format_for_display()` produces `"869.618MHz"`, `"62.5kHz"`, `"22dBm"`
  - [x] 11.4 Test `format_for_display()` strips unnecessary decimal (e.g. `22.0` → `"22dBm"`)
  - [x] 11.5 Test `format_for_display()` with `None` values returns `None`
  - [x] 11.6 Test that `from_config_string` no longer exists on `RadioConfig`

- [x] 12. Add `WebSettings` config tests in `tests/test_common/`
  - [x] 12.1 Test defaults to EU/UK Narrow values for all six fields
  - [x] 12.2 Test reads individual `NETWORK_RADIO_*` env vars as correct types
  - [x] 12.3 Test `WebSettings` no longer has `network_radio_config` field
  - [x] 12.4 Test `NETWORK_RADIO_FREQUENCY=915.0` sets `network_radio_frequency == 915.0`

- [x] 13. Update web test fixtures
  - [x] 13.1 Update `tests/test_web/conftest.py` — replace `network_radio_config` with individual params
  - [x] 13.2 Update `tests/test_web/test_app.py` — replace `network_radio_config` with individual params

## Verification

- [x] 14. Run targeted tests
  - [x] 14.1 `pytest tests/test_common/ -v` — 30 passed
  - [x] 14.2 `pytest tests/test_web/ -v` — 218 passed

- [x] 15. Run quality checks
  - [x] 15.1 `pre-commit run --all-files` — all pass (black auto-formatted 2 files)
