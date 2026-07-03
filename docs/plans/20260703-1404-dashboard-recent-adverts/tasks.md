# Tasks: Dashboard Recent Adverts Card Improvements

> Generated from `plan.md` on 2026-07-03

## Backend: Schema & Data

- [x] Add `route_type`, `observers`, and `observed_by` fields to `RecentAdvertisement` schema
  - [x] Open `src/meshcore_hub/common/schemas/messages.py`
  - [x] Add `route_type: Optional[str] = Field(default=None, description="Route type")` after `received_at` (line 244)
  - [x] Add `observers: list[ObserverInfo] = Field(default_factory=list, description="All observers that captured this advertisement")` after `route_type`
  - [x] Add `observed_by: Optional[str] = Field(default=None, description="Observing interface node public key")` after `observers`

- [x] Wire observer data into `get_stats` dashboard endpoint
  - [x] Open `src/meshcore_hub/api/routes/dashboard.py`
  - [x] Add `fetch_observers_for_events` to the import from `observer_utils` (line 17)
  - [x] After the recent-ads query (line 174) and before building `RecentAdvertisement` list (line 202), collect event hashes and call `fetch_observers_for_events(session, "advertisement", ad_event_hashes)`
  - [x] Collect `observer_node_id` values from recent ads and batch-query `Node.id, Node.public_key` to build an `observer_pk_map` dict
  - [x] Pass `route_type=ad.route_type`, `observers=...`, and `observed_by=...` into the `RecentAdvertisement(...)` constructor (line 203)

## Frontend: Shared Component Extraction

- [x] Extract `routeTypeBadge` from `advertisements.js` into `components.js`
  - [x] Open `src/meshcore_hub/web/static/js/spa/components.js`
  - [x] Add exported `routeTypeBadge(routeType)` function after `observerIcons` (near line 559) with the same flood/direct/transport logic
  - [x] Open `src/meshcore_hub/web/static/js/spa/pages/advertisements.js`
  - [x] Remove the local `routeTypeBadge` function (lines 12–23)
  - [x] Add `routeTypeBadge` to the destructured import from `../components.js` (line 2–9)

## Frontend: Dashboard Card Rewrite

- [x] Rewrite `renderRecentAds` in `dashboard.js`
  - [x] Open `src/meshcore_hub/web/static/js/spa/pages/dashboard.js`
  - [x] Add `observerIcons` and `routeTypeBadge` to the import from `../components.js` (line 2–6)
  - [x] Remove `typeEmoji` from the import (only used by old emoji column; verify no other callers)
  - [x] Remove `.slice(0, 5)` call on line 38 so all 10 rows render
  - [x] Rewrite the table to four columns: Node, Type, Time, Observers
  - [x] Implement three-way observer fallback in the row template: `ad.observers` array → `ad.observed_by` satellite emoji → dash
  - [x] Use `routeTypeBadge(ad.route_type)` for the Type column
  - [x] Use `observerIcons(ad.observers)` for the Observers column when observers array is non-empty
  - [x] Retain the existing `formatTimeOnly(ad.received_at)` for the Time column

## Tests

- [x] Update existing dashboard tests for new fields
  - [x] Open `tests/test_api/test_dashboard.py`
  - [x] In `test_recent_ads_excludes_direct` (line 659): add assertions for `route_type == "flood"`, `observers == []`, `observed_by is None`
  - [x] In `test_recent_advertisements_includes_tag_name` (line 847): add assertions for `route_type == "flood"`, `observers == []`, `observed_by is None`

- [x] Add new test for observer population
  - [x] Add `test_recent_advertisements_includes_observers`: create observer Node, Advertisement with `event_hash`, and EventObserver row; assert `observers` has length 1 and correct `public_key`

- [x] Add new test for `observed_by` fallback
  - [x] Add `test_recent_advertisements_includes_observed_by`: create observer Node, Advertisement with `observer_node_id` set but no `event_hash` / EventObserver; assert `observers == []` and `observed_by` matches observer public key

## Verification

- [ ] Run dashboard API tests: `pytest --no-cov tests/test_api/test_dashboard.py -v`
- [ ] Run full quality checks: `pre-commit run --all-files`
- [ ] Rebuild stack: `make build`
- [ ] Visually verify `/dashboard` Recent Adverts card: route type badges appear, observer count badges appear, 10 rows shown, time column retained
- [ ] Visually verify `/advertisements` page: route type badges still render correctly (import refactor did not break them)
