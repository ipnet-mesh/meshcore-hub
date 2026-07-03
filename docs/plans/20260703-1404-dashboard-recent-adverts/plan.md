# Dashboard Recent Adverts Card Improvements

## Summary

The Recent Adverts card on the dashboard page currently shows a compact table of
5 advertisements with three columns: Node (name + truncated key), Type (a
satellite-dish emoji derived from `adv_type`), and Time. This plan enriches the
card to better match the full Advertisement list page by replacing the emoji
column with a route-type text badge (e.g. "Flood", "Relay"), adding an Observers
column (observer count badges with name tooltips), and increasing the displayed
row count from 5 to 10. The Time column is retained.

This requires a small backend change to include `route_type` and `observers` in
the `RecentAdvertisement` schema and the `get_stats` query, plus a frontend
rewrite of the `renderRecentAds` function to consume the new fields. A local
`routeTypeBadge` helper from `advertisements.js` is promoted to a shared export
in `components.js` to avoid duplication.

## Background & Motivation

The dashboard was recently restructured (plan
`20260703-1330-dashboard-packets-widget`) to remove the top stat-box row and
fold headline numbers into chart card corners. The bottom section retains two
cards: Recent Adverts and Recent Channel Messages. The Recent Adverts card is
the primary "what just happened" surface on the dashboard, but its current
information density is low — it shows only a type emoji and a time, omitting two
of the most useful columns from the full Advertisement list page: the route type
badge (which distinguishes flood vs. direct/relay) and the observer count (how
many stations heard the advert).

The recent git history shows sustained UI polish work (panel-accent redesign,
mobile nav clickthrough fix, typography adoption in commits `479c263`,
`510612d`, `cb677b3`), so this fits the current direction of tightening the
overview surfaces to be more informative at a glance.

The observer infrastructure already exists: `fetch_observers_for_events()` in
`observer_utils.py` batch-fetches `ObserverInfo` objects by `event_hash` and is
already used by the advertisements, messages, telemetry, and trace-path list
endpoints. The Advertisement model has `route_type` and `event_hash` columns.
The frontend `observerIcons()` helper in `components.js` already renders the
count-badge-with-tooltip. The only missing piece is wiring these into the
dashboard's recent-adverts data path and rendering.

## Goals

- Replace the satellite-dish emoji column in the dashboard Recent Adverts card
  with a route-type text badge (Flood / Relay / Zero-hop / Direct relay),
  matching the Advertisement list page's badge rendering.
- Add an Observers column showing observer count badges (with name tooltips),
  matching the Advertisement list page's observer rendering.
- Increase the displayed recent adverts from 5 to 10 (the backend already
  fetches 10; the frontend currently slices to 5).
- Retain the Time column (confirmed by the user).
- Avoid code duplication by sharing the `routeTypeBadge` helper between the
  dashboard and the advertisements list page.

## Non-Goals

- No changes to the Advertisement list page rendering or behavior (it already
  has route type badges and observer columns). It only changes its import source
  for `routeTypeBadge`.
- No changes to the homepage stat cards or dashboard chart cards (those were
  addressed in the prior packets-widget plan).
- No new API endpoints, feature flags, config variables, i18n keys, or database
  migrations.
- No changes to the Recent Channel Messages card.
- No pagination, sorting, filtering, or observer-filter toggle on the dashboard
  card (the dashboard is a read-only overview; full filtering lives on the
  Advertisement list page).

## Requirements

### Functional Requirements

- **FR-1** — The dashboard Recent Adverts card displays up to 10 advertisement
  rows (currently 5). The backend `/stats` endpoint already returns 10; the
  frontend `ads.slice(0, 5)` call must be removed.
- **FR-2** — Each row has four columns: **Node** (display name + truncated
  public key underneath, linked to `/nodes/{public_key}`), **Type** (route-type
  badge), **Time** (time-only formatted, as today), **Observers** (observer
  count badge or dash).
- **FR-3** — The Type column renders a route-type badge using the same logic as
  the Advertisement list page: `flood` → blue "Flood" badge;
  `transport_flood` → blue "Relay" badge; `direct` → green "Zero-hop" badge;
  `transport_direct` → green "Direct relay" badge; `null`/unknown → empty
  (nothing rendered).
- **FR-4** — The Observers column renders an observer count badge
  (`observerIcons()`) when the advert has `observers.length >= 1`, a faded
  satellite emoji when only the legacy `observed_by` field is present (no
  event-observer rows), and a faded dash when neither is present — mirroring the
  Advertisement list page's three-way fallback.
- **FR-5** — The `GET /api/v1/dashboard/stats` response includes `route_type`,
  `observers`, and `observed_by` on each item in `recent_advertisements`.

### Technical Requirements

- **TR-1** — The `RecentAdvertisement` schema gains three fields:
  `route_type: Optional[str]`, `observers: list[ObserverInfo]` (default
  empty list), and `observed_by: Optional[str]`. The `ObserverInfo` schema is
  reused as-is (already defined in the same module).
- **TR-2** — The `get_stats` dashboard route collects `event_hash` values from
  the fetched recent adverts and calls `fetch_observers_for_events(session,
  "advertisement", event_hashes)` to batch-resolve observer data in a single
  query — the same pattern used by the advertisements list endpoint.
- **TR-3** — The `routeTypeBadge` function is moved from a local definition in
  `advertisements.js` to an exported function in `components.js`, so both the
  dashboard and the advertisements page share a single implementation.
  `advertisements.js` updates its import accordingly.
- **TR-4** — The frontend `renderRecentAds` function imports `observerIcons`
  and `routeTypeBadge` from `components.js` and uses them in the new column
  layout. The `typeEmoji` import (used only for the old emoji column) is removed
  from `dashboard.js` if it becomes unused after the change.
- **TR-5** — Observer fallback logic matches the Advertisement list page: if
  `ad.observers` is a non-empty array, render `observerIcons(ad.observers)`;
  otherwise if `ad.observed_by` is truthy, render a faded satellite emoji; else
  render a faded dash.
- **TR-6** — No new i18n keys needed. The route-type badge text ("Flood",
  "Relay", "Zero-hop", "Direct relay") is hardcoded in the existing
  `routeTypeBadge` function and is not i18n-ized today. The column headers reuse
  existing keys: `entities.node`, `common.type`, `common.received`,
  `common.observers`.

## Implementation Plan

### Phase 1: Backend — schema & data

- **`src/meshcore_hub/common/schemas/messages.py`** — `RecentAdvertisement`
  (line 237): add three fields after `received_at`:
  ```python
  route_type: Optional[str] = Field(default=None, description="Route type")
  observers: list[ObserverInfo] = Field(
      default_factory=list, description="All observers that captured this advertisement"
  )
  observed_by: Optional[str] = Field(
      default=None, description="Observing interface node public key"
  )
  ```
  `ObserverInfo` is already defined earlier in the same module (line 9), so no
  new import needed.

- **`src/meshcore_hub/api/routes/dashboard.py`** — `get_stats()`:
  - Add `fetch_observers_for_events` to the import from `observer_utils` (line
    17 already imports `resolve_sender_names` from that module).
  - After the recent-adverts query (line 164–174) and before building the
    `RecentAdvertisement` list (line 202), collect event hashes and fetch
    observers:
    ```python
    ad_event_hashes = [ad.event_hash for ad in recent_ads if ad.event_hash]
    observers_by_hash = fetch_observers_for_events(
        session, "advertisement", ad_event_hashes
    )
    ```
  - Resolve `observer_node_id` → `public_key` for the `observed_by` fallback.
    Collect observer node IDs from the ads and look up their public keys:
    ```python
    observer_node_ids = [ad.observer_node_id for ad in recent_ads if ad.observer_node_id]
    observer_pk_map: dict[str, str] = {}
    if observer_node_ids:
        obs_query = select(Node.id, Node.public_key).where(
            Node.id.in_(observer_node_ids)
        )
        for node_id, public_key in session.execute(obs_query).all():
            observer_pk_map[node_id] = public_key
    ```
  - In the `RecentAdvertisement(...)` constructor (line 203–210), add:
    ```python
    route_type=ad.route_type,
    observers=observers_by_hash.get(ad.event_hash, []) if ad.event_hash else [],
    observed_by=observer_pk_map.get(ad.observer_node_id) if ad.observer_node_id else None,
    ```

### Phase 2: Frontend — shared component extraction

- **`src/meshcore_hub/web/static/js/spa/components.js`** — Add an exported
  `routeTypeBadge(routeType)` function with the same logic currently in
  `advertisements.js:12-23`:
  ```js
  export function routeTypeBadge(routeType) {
      if (!routeType) return nothing;
      if (routeType === 'flood' || routeType === 'transport_flood') {
          return html`<span class="badge badge-sm badge-info">${routeType === 'flood' ? 'Flood' : 'Relay'}</span>`;
      }
      if (routeType === 'direct' || routeType === 'transport_direct') {
          return html`<span class="badge badge-sm badge-success">${routeType === 'direct' ? 'Zero-hop' : 'Direct relay'}</span>`;
      }
      return nothing;
  }
  ```
  Place it near the other badge/icon helpers (e.g. after `observerIcons` at line
  559). Ensure `html` and `nothing` are already imported (they are).

- **`src/meshcore_hub/web/static/js/spa/pages/advertisements.js`** — Remove the
  local `routeTypeBadge` function (lines 12–23) and add it to the import from
  `../components.js` (line 2–9).

### Phase 3: Frontend — dashboard card rewrite

- **`src/meshcore_hub/web/static/js/spa/pages/dashboard.js`** —
  `renderRecentAds()` (lines 34–68):
  - **Imports** (lines 2–6): add `observerIcons` and `routeTypeBadge` to the
    destructured import from `../components.js`. Remove `typeEmoji` from the
    import if it is no longer used elsewhere in the file (verify: `typeEmoji`
    is only used at line 51 in `renderRecentAds`, so it can be dropped).
  - **Remove the `.slice(0, 5)`** call (line 38) so all 10 rows render.
  - **Rewrite the table** to four columns. Replace the current `<thead>` and
    row template:
    ```js
    function renderRecentAds(ads) {
        if (!ads || ads.length === 0) {
            return html`<p class="text-sm opacity-70">${t('common.no_entity_yet', { entity: t('entities.advertisements').toLowerCase() })}</p>`;
        }
        const rows = ads.map(ad => {
            const friendlyName = ad.tag_name || ad.name;
            const displayName = friendlyName || (ad.public_key.slice(0, 12) + '...');
            const keyLine = friendlyName
                ? html`<div class="text-xs opacity-50 font-mono">${ad.public_key.slice(0, 12)}...</div>`
                : nothing;
            let observersBlock;
            if (ad.observers && ad.observers.length >= 1) {
                observersBlock = html`${observerIcons(ad.observers)}`;
            } else if (ad.observed_by) {
                observersBlock = html`<span class="opacity-50">\u{1F4E1}</span>`;
            } else {
                observersBlock = html`<span class="opacity-50">-</span>`;
            }
            return html`<tr>
                <td>
                    <a href="/nodes/${ad.public_key}" class="link link-hover">
                        <div class="font-medium">${displayName}</div>
                    </a>
                    ${keyLine}
                </td>
                <td>${routeTypeBadge(ad.route_type)}</td>
                <td class="text-right text-sm opacity-70">${formatTimeOnly(ad.received_at)}</td>
                <td>${observersBlock}</td>
            </tr>`;
        });

        return html`<div class="overflow-x-auto">
            <table class="table table-sm w-full">
                <thead>
                    <tr>
                        <th>${t('entities.node')}</th>
                        <th>${t('common.type')}</th>
                        <th class="text-right">${t('common.received')}</th>
                        <th>${t('common.observers')}</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }
    ```

### Phase 4: Tests & verification

- **`tests/test_api/test_dashboard.py`**:
  - **Existing test `test_recent_ads_excludes_direct`** (line 659): the flood ad
    already has `route_type="flood"`. Add assertions:
    ```python
    assert data["recent_advertisements"][0]["route_type"] == "flood"
    assert data["recent_advertisements"][0]["observers"] == []
    assert data["recent_advertisements"][0]["observed_by"] is None
    ```
  - **Existing test `test_recent_advertisements_includes_tag_name`** (line 847):
    the ad has `route_type="flood"` but no `event_hash`. Assert:
    ```python
    assert data["recent_advertisements"][0]["route_type"] == "flood"
    assert data["recent_advertisements"][0]["observers"] == []
    assert data["recent_advertisements"][0]["observed_by"] is None
    ```
  - **New test `test_recent_advertisements_includes_observers`**: Create an
    observer `Node`, an `Advertisement` with an `event_hash`, and an
    `EventObserver` row linking them. Assert that `recent_advertisements[0]` has
    `observers` with length 1 and the observer's `public_key` matches. Mirror
    the fixture style of `test_api/test_advertisements.py:40-66`.
  - **New test `test_recent_advertisements_includes_observed_by`**: Create an
    observer `Node` (public key `OBSERVERKEY...`), set
    `advertisement.observer_node_id = observer_node.id`, no `event_hash` / no
    `EventObserver` row. Assert that `data["recent_advertisements"][0]` has
    `observers == []` and `observed_by == "OBSERVERKEY..."`, covering the
    satellite-emoji fallback path.
- Run `pytest --no-cov tests/test_api/test_dashboard.py`.
- Run `pre-commit run --all-files`.
- `make build` then visually verify the `/dashboard` Recent Adverts card: route
  type badges appear, observer count badges appear, 10 rows shown, time column
  retained.

## Review

**Status**: Approved

**Reviewed**: 2026-07-03

### Resolutions

- **`observed_by` on `RecentAdvertisement`**: Add the field. The backend resolves
  `advertisement.observer_node_id → Node.public_key` for each recent ad (batched
  query) and populates `observed_by` on the schema. The frontend uses the
  full three-way fallback: `ad.observers` array → `ad.observed_by` (satellite
  emoji) → dash. A new test `test_recent_advertisements_includes_observed_by`
  covers this path.

### Remaining Action Items

- (none)

## References

- `docs/plans/20260703-1330-dashboard-packets-widget/plan.md` — prior dashboard
  restructure (removed stat boxes, added chart-card corner numbers, added
  Packets chart). This plan continues polishing the dashboard's bottom section.
- `docs/plans/20260614-1220-observer-filter-badges/plan.md` — introduced the
  `observerIcons` helper and observer badge rendering pattern used here.
- `docs/plans/20260515-1900-recent-adverts-timestamps/plan.md` — prior work on
  the recent-adverts data path (added `public_key` filter to the advertisements
  API for the node-detail page; the dashboard path is separate).
- `src/meshcore_hub/api/observer_utils.py` — `fetch_observers_for_events()`,
  the batch observer-resolution utility reused by this plan.
- `src/meshcore_hub/api/routes/advertisements.py:210-243` — the reference
  implementation of observer/route-type population in the advertisements list
  endpoint.
