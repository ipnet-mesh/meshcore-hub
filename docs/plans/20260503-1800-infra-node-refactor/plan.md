# Infra Node Refactor — Replace `role=infra` Tag with Adopted Nodes

**Date:** 2026-05-03
**Status:** Draft

## Overview

Replace the `role=infra` NodeTag convention with the existing UserProfileNode adoption model as the source of truth for "infrastructure" status. Currently, infrastructure nodes are identified by a `role=infra` tag, which is a manual, unstructured convention. The adoption system (`user_profile_nodes` table) already links operators to nodes in a first-class, enforced relationship. This refactor makes adopted nodes the canonical infrastructure indicator across the Map, Prometheus metrics, and alerting.

No new models or tables. No new API endpoints. An Alembic migration is included to clean up obsolete tags.

## Decisions

1. **Adopted = Infrastructure** — A node is considered "infrastructure" if it has a record in the `user_profile_nodes` table (i.e., it has been adopted by an operator). The `is_infra` concept is renamed to `is_adopted` throughout.

2. **Promote `adopted` label over `role` tag** — The `meshcore_node_last_seen_timestamp_seconds` metric changes from a `role` label (derived from `NodeTag`) to an `adopted` boolean label (`"true"`/`"false"`). This is a breaking change for existing Prometheus queries.

3. **Retain the `role` tag for display** — The `role` tag is still read and displayed in map popups (line `roleHtml` in `map.js`), but it no longer drives the infrastructure/public icon distinction. The map icon color and filter now use adoption status.

4. **Rename `infra_center` to `adopted_center`** — The server-computed geographic centroid of infrastructure/adopted nodes is renamed for clarity. The API response field changes from `infra_center` to `adopted_center`.

5. **Rename `infra_nodes` debug field to `adopted_nodes`** — The debug count in map data is renamed for consistency.

6. **Map category filter changes** — The "Infrastructure Only" filter option now shows only adopted nodes. The label remains "Infrastructure Only" (existing i18n key `map.infrastructure_only`) since the user-facing concept is unchanged.

7. **Prometheus alert rule updated** — The `NodeNotSeen` alert changes from `role="infra"` selector to `adopted="true"` selector. This is a documentation + config change in `etc/prometheus/alerts.yml`.

8. **No `role` tag filter in metrics query** — The metrics `collect_metrics()` function replaces the `NodeTag` subquery JOIN with a `UserProfileNode` existence check. This is simpler and uses the enforced relationship.

9. **OIDC-disabled = no adoption UI** — When `OIDC_ENABLED=false`, there are no user profiles and therefore no adopted nodes. The map must not display adoption-dependent UI elements: no "Infrastructure Only" filter option, no icon distinction, no indicator dot in popups, and no legend. All nodes render identically (green markers) since the adoption concept does not apply. The server still computes `adopted_center` and `is_adopted` fields (they will always be `null`/`false`), but the client ignores them when OIDC is disabled.

10. **Data cleanup via Alembic migration** — An Alembic migration removes obsolete `role=infra` and `member_id` tags from the `node_tags` table. These tags are superseded by the adoption system and should not linger in the database.

11. **Add `meshcore_nodes_adopted` metric** — A new Prometheus gauge exposes the count of adopted nodes, complementing the existing `meshcore_nodes_total` and `meshcore_nodes_active` metrics.

12. **New map icon colors: green (normal) and blue (adopted)** — The existing red (#ef4444) for infrastructure nodes is confusing (red implies offline/broken). Colors change to green (#22c55e / #15803d) for normal nodes and blue (#3b82f6 / #1e40af) for adopted nodes.

## Terminology

| Term | Meaning |
|---|---|
| Adopted node | A node with a record in `user_profile_nodes`, linked to an operator's `UserProfile` |
| `is_adopted` | Boolean flag replacing `is_infra` — true when the node has an adoption record |
| `adopted_center` | Geographic centroid of all adopted nodes (replaces `infra_center`) |
| `adopted` label | Prometheus metric label (`"true"`/`"false"`) replacing `role` tag-derived value |
| `role` tag | Optional NodeTag with key `"role"` — retained for display, no longer drives infra logic |
| `member_id` tag | Obsolete NodeTag key from the pre-adoption member system — removed by migration |
| OIDC-disabled | Deployment where `OIDC_ENABLED=false`; no user profiles, no adoption, no infra distinction |

## Current State

### How `role=infra` Works Today

| Layer | File | Lines | What it does |
|-------|------|-------|-------------|
| **Server map data** | `web/app.py` | 707–708, 743 | Iterates node tags looking for `key == "role"`, sets `role` variable. Sets `is_infra: role == "infra"` on each node dict. |
| **Server infra center** | `web/app.py` | 754–772 | Filters nodes where `is_infra` is truthy, computes `infra_center` centroid. Passes `infra_nodes` count in debug. |
| **Map client — icon** | `map.js` | 52–54 | `node.is_infra` chooses red (#ef4444) vs blue (#3b82f6) marker icon |
| **Map client — popup** | `map.js` | 86–92 | `node.is_infra` renders a colored dot indicator with "Infrastructure"/"Public" title |
| **Map client — filter** | `map.js` | 202–204, 286 | Category dropdown with "Infrastructure Only" option filters on `node.is_infra` |
| **Map client — centering** | `map.js` | 25–31, 125, 330–340 | `infraCenter` from server used as anchor point; initial map fit to infra nodes bounds |
| **Map client — legend** | `map.js` | 252–260 | Red = Infrastructure, Blue = Public |
| **Prometheus metrics** | `api/metrics.py` | 147–176 | LEFT JOINs `NodeTag` where `key == "role"`, exposes `role` label on `meshcore_node_last_seen_timestamp_seconds` |
| **Prometheus alert** | `etc/prometheus/alerts.yml` | 9–16 | `NodeNotSeen` alert selects `role="infra"` nodes not seen for 48h |

### How Adopted Nodes Already Work

| Layer | File | Lines | What it does |
|-------|------|-------|-------------|
| **Model** | `common/models/user_profile_node.py` | 20–60 | Join table `user_profile_nodes` with composite PK, unique constraint on `node_id` (one adopter per node) |
| **API adopt/release** | `api/routes/adoptions.py` | — | `POST /api/v1/adoptions` (operator/admin), `DELETE /api/v1/adoptions/{public_key}` |
| **Node API** | `api/routes/nodes.py` | 17–34, 45–47 | `_get_adopted_by()` extracts adopter info; `adopted_by` query param filters nodes |
| **Node schema** | `common/schemas/nodes.py` | 75–85, 103–105 | `AdoptedByUser` schema; `NodeRead.adopted_by` optional field |
| **Map server** | `web/app.py` | 726–732 | Already reads `adopted_by` from API response and sets `owner` on node dict |
| **Map client** | `map.js` | 69–76, 218–233 | Popups show owner info; member dropdown conditionally shown when `config.oidc_enabled` |

### OIDC-Conditional Pattern (Existing)

The codebase already uses `config.oidc_enabled` to conditionally render OIDC-dependent UI:

| File | Line | Condition |
|------|------|-----------|
| `map.js` | 218 | `config.oidc_enabled && profiles.length > 0` — member filter dropdown |
| `nodes.js` | 57, 147 | `config.oidc_enabled` — adopted_by filter, profile select |
| `advertisements.js` | 60, 191 | `config.oidc_enabled` — adopted_by filter, profile select |
| `node-detail.js` | 296 | `!config.oidc_enabled \|\| !config.user` — hide adoption section |
| `components.js` | 36, 597 | `config.oidc_enabled` — role checks, auth section |

### Obsolete Tags

| Tag Key | Status | Why obsolete |
|---------|--------|-------------|
| `role` (value=`infra`) | Superseded | Adoption status (`user_profile_nodes`) now determines infrastructure |
| `member_id` | Superseded | The old member→node mapping system was replaced by the adoption model (`UserProfileNode`) |

These tags may exist in existing databases. The Alembic migration (Phase 5) will clean them up.

### Seed Files

| File | Contains | Action needed |
|------|----------|---------------|
| `example/seed/node_tags.yaml` | `role: gateway` on example node | Remove `role` key from example |
| `seed/node_tags.yaml` | If present, may contain `role` or `member_id` entries | Remove those keys |

### Tests

| Test File | Tests | Lines |
|-----------|-------|-------|
| `tests/test_web/test_map.py` | `TestMapDataInfrastructure` (4 tests) | 278–420 |
| `tests/test_api/test_metrics.py` | `test_node_last_seen_timestamp_with_role` | 199–225 |

---

## Implementation

### Phase 1: Update Server-Side Map Data (`web/app.py`)

**File:** `src/meshcore_hub/web/app.py`

Replace the `role=infra` detection with adoption-based detection.

#### 1.1 Change node dict construction (L742–744)

```python
# Before:
"role": role,
"is_infra": role == "infra",
"owner": owner,

# After:
"role": role,
"is_adopted": adopted_info is not None,
"owner": owner,
```

The `role` tag is still read and passed through for display in popups. The `is_infra` key becomes `is_adopted`, sourced from whether the node has `adopted_by` data (which the API already populates).

Note: `adopted_info` is already computed at L726 (`adopted_info = node.get("adopted_by")`).

#### 1.2 Rename infra_center to adopted_center (L754–772)

```python
# Before (L754):
infra_nodes = [n for n in nodes_with_location if n.get("is_infra")]
infra_count = len(infra_nodes)

# After:
adopted_nodes = [n for n in nodes_with_location if n.get("is_adopted")]
adopted_count = len(adopted_nodes)
```

```python
# Before (L767):
infra_center: dict[str, float] | None = None
if infra_nodes:
    infra_center = {
        "lat": sum(n["lat"] for n in infra_nodes) / len(infra_nodes),
        "lon": sum(n["lon"] for n in infra_nodes) / len(infra_nodes),
    }

# After:
adopted_center: dict[str, float] | None = None
if adopted_nodes:
    adopted_center = {
        "lat": sum(n["lat"] for n in adopted_nodes) / len(adopted_nodes),
        "lon": sum(n["lon"] for n in adopted_nodes) / len(adopted_nodes),
    }
```

#### 1.3 Update response dict (L774–787)

```python
# Before:
return JSONResponse({
    "nodes": nodes_with_location,
    "profiles": list(profiles_by_id.values()),
    "center": {"lat": center_lat, "lon": center_lon},
    "infra_center": infra_center,
    "debug": {
        "total_nodes": total_nodes,
        "nodes_with_coords": nodes_with_coords,
        "infra_nodes": infra_count,
        "error": error,
    },
})

# After:
return JSONResponse({
    "nodes": nodes_with_location,
    "profiles": list(profiles_by_id.values()),
    "center": {"lat": center_lat, "lon": center_lon},
    "adopted_center": adopted_center,
    "debug": {
        "total_nodes": total_nodes,
        "nodes_with_coords": nodes_with_coords,
        "adopted_nodes": adopted_count,
        "error": error,
    },
})
```

### Phase 2: Update Prometheus Metrics (`api/metrics.py`)

**File:** `src/meshcore_hub/api/metrics.py`

Replace the `role` label (from NodeTag) with `adopted` label (from UserProfileNode), and add a new `meshcore_nodes_adopted` gauge.

#### 2.1 Add `UserProfileNode` to imports

`UserProfileNode` is **not** currently imported in `metrics.py` (L14–23). Add it to the import block:

```python
from meshcore_hub.common.models import (
    Advertisement,
    EventLog,
    Message,
    Node,
    Telemetry,
    TracePath,
    UserProfile,
    UserProfileNode,  # ADD
)
```

`NodeTag` can be removed from the import list after the refactor (no longer used).

#### 2.2 Replace the node_last_seen gauge query (L147–176)

```python
# Before:
node_last_seen = Gauge(
    "meshcore_node_last_seen_timestamp_seconds",
    "Unix timestamp of when the node was last seen",
    ["public_key", "node_name", "adv_type", "role"],
    registry=registry,
)
role_subq = (
    select(NodeTag.node_id, NodeTag.value.label("role"))
    .where(NodeTag.key == "role")
    .subquery()
)
nodes_with_last_seen = session.execute(
    select(
        Node.public_key,
        Node.name,
        Node.adv_type,
        Node.last_seen,
        role_subq.c.role,
    )
    .outerjoin(role_subq, Node.id == role_subq.c.node_id)
    .where(Node.last_seen.isnot(None))
).all()
for public_key, name, adv_type, last_seen, role in nodes_with_last_seen:
    node_last_seen.labels(
        public_key=public_key,
        node_name=name or "",
        adv_type=adv_type or "unknown",
        role=role or "",
    ).set(last_seen.timestamp())

# After:
node_last_seen = Gauge(
    "meshcore_node_last_seen_timestamp_seconds",
    "Unix timestamp of when the node was last seen",
    ["public_key", "node_name", "adv_type", "adopted"],
    registry=registry,
)
adopted_subq = (
    select(UserProfileNode.node_id)
    .subquery()
)
nodes_with_last_seen = session.execute(
    select(
        Node.public_key,
        Node.name,
        Node.adv_type,
        Node.last_seen,
        adopted_subq.c.node_id.isnot(None).label("is_adopted"),
    )
    .outerjoin(adopted_subq, Node.id == adopted_subq.c.node_id)
    .where(Node.last_seen.isnot(None))
).all()
for public_key, name, adv_type, last_seen, is_adopted in nodes_with_last_seen:
    node_last_seen.labels(
        public_key=public_key,
        node_name=name or "",
        adv_type=adv_type or "unknown",
        adopted="true" if is_adopted else "false",
    ).set(last_seen.timestamp())
```

#### 2.3 Add `meshcore_nodes_adopted` gauge

Insert after the `nodes_with_location` gauge (after L145), before the node_last_seen gauge:

```python
nodes_adopted = Gauge(
    "meshcore_nodes_adopted",
    "Number of adopted nodes (nodes with an adoption record)",
    registry=registry,
)
adopted_count = (
    session.execute(select(func.count(UserProfileNode.node_id))).scalar() or 0
)
nodes_adopted.set(adopted_count)
```

#### 2.4 Remove `NodeTag` import

`NodeTag` is only used in the `role_subq` block. After replacing it with `UserProfileNode`, remove `NodeTag` from the import list (L19).

### Phase 3: Update Prometheus Alert Rule (`etc/prometheus/alerts.yml`)

**File:** `etc/prometheus/alerts.yml`

```yaml
# Before:
- alert: NodeNotSeen
  expr: time() - meshcore_node_last_seen_timestamp_seconds{role="infra"} > 48 * 3600
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Node {{ $labels.node_name }} ({{ $labels.role }}) not seen for 48+ hours"
    description: "Node {{ $labels.public_key }} ({{ $labels.adv_type }}, role={{ $labels.role }}) last seen {{ $value | humanizeDuration }} ago."

# After:
- alert: NodeNotSeen
  expr: time() - meshcore_node_last_seen_timestamp_seconds{adopted="true"} > 48 * 3600
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Adopted node {{ $labels.node_name }} not seen for 48+ hours"
    description: "Adopted node {{ $labels.public_key }} ({{ $labels.adv_type }}) last seen {{ $value | humanizeDuration }} ago."
```

### Phase 4: Update Map Client (`map.js`)

**File:** `src/meshcore_hub/web/static/js/spa/pages/map.js`

All adoption-dependent UI is gated on `config.oidc_enabled`. When OIDC is disabled, the map renders all nodes with identical green markers, no infrastructure filter, no legend, and no indicator dots.

Icon colors change from red (infra) / blue (normal) to **blue (adopted) / green (normal)**.

| Node type | Before | After |
|-----------|--------|-------|
| Adopted (OIDC enabled) | Red `#ef4444` / `#b91c1c` | Blue `#3b82f6` / `#1e40af` |
| Normal | Blue `#3b82f6` / `#1e40af` | Green `#22c55e` / `#15803d` |
| All nodes (OIDC disabled) | Red/blue split | Green only |

#### 4.1 Add `oidcEnabled` parameter to `createNodeIcon()` and `createPopupContent()` signatures

Both functions currently take only `node`. Add `oidcEnabled` as a second parameter:

```javascript
// Before:
function createNodeIcon(node) {
function createPopupContent(node) {

// After:
function createNodeIcon(node, oidcEnabled) {
function createPopupContent(node, oidcEnabled) {
```

Update the call sites (L295–296) to pass `config.oidc_enabled`:

```javascript
// Before at L295–296:
const marker = L.marker([node.lat, node.lon], { icon: createNodeIcon(node) }).addTo(map);
marker.bindPopup(createPopupContent(node));

// After:
const marker = L.marker([node.lat, node.lon], { icon: createNodeIcon(node, config.oidc_enabled) }).addTo(map);
marker.bindPopup(createPopupContent(node, config.oidc_enabled));
```

#### 4.2 Update `createNodeIcon()` — new colors + conditional (L47–54, L295)

```javascript
// Before:
const iconHtml = node.is_infra
    ? '<div style="width: 12px; height: 12px; background: #ef4444; border: 2px solid #b91c1c; border-radius: 50%; box-shadow: 0 0 4px rgba(239,68,68,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>'
    : '<div style="width: 12px; height: 12px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';

// After:
const iconHtml = (oidcEnabled && node.is_adopted)
    ? '<div style="width: 12px; height: 12px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>'
    : '<div style="width: 12px; height: 12px; background: #22c55e; border: 2px solid #15803d; border-radius: 50%; box-shadow: 0 0 4px rgba(34,197,94,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';
```

Adopted nodes get blue markers. Normal nodes (and all nodes when OIDC disabled) get green markers.

#### 4.3 Update `createPopupContent()` — conditional indicator with new colors (L86–92)

```javascript
// Before (L87):
if (typeof node.is_infra !== 'undefined') {
    const dotColor = node.is_infra ? '#ef4444' : '#3b82f6';
    const borderColor = node.is_infra ? '#b91c1c' : '#1e40af';
    const title = node.is_infra ? t('map.infrastructure') : t('map.public');

// After:
if (oidcEnabled && typeof node.is_adopted !== 'undefined') {
    const dotColor = node.is_adopted ? '#3b82f6' : '#22c55e';
    const borderColor = node.is_adopted ? '#1e40af' : '#15803d';
    const title = node.is_adopted ? t('map.infrastructure') : t('map.public');
```

The popup indicator dot is only rendered when OIDC is enabled. When OIDC is disabled, `infraIndicatorHtml` stays empty and no dot appears.

#### 4.4 Update `getAnchorPoint()` — rename parameter (L25)

```javascript
// Before:
function getAnchorPoint(nodes, infraCenter) {
    if (infraCenter) return infraCenter;

// After:
function getAnchorPoint(nodes, adoptedCenter) {
    if (adoptedCenter) return adoptedCenter;
```

#### 4.5 Update data destructuring — rename variable (L125)

```javascript
// Before:
const infraCenter = data.infra_center || null;

// After:
const adoptedCenter = data.adopted_center || null;
```

#### 4.6 Update category filter — conditional on OIDC (L202–204)

```javascript
// Before:
<select id="filter-category" class="select select-bordered select-sm" @change=${applyFilters}>
    <option value="">${t('common.all_entity', { entity: t('entities.nodes') })}</option>
    <option value="infra">${t('map.infrastructure_only')}</option>
</select>

// After:
<select id="filter-category" class="select select-bordered select-sm" @change=${applyFilters}>
    <option value="">${t('common.all_entity', { entity: t('entities.nodes') })}</option>
    ${config.oidc_enabled ? html`<option value="infra">${t('map.infrastructure_only')}</option>` : nothing}
</select>
```

When OIDC is disabled, the dropdown shows only "All Nodes".

#### 4.7 Update legend — conditional on OIDC with new colors (L252–260)

```javascript
// Before:
<div class="mt-4 flex flex-wrap gap-4 items-center text-sm">
    <span class="opacity-70">${t('map.legend')}</span>
    <div class="flex items-center gap-1">
        <div style="width: 10px; ... background: #ef4444; ..."></div>
        <span>${t('map.infrastructure')}</span>
    </div>
    <div class="flex items-center gap-1">
        <div style="width: 10px; ... background: #3b82f6; ..."></div>
        <span>${t('map.public')}</span>
    </div>
</div>

// After:
${config.oidc_enabled ? html`
<div class="mt-4 flex flex-wrap gap-4 items-center text-sm">
    <span class="opacity-70">${t('map.legend')}</span>
    <div class="flex items-center gap-1">
        <div style="width: 10px; height: 10px; background: #3b82f6; border: 2px solid #1e40af; border-radius: 50%;"></div>
        <span>${t('map.infrastructure')}</span>
    </div>
    <div class="flex items-center gap-1">
        <div style="width: 10px; height: 10px; background: #22c55e; border: 2px solid #15803d; border-radius: 50%;"></div>
        <span>${t('map.public')}</span>
    </div>
</div>
` : nothing}
```

Legend now shows: blue = Infrastructure, green = Public. Hidden entirely when OIDC disabled.

#### 4.8 Update `applyFilters()` — rename variable (L152)

```javascript
// Before:
if (categoryFilter !== 'infra') {
    const anchor = getAnchorPoint(filteredNodes, infraCenter);

// After:
if (categoryFilter !== 'infra') {
    const anchor = getAnchorPoint(filteredNodes, adoptedCenter);
```

#### 4.9 Update `applyFiltersCore()` — use `is_adopted` (L286)

```javascript
// Before (L286):
if (categoryFilter === 'infra' && !node.is_infra) return false;

// After:
if (categoryFilter === 'infra' && !node.is_adopted) return false;
```

This filter only activates when the user selects "Infrastructure Only" from the dropdown, which is only present when OIDC is enabled (Phase 4.6).

#### 4.10 Update initial map centering — conditional on OIDC (L330–340)

```javascript
// Before (L330–340):
const infraNodes = allNodes.filter(n => n.is_infra);
if (infraNodes.length > 0) {
    const bounds = L.latLngBounds(infraNodes.map(n => [n.lat, n.lon]));
    map.fitBounds(bounds, { padding: BOUNDS_PADDING });
} else if (allNodes.length > 0) {
    const anchor = getAnchorPoint(allNodes, infraCenter);
    const nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
    const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
    const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
    map.fitBounds(bounds, { padding: BOUNDS_PADDING });
}

// After:
if (config.oidc_enabled) {
    const adoptedNodes = allNodes.filter(n => n.is_adopted);
    if (adoptedNodes.length > 0) {
        const bounds = L.latLngBounds(adoptedNodes.map(n => [n.lat, n.lon]));
        map.fitBounds(bounds, { padding: BOUNDS_PADDING });
    } else if (allNodes.length > 0) {
        const anchor = getAnchorPoint(allNodes, adoptedCenter);
        const nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
        const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
        const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
        map.fitBounds(bounds, { padding: BOUNDS_PADDING });
    }
} else if (allNodes.length > 0) {
    const anchor = getAnchorPoint(allNodes, null);
    const nearbyNodes = getNodesWithinRadius(allNodes, anchor.lat, anchor.lon, MAX_BOUNDS_RADIUS_KM);
    const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
    const bounds = L.latLngBounds(nodesToFit.map(n => [n.lat, n.lon]));
    map.fitBounds(bounds, { padding: BOUNDS_PADDING });
}
```

### Phase 5: Alembic Migration — Remove Obsolete Tags

**New file:** `alembic/versions/YYYYMMDD_HHMM_<rev>_remove_obsolete_node_tags.py`

Create a new Alembic migration that deletes obsolete `role=infra` and `member_id` tags from the `node_tags` table. This is a data-only migration (no schema changes).

```python
"""remove obsolete role and member_id node tags

Revision ID: <auto>
Revises: d7a9bbe85a9e
Create Date: <auto>

"""
from typing import Sequence, Union

from alembic import op

revision: str = "<auto>"
down_revision: Union[str, None] = "d7a9bbe85a9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM node_tags WHERE key = 'role' AND value = 'infra'"
    )
    op.execute(
        "DELETE FROM node_tags WHERE key = 'member_id'"
    )


def downgrade() -> None:
    pass
```

Notes:
- Uses raw SQL (`op.execute`) since it's a data migration, not a schema change
- `downgrade()` is intentionally empty — these obsolete tags should not be restored
- Targets `role=infra` specifically (not all `role` tags — users may have `role=gateway` etc.)
- Removes all `member_id` tags unconditionally (the key is fully obsolete)
- `down_revision` chains to `d7a9bbe85a9e` (current HEAD: `add_description_and_url_to_user_profiles`)

### Phase 6: Update Seed Files

**File:** `example/seed/node_tags.yaml`

Remove the `role: gateway` tag from the example node (L19). The `role` tag is no longer a recommended standard tag for infrastructure purposes. The example should only show recommended tags (`friendly_name`, `lat`, `lon`, etc.).

```yaml
# Before:
0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:
  friendly_name: Gateway Node
  role: gateway
  lat: 37.7749
  lon: -122.4194
  is_online: true

# After:
0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:
  friendly_name: Gateway Node
  lat: 37.7749
  lon: -122.4194
  is_online: true
```

**File:** `seed/node_tags.yaml`

If this file exists and contains `role` or `member_id` entries, remove those keys. (This file is gitignored and user-maintained, so the change is advisory.)

### Phase 7: Update Tests

#### 7.1 Map tests (`tests/test_web/test_map.py`)

**File:** `tests/test_web/test_map.py`

Update `TestMapDataInfrastructure` class (L278–420):

All four tests need updating:
- Mock node data should include `adopted_by` field instead of/in addition to `role` tag for adopted nodes
- Assertions should check `adopted_center` instead of `infra_center`
- Assertions should check `is_adopted` instead of `is_infra`
- Debug assertions should check `adopted_nodes` instead of `infra_nodes`

**`test_map_data_includes_infra_center`** (L281):
```python
# Mock data: change adopted node to have adopted_by instead of role tag
{
    "id": "node-1",
    "public_key": "abc123",
    "name": "Adopted Node",
    "lat": 40.0,
    "lon": -74.0,
    "tags": [],
    "adopted_by": {
        "user_id": "user-1",
        "name": "Operator",
        "callsign": "W1ABC",
        "profile_id": "profile-1",
    },
},
# Assertions: assert data["adopted_center"] is not None
```

**`test_map_data_infra_center_null_when_no_infra`** (L322):
```python
# Node without adopted_by → adopted_center is None
assert data["adopted_center"] is None
```

**`test_map_data_sets_is_infra_flag`** (L352):
```python
# Node with adopted_by → is_adopted=True
# Node without adopted_by → is_adopted=False
assert nodes_by_name["Adopted Node"]["is_adopted"] is True
assert nodes_by_name["Regular Node"]["is_adopted"] is False
```

**`test_map_data_debug_includes_infra_count`** (L392):
```python
assert data["debug"]["adopted_nodes"] == 1
```

#### 7.2 Metrics tests (`tests/test_api/test_metrics.py`)

**File:** `tests/test_api/test_metrics.py`

**`test_node_last_seen_timestamp_with_role`** (L199):
- Rename to `test_node_last_seen_timestamp_with_adoption`
- Replace `NodeTag` setup with `UserProfileNode` + `UserProfile` setup
- Change assertion from `role="infra"` to `adopted="true"`
- Add a non-adopted node to verify `adopted="false"`

```python
def test_node_last_seen_timestamp_with_adoption(self, api_db_session, client_no_auth):
    """Test that node_last_seen_timestamp includes adopted label from adoption."""
    seen_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    profile = UserProfile(
        user_id="auth0|test123",
        name="Test Operator",
    )
    api_db_session.add(profile)
    api_db_session.flush()

    adopted_node = Node(
        public_key="adopted1234adopted1234adopted12",
        name="Adopted Node",
        adv_type="REPEATER",
        first_seen=seen_at,
        last_seen=seen_at,
    )
    unadopted_node = Node(
        public_key="unadopted1234unadopted1234unad",
        name="Unadopted Node",
        adv_type="CLIENT",
        first_seen=seen_at,
        last_seen=seen_at,
    )
    api_db_session.add_all([adopted_node, unadopted_node])
    api_db_session.flush()

    adoption = UserProfileNode(
        user_profile_id=profile.id,
        node_id=adopted_node.id,
    )
    api_db_session.add(adoption)
    api_db_session.commit()

    _clear_metrics_cache()
    response = client_no_auth.get("/metrics")
    assert response.status_code == 200
    assert (
        "meshcore_node_last_seen_timestamp_seconds"
        '{adv_type="REPEATER",'
        'node_name="Adopted Node",'
        'public_key="adopted1234adopted1234adopted12",'
        'adopted="true"}'
    ) in response.text
    assert (
        "meshcore_node_last_seen_timestamp_seconds"
        '{adv_type="CLIENT",'
        'node_name="Unadopted Node",'
        'public_key="unadopted1234unadopted1234unad",'
        'adopted="false"}'
    ) in response.text
```

**Add test for `meshcore_nodes_adopted` gauge:**

```python
def test_nodes_adopted_metric(self, api_db_session, client_no_auth):
    """Test that meshcore_nodes_adopted gauge reflects adopted node count."""
    seen_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    profile = UserProfile(user_id="auth0|metric_test", name="Metric Op")
    api_db_session.add(profile)
    api_db_session.flush()

    node1 = Node(public_key="adopted_metric_0000000000000000", first_seen=seen_at, last_seen=seen_at)
    node2 = Node(public_key="unadopted_metric_00000000000000", first_seen=seen_at, last_seen=seen_at)
    api_db_session.add_all([node1, node2])
    api_db_session.flush()

    adoption = UserProfileNode(user_profile_id=profile.id, node_id=node1.id)
    api_db_session.add(adoption)
    api_db_session.commit()

    _clear_metrics_cache()
    response = client_no_auth.get("/metrics")
    assert response.status_code == 200
    assert 'meshcore_nodes_adopted 1.0' in response.text
```

The existing `test_node_last_seen_timestamp_present` test (L174, not `test_node_last_seen_timestamp_no_role`) asserts `role=""`. After the refactor, it must assert `adopted="false"` instead. Rename to `test_node_last_seen_timestamp_no_adoption`.

The metrics test file imports (`tests/test_api/test_metrics.py` L16) must be updated to add `UserProfile` and `UserProfileNode` alongside the existing `Node, NodeTag` import:

### Phase 8: Update i18n Documentation (`docs/i18n.md`)

**File:** `docs/i18n.md`

No i18n key changes needed — the existing `map.infrastructure_only`, `map.infrastructure`, `map.public` labels remain the same since the user-facing terminology is unchanged. The map still says "Infrastructure" and "Infrastructure Only" in the UI (when OIDC is enabled).

Update the i18n.md entry for `map.infrastructure` and `map.infrastructure_only` to note:
- The underlying data source has changed from `role=infra` tag to adoption status
- These keys are only rendered when `OIDC_ENABLED=true`

### Phase 9: Update Project Documentation

**File:** `AGENTS.md`

Update the "Standard Node Tags" section to:
- Remove `role` from the recommended standard tags table (it is now fully freeform, not infrastructure-related)
- Note that infrastructure status is determined by node adoption, not tags

**File:** `README.md`

Update any references to `role=infra`, `infra_center`, or infrastructure node behavior.

**File:** `docs/seeding.md`

Remove `role: gateway` from the node tags YAML example (L43). Replace with a tag that is not `role`-centric (e.g., `is_online` or `description`). The `role` tag is no longer a recommended standard tag.

**File:** `docs/upgrading.md`

Add upgrade note about:
- Prometheus label change (`role` → `adopted`)
- Map API response field changes (`infra_center` → `adopted_center`, `is_infra` → `is_adopted`)
- Map icon color change (red/green → blue/green)
- Alembic migration removes `role=infra` and `member_id` tags automatically

---

## File Change Summary

| # | File | Action | Phase(s) | Description |
|---|------|--------|----------|-------------|
| 1 | `src/meshcore_hub/web/app.py` | Modify | 1 | Replace `is_infra` with `is_adopted`; rename `infra_center`→`adopted_center`, `infra_nodes`→`adopted_nodes` |
| 2 | `src/meshcore_hub/api/metrics.py` | Modify | 2 | Replace `role` label with `adopted` label; add `meshcore_nodes_adopted` gauge; remove `NodeTag` import |
| 3 | `etc/prometheus/alerts.yml` | Modify | 3 | Change alert from `role="infra"` to `adopted="true"` |
| 4 | `src/meshcore_hub/web/static/js/spa/pages/map.js` | Modify | 4 | New colors (blue=adopted, green=normal); replace `is_infra`→`is_adopted`; gate adoption UI on `config.oidc_enabled` |
| 5 | `alembic/versions/..._remove_obsolete_node_tags.py` | Create | 5 | Data migration to delete `role=infra` and `member_id` tags |
| 6 | `example/seed/node_tags.yaml` | Modify | 6 | Remove `role: gateway` from example node |
| 7 | `tests/test_web/test_map.py` | Modify | 7 | Update `TestMapDataInfrastructure` tests for adoption-based logic |
| 8 | `tests/test_api/test_metrics.py` | Modify | 7 | Update role-based test to adoption-based; add `meshcore_nodes_adopted` test |
| 9 | `docs/i18n.md` | Modify | 8 | Note data source change and OIDC dependency in map.* key documentation |
| 10 | `AGENTS.md` | Modify | 9 | Remove `role` from Standard Node Tags; note adoption as infra source |
| 11 | `README.md` | Modify | 9 | Update `role=infra`, `infra_center` references |
| 12 | `docs/seeding.md` | Modify | 9 | Remove `role: gateway` from YAML example |
| 13 | `docs/upgrading.md` | Modify | 9 | Add upgrade notes for all breaking changes |

---

## Execution Order

1. **Phase 1:** Update server-side map data (`web/app.py`)
2. **Phase 2:** Update Prometheus metrics (`api/metrics.py`) — includes `meshcore_nodes_adopted`
3. **Phase 3:** Update Prometheus alert rule (`etc/prometheus/alerts.yml`)
4. **Phase 4:** Update map client (`map.js`) — new colors + OIDC-conditional logic
5. **Phase 5:** Create Alembic migration to remove obsolete `role=infra` and `member_id` tags
6. **Phase 6:** Update seed files (`example/seed/node_tags.yaml`)
7. **Phase 7:** Update tests (`test_map.py`, `test_metrics.py`)
8. **Phase 8:** Update i18n docs (`docs/i18n.md`)
9. **Phase 9:** Update project docs (`AGENTS.md`, `README.md`, `docs/upgrading.md`)

Phases 1–4 are the core code changes. Phase 5 is the data migration. Phase 6 updates seed examples. Phase 7 updates tests. Phases 8–9 are documentation.

---

## Migration Notes

### Prometheus Breaking Change

The `meshcore_node_last_seen_timestamp_seconds` metric changes from:

```
meshcore_node_last_seen_timestamp_seconds{public_key="...", node_name="...", adv_type="...", role="infra"} 1718438400.0
```

to:

```
meshcore_node_last_seen_timestamp_seconds{public_key="...", node_name="...", adv_type="...", adopted="true"} 1718438400.0
```

A new metric is added:

```
meshcore_nodes_adopted 3.0
```

**External users** with custom Prometheus/Grafana dashboards querying `role="infra"` must update to `adopted="true"`.

### Map API Response Change

The `/map/data` response changes:

```diff
{
  "nodes": [...],
  "profiles": [...],
  "center": {...},
- "infra_center": {"lat": 40.0, "lon": -74.0},
+ "adopted_center": {"lat": 40.0, "lon": -74.0},
  "debug": {
    "total_nodes": 10,
    "nodes_with_coords": 8,
-   "infra_nodes": 3,
+   "adopted_nodes": 3,
    "error": null
  }
}
```

Node objects within `nodes` array change:

```diff
{
  "public_key": "...",
  "name": "...",
- "is_infra": true,
+ "is_adopted": true,
  "owner": {...},
  ...
}
```

### Map Icon Color Change

| Node type | Before | After |
|-----------|--------|-------|
| Adopted (OIDC enabled) | Red `#ef4444` | Blue `#3b82f6` |
| Normal | Blue `#3b82f6` | Green `#22c55e` |
| All nodes (OIDC disabled) | N/A (not distinguished) | Green `#22c55e` |

### Database Data Migration

The Alembic migration automatically:
- Deletes all `node_tags` rows where `key = "role"` AND `value = "infra"`
- Deletes all `node_tags` rows where `key = "member_id"`

The migration is non-destructive to other tags. Other `role` values (e.g., `role=gateway`) are preserved. The downgrade is intentionally empty (obsolete tags should not be restored).

### OIDC-Disabled Deployments

When `OIDC_ENABLED=false`:
- `adopted_center` is always `null` (no adoption records exist)
- `adopted_nodes` debug count is always `0`
- All nodes have `is_adopted: false`
- The map shows no filter option for "Infrastructure Only", no legend, no colored indicator dots — all nodes render as green markers
- `meshcore_nodes_adopted` gauge reads `0.0`
- The Prometheus metric still includes the `adopted="false"` label on all nodes — external alerting rules that target `adopted="true"` will simply never fire, which is correct

### No Schema Migration Required

No table schema changes. Only data cleanup (Phase 5) removes obsolete rows from `node_tags`.

---

## Out of Scope (Deferred)

| Item | Reason |
|------|--------|
| Adding an "Adopted Only" filter label | The existing "Infrastructure Only" label is user-appropriate |
