# Infra Node Refactor — Task Checklist

**Plan:** `docs/plans/20260503-1800-infra-node-refactor/plan.md`
**Status:** Not Started

---

## Phase 1: Update Server-Side Map Data

- [ ] **1.1** `src/meshcore_hub/web/app.py` — Replace `is_infra: role == "infra"` with `is_adopted: adopted_info is not None` in node dict construction (L743)
- [ ] **1.2** `src/meshcore_hub/web/app.py` — Rename `infra_nodes` → `adopted_nodes` variable and filter (L754)
- [ ] **1.3** `src/meshcore_hub/web/app.py` — Rename `infra_center` → `adopted_center` and update centroid computation (L767–772)
- [ ] **1.4** `src/meshcore_hub/web/app.py` — Update JSONResponse to use `adopted_center` and `adopted_nodes` in debug (L774–787)

## Phase 2: Update Prometheus Metrics

- [ ] **2.1** `src/meshcore_hub/api/metrics.py` — Add `UserProfileNode` to import block (L14–23); it is NOT currently imported
- [ ] **2.2** `src/meshcore_hub/api/metrics.py` — Replace `role` label with `adopted` label on `meshcore_node_last_seen_timestamp_seconds` gauge (L147–152)
- [ ] **2.3** `src/meshcore_hub/api/metrics.py` — Replace `NodeTag` role subquery with `UserProfileNode` existence subquery (L154–158)
- [ ] **2.4** `src/meshcore_hub/api/metrics.py` — Update query to use `adopted_subq` and compute `is_adopted` boolean (L159–169)
- [ ] **2.5** `src/meshcore_hub/api/metrics.py` — Update label assignment to use `adopted="true"/"false"` (L170–176)
- [ ] **2.6** `src/meshcore_hub/api/metrics.py` — Add `meshcore_nodes_adopted` gauge (count of `UserProfileNode` rows)
- [ ] **2.7** `src/meshcore_hub/api/metrics.py` — Remove `NodeTag` from import list (no longer used)

## Phase 3: Update Prometheus Alert Rule

- [ ] **3.1** `etc/prometheus/alerts.yml` — Change `role="infra"` to `adopted="true"` in expression (L10)
- [ ] **3.2** `etc/prometheus/alerts.yml` — Update summary and description annotations to reference "adopted" (L15–16)

## Phase 4: Update Map Client (new colors + OIDC-conditional logic)

- [ ] **4.1** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Add `oidcEnabled` parameter to `createNodeIcon(node, oidcEnabled)` signature
- [ ] **4.2** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Add `oidcEnabled` parameter to `createPopupContent(node, oidcEnabled)` signature
- [ ] **4.3** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Update call sites (L295–296) to pass `config.oidc_enabled` to `createNodeIcon()` and `createPopupContent()`
- [ ] **4.4** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Change icon colors in `createNodeIcon()`: adopted = blue `#3b82f6`/`#1e40af`, normal = green `#22c55e`/`#15803d`; gate adopted color on `oidcEnabled` parameter (L52–54)
- [ ] **4.5** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Change popup indicator colors in `createPopupContent()`: match new blue/green scheme; gate on `oidcEnabled` parameter (L87–91)
- [ ] **4.6** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Rename `infraCenter` param to `adoptedCenter` in `getAnchorPoint()` (L25–26)
- [ ] **4.7** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Rename `infraCenter` to `adoptedCenter` in data destructuring (L125)
- [ ] **4.8** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Gate "Infrastructure Only" `<option>` on `config.oidc_enabled` using conditional lit-html (L202–204)
- [ ] **4.9** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Wrap legend section in `config.oidc_enabled` conditional; update legend colors to blue (Infrastructure) / green (Public) (L252–260)
- [ ] **4.10** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Rename `infraCenter` to `adoptedCenter` in `applyFilters()` anchor call (L152)
- [ ] **4.11** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Change `node.is_infra` to `node.is_adopted` in `applyFiltersCore()` filter (L286)
- [ ] **4.12** `src/meshcore_hub/web/static/js/spa/pages/map.js` — Wrap initial map centering in `config.oidc_enabled` check — skip adopted-centering when OIDC disabled (L330–340)

## Phase 5: Alembic Migration — Remove Obsolete Tags

- [ ] **5.1** `alembic/versions/` — Create new migration chained to `d7a9bbe85a9e` with `DELETE FROM node_tags WHERE key = 'role' AND value = 'infra'`
- [ ] **5.2** `alembic/versions/` — Add `DELETE FROM node_tags WHERE key = 'member_id'` to same migration upgrade()
- [ ] **5.3** Verify migration runs cleanly: `meshcore-hub db upgrade`

## Phase 6: Update Seed Files

- [ ] **6.1** `example/seed/node_tags.yaml` — Remove `role: gateway` tag from example node (L19)
- [ ] **6.2** `seed/node_tags.yaml` — Remove any `role` or `member_id` entries if present

## Phase 7: Update Tests

- [ ] **7.1** `tests/test_web/test_map.py` — Update `test_map_data_includes_infra_center`: mock `adopted_by` instead of role tag, assert `adopted_center` (L281–320)
- [ ] **7.2** `tests/test_web/test_map.py` — Update `test_map_data_infra_center_null_when_no_infra`: assert `adopted_center` is None (L322–350)
- [ ] **7.3** `tests/test_web/test_map.py` — Update `test_map_data_sets_is_infra_flag`: assert `is_adopted` flag (L352–390)
- [ ] **7.4** `tests/test_web/test_map.py` — Update `test_map_data_debug_includes_infra_count`: assert `adopted_nodes` count (L392–420)
- [ ] **7.5** `tests/test_web/test_map.py` — Rename `TestMapDataInfrastructure` class to `TestMapDataAdoptedNodes`
- [ ] **7.6** `tests/test_api/test_metrics.py` — Rewrite `test_node_last_seen_timestamp_with_role` as `test_node_last_seen_timestamp_with_adoption` using `UserProfile` + `UserProfileNode` (L199–225)
- [ ] **7.7** `tests/test_api/test_metrics.py` — Update imports (L16): add `UserProfile`, `UserProfileNode` alongside existing `Node, NodeTag`
- [ ] **7.8** `tests/test_api/test_metrics.py` — Update `test_node_last_seen_timestamp_present` (L174) to assert `adopted="false"` (rename to `test_node_last_seen_timestamp_no_adoption`)
- [ ] **7.9** `tests/test_api/test_metrics.py` — Add `test_nodes_adopted_metric` to verify `meshcore_nodes_adopted` gauge
- [ ] **7.10** Run `pytest tests/test_web/test_map.py tests/test_api/test_metrics.py -v`

## Phase 8: Update i18n Documentation

- [ ] **8.1** `docs/i18n.md` — Update `map.infrastructure_only` and `map.infrastructure` entries to note adoption-based data source and OIDC dependency

## Phase 9: Update Project Documentation

- [ ] **9.1** `AGENTS.md` — Remove `role` from Standard Node Tags table; note adoption as infrastructure source
- [ ] **9.2** `README.md` — Update any references to `role=infra`, `infra_center`, or infrastructure node behavior
- [ ] **9.3** `docs/seeding.md` — Remove `role: gateway` from YAML example (L43); replace with non-`role`-centric tag
- [ ] **9.4** `docs/upgrading.md` — Add upgrade note about Prometheus label change, map API changes, icon color change, and Alembic migration

---

## File Change Summary

| # | File | Action | Phase(s) |
|---|------|--------|----------|
| 1 | `src/meshcore_hub/web/app.py` | Modify | 1 |
| 2 | `src/meshcore_hub/api/metrics.py` | Modify | 2 |
| 3 | `etc/prometheus/alerts.yml` | Modify | 3 |
| 4 | `src/meshcore_hub/web/static/js/spa/pages/map.js` | Modify | 4 |
| 5 | `alembic/versions/..._remove_obsolete_node_tags.py` | Create | 5 |
| 6 | `example/seed/node_tags.yaml` | Modify | 6 |
| 7 | `tests/test_web/test_map.py` | Modify | 7 |
| 8 | `tests/test_api/test_metrics.py` | Modify | 7 |
| 9 | `docs/i18n.md` | Modify | 8 |
| 10 | `AGENTS.md` | Modify | 9 |
| 11 | `README.md` | Modify | 9 |
| 12 | `docs/seeding.md` | Modify | 9 |
| 13 | `docs/upgrading.md` | Modify | 9 |
