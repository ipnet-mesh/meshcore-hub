# Routes (Route Health Monitoring)

## How it works (overview)

> This section is a plain-language explainer for sharing and discussion. The
> detailed PRD follows below.

MeshCore packets travel across the network by hopping through repeater nodes.
Every packet the hub captures already records the sequence of nodes it passed
through (its **path**). This feature turns that recorded path data into a way
to **monitor whether a route you care about is actually working**.

**The idea, with an example.** Suppose there are known repeaters near Ipswich
and Norwich, and you want to know when traffic stops getting between them.
You'd create a **Route** named "Ipswich ↔ Norwich", pick those two repeater
nodes in order, set a window of "last 24 hours" and a threshold of "3
packets". The hub then continuously asks: *in the last 24 hours, did at least
3 distinct packets travel along a path that passed through the Ipswich
repeater and then the Norwich repeater?* If yes, the route is **healthy**; if
not, it's **unhealthy** and something along that route may be down.

The two nodes don't need to be directly adjacent — a packet counts if it went
Ipswich → …some other repeaters… → Norwich, **in that order**. You can also add
a midpoint node (say, a Cambridge repeater) to make the route more specific
and reduce accidental matches.

**Health, in one line:** a route is healthy when **≥ N distinct packets**, each
seen within the time window, each travelled a path that contains your
configured nodes in the right order (gaps allowed). It also reports a
**quality band** — `clear` when comfortably above the threshold, `marginal`
when barely meeting it — so a fading route goes yellow before it goes red
(see F4).

**Where the numbers come from.** Each packet's path is a list of short node
identifiers (the first byte or two of each node's public key). Routes match on
those identifiers. Most traffic on our network today uses 1-byte identifiers,
so routes default to matching on that one byte — which catches every packet
regardless of how detailed its path is, at the cost of occasional collisions
(two different nodes sharing a first byte). Several levers keep that
manageable: prefer nodes with a rare first byte, add a midpoint node, require
enough packets, and (optionally) cap how far apart the endpoints may be on the
path.

**How it runs day-to-day:**

- A small background task in the collector re-evaluates every route once a
  minute and stores the result.
- The web UI shows a list of routes with colour-coded health badges and lets
  admins create and edit them.
- Prometheus exposes `meshcore_route_healthy` (0 or 1) and
  `meshcore_route_matched_packets` per route, so external alerts can be wired
  up (e.g. "page me if Ipswich ↔ Norwich has been unhealthy for 10 minutes").
- Each route has a visibility level (community / member / operator / admin),
  so sensitive routes are only shown to the right roles — exactly like channel
  keys today.
- Routes can be configured in the web UI by admins, **or** loaded from a YAML
  file by site operators without logging in (via the existing seed system) —
  handy for provisioning a fresh instance before any users exist.

**Things to know before configuring one.** Routes rely on the hub capturing
raw packets (`FEATURE_PACKETS` on), and on at least one observer hearing
enough of a packet's path to recognise your configured nodes. A route that
reads unhealthy might mean the route is down **or** that no observer is
well-placed to see it — the UI shows which observers contributed so you can
tell the two apart.

## Summary

A new **Route** entity lets operators define an ordered sequence of mesh nodes
(e.g. an Ipswich repeater → a Norwich repeater) and have the hub continuously
test whether packets are traversing that route. Each route carries a time
window (e.g. 24h) and a packet-count threshold (e.g. 3); when enough distinct
packets whose path contains the configured nodes *in order, with gaps allowed*
are observed within the window, the route is **healthy**. A **comfort bar**
(`degraded_threshold`, defaulting to twice the floor) subdivides healthy into
`clear` vs `marginal` so a route trending toward failure is visible before it
breaks.

Health is computed by a background evaluator inside the collector (mirroring
the existing spam re-scoring sweep) and cached in a results table. The API/UI
read those cached results; `/metrics` exposes `meshcore_route_healthy` and
`meshcore_route_matched_packets` gauges (plus a `meshcore_route_quality` band
gauge) for external Prometheus alerting. The feature is instance-wide and
role-scoped per route (community/member/operator/admin), exactly like channels.

## Background & Motivation

The hub already captures every on-air packet into `raw_packets`, one row per
observer reception, with the full ordered hop sequence stored **inside the
`decoded` JSON** (`decoded.path`, trace fallback `decoded.payload.decoded.
pathHashes`; see `collector/handlers/raw_packet.py:106-112` and
`api/routes/packet_groups.py:36-51`). The path hashes are short public-key
prefixes — confirmed from the `meshcoredecoder` library
(`text_message.py:81-93`: "First byte of source node public key") — at a width
of 1, 2, or 3 bytes selected **per packet** by the path-length byte's top two
bits (`packet_decoder.py:155-160, 505-514`).

The data needed to answer "did packets traverse route X recently?" is therefore
already captured, but it lives only in JSON and cannot be matched efficiently.
Two prior plans laid the groundwork:

- **path-hash-bytes-filter** (`20260703-2338`) pulled the *byte width* of each
  packet's path out of JSON into the indexed `raw_packets.path_hash_bytes`
  column, and froze the dual-path extraction logic this plan reuses for the
  hop-table backfill.
- **spam-detection** (`20260622-2243`) introduced the collector-side background
  sweep thread this plan's evaluator copies, and documented the path semantics
  (origin-side hops shared across observers, receiver-side hops diverging per
  observer) that govern correct matching.

A network stats snapshot for the target deployment shows **90% 1-byte, 9%
2-byte, <1% 3-byte** traffic, which drives the default matching width (1-byte
prefix) and the collision-mitigation strategy. Because a node's first pubkey
byte is always present regardless of packet width, a 1-byte prefix match
catches a node at any width — the trade-off is collision (256 buckets), which
the plan mitigates with four independent, composable levers: (1) preferring
unique-prefix nodes, (2) configuring 3-node paths for combinatorial
specificity, (3) the count threshold, and (4) an optional per-route **hop-span
cap** (`max_hop_span`) that rejects matches where the configured nodes'
first bytes co-occur far apart on an unrelated long flood path.

## Goals

- Let operators configure ordered multi-node routes and have the hub report
  whether each is healthy over a configurable window + packet-count threshold.
- Report a **quality band** (clear / marginal / failing / unknown), not just a
  binary alive/dead, so a degrading route is visible before it crosses the
  red floor.
- Make matching **performant** regardless of window size via a denormalized
  hop index populated at ingest, not by scanning/parsing JSON on demand.
- Expose route health to **Prometheus** for external monitoring/alerting, and
  to a dedicated admin UI for configuration and human check-in.
- Reuse existing patterns (channel-style role-scoped CRUD, spam-style
  collector sweep, raw-packet dual-path extraction) so the feature is
  consistent with the codebase.
- Keep the feature **backend-agnostic** (SQLite + Postgres) and **retention-
  safe** (hop rows cascade-delete with their `raw_packets`).

## Non-Goals

- Historical route-health time series (only the latest result is cached in
  `route_results`; retention of trend points is future work).
- In-app alert rule authoring — operators write Prometheus alert expressions
  against the emitted gauges.
- Auto-selecting the match width from the observed wire distribution (the width
  is an explicit per-route knob; auto-selection is future work).
- Trace-route-specific analysis — Routes key off all packet types via
  `raw_packets`/the hop table, not the `trace_paths` table.
- Decoupling hop extraction from raw packet capture (Routes require
  `FEATURE_PACKETS=1`; extraction piggybacks on `store_raw_packet`).

## Requirements

### Functional Requirements

- **F1 — Route configuration.** An operator with the `admin` role can create,
  update, and delete Routes. Each Route has: a unique name, optional
  description, a `visibility` (community/member/operator/admin, default
  `community`), a `match_width` (1/2/3, default 1), `window_hours` (default 24,
  range 1..720), `packet_count_threshold` (default 3, range 1..10000),
  `degraded_threshold` (nullable int, default `null` ⇒ effective comfort bar
  of `2 × packet_count_threshold`; when set explicitly it must be `>
  packet_count_threshold` — the comfort bar at/above which a healthy route
  reads `clear` instead of `marginal`; see F4), `max_hop_span` (nullable int,
  default `null` = unlimited), an `enabled` flag (default true), an ordered
  list of **≥2** path node specs, and an optional observer scope.
- **F2 — Path node specs.** Each path entry selects a known Node (from
  `nodes`);   the system derives `expected_hash = public_key[:2*match_width].upper()` at
  save time. Entries are ordered; entries must be **distinct** (the same node
  twice in one route is invalid). The subsequence match preserves that order
  with gaps allowed (intermediary nodes may sit between configured entries).
  `match_width` is **per-route**: an operator who knows the traffic in a given
  area is uniformly 2- or 3-byte can widen that route's width to drop from 256
  to 65 536 / 16 777 216 buckets (far fewer collisions), at the cost of
  becoming blind to narrower-width traffic — the UI's live "matches in 24h"
  preview confirms coverage before save.
- **F2b — Optional hop-span cap (collision lever).** A Route may set
  `max_hop_span` (nullable, default `null` = unlimited): the maximum number of
  hops allowed between the first and last configured node in a matched
  subsequence (`position(last) − position(first) ≤ max_hop_span`). This is the
  primary locality-based collision reducer — it rejects first-byte
  co-occurrences that are far apart on an unrelated long flood path, without
  the false negatives a total-`path_len` cap would introduce on long packets
  that contain a short genuine sub-path. It needs no new hop-table column
  (positions are already stored).
- **F3 — Observer scope.** Each Route selects **all observers** (default) or a
  specific set of observer nodes. When scoped, only receptions by those
  observers are considered.
- **F4 — Health semantics.** A Route is **healthy** when the number of
  **distinct packets** (`packet_hash`) whose path, in at least one observer's
  reception (within the observer scope, if set), contains the configured
  ordered subsequence within the window and within `max_hop_span` (if set), is
  greater than or equal to `packet_count_threshold`. Each evaluation writes a
  `route_result` row carrying two axes:
  - **`state`** (the alerting axis) — one of:
    - **`healthy`** — `matched_count >= packet_count_threshold`.
    - **`unhealthy`** — in-scope observers received packets in the window but
      `matched_count < threshold` (route may be down).
    - **`no_coverage`** — `matched_count == 0` **and** no in-scope observer
      received any packet with a non-empty path in the window (cannot
      distinguish route-down from no-listener; the operator action is to
      add/widen observers, not assume the route failed). When the scope is
      "all observers", `no_coverage` is only reachable when the whole mesh is
      silent.
  - **`quality`** (the display axis — a traffic-light band derived from
    `state` + `matched_count` + the two thresholds) — one of:
    - **`clear`** — `state == healthy` **and** `matched_count >=
      effective_degraded`: comfortably healthy.
    - **`marginal`** — `state == healthy` **and** `matched_count <
      effective_degraded`: meets the floor but not the comfort bar — the
      route is trending toward failure.
    - **`failing`** — `state == unhealthy`.
    - **`unknown`** — `state == no_coverage`.
    where `effective_degraded = route.degraded_threshold or (2 ×
    route.packet_count_threshold)` — the relative default means every route
    has a band out of the box; an operator only sets `degraded_threshold`
    explicitly to widen or tighten the band.

  The evaluator separates `unhealthy` from `no_coverage` with one extra
  existence check (any in-scope `packet_path_hops` row in the window), then
  derives `quality`. Disabled routes are excluded from evaluation entirely —
  they produce no `route_result`, are omitted from Prometheus output, and
  render a gray **disabled** badge (that badge comes from `route.enabled`,
  not a result state).
- **F5 — Visibility scoping.** The route list is filtered by the requesting
  user's role exactly like channels, using `VISIBILITY_LEVELS` from
  `api/channel_visibility.py`. Reads are role-scoped; writes are admin-only.
- **F6 — UI.** A dedicated `/routes` page (see **UI Design** below) behaves as
  a status board: a health summary strip, cards grouped by visibility with
  failing/no_coverage/marginal sorted first, a five-state quality badge
  (`clear` / `marginal` / `failing` / `no_coverage` / `disabled` — colour map
  in UI Design → The route card), and an inline accordion expand revealing
  the diagnosis, contributing observers, the latest matched path, a config
  recap, and a deep-link to the packets view. Admin CRUD uses a wider modal
  containing a node path-builder and observer picker with prefix-collision
  badges, a live "matches in 24h" preview, and a segmented `match_width`
  control. Mirrors `channels.js` structure throughout.
- **F7 — Prometheus.** `/metrics` emits `meshcore_route_healthy{route}` (1 if
  `quality` ∈ {clear, marginal} else 0), `meshcore_route_quality{route}`
  (0=clear, 1=marginal, 2=failing, 3=unknown — supersedes the originally-
  planned `meshcore_route_state`; gives the `marginal` band its own alertable
  value; alert recipes — "not clear" = `quality >= 1`, "page on failure
  only" = `quality == 2`, "indeterminate" = `quality == 3` — note `unknown`
  =3 carries the highest ordinal but is indeterminate, not more severe than
  `failing`), `meshcore_route_matched_packets{route}` (a **lower bound** when
  `quality == clear`: the evaluator short-circuits at `effective_degraded`,
  so the gauge reports "≥ N" rather than an exact count for comfortably-
  healthy routes; exact for `marginal` / `failing` / `unknown`),
  `meshcore_route_threshold{route}`, and `meshcore_route_degraded_threshold
  {route}` (the effective comfort bar; `2 × threshold` when the route hasn't
  set one) for **all** enabled routes (no visibility filtering on the
  monitoring feed).
- **F8 — Seeding (no-auth provisioning).** Site operators can load Routes
  from a YAML file (`$SEED_HOME/routes.yaml`) without authenticating, via the
  existing `meshcore-hub seed` command (and the compose `seed` profile). The
  file is keyed by route name; each entry holds the route's knobs plus an
  ordered `path` of **≥2** node public_keys and, optionally, an `observers`
  list of public_keys. The importer resolves each public_key to its node,
  derives `expected_hash = public_key[:2*match_width].upper()` itself, and upserts the
  route plus its `route_nodes`/`route_observers` children idempotently by name
  — mirroring how `channels.yaml` is seeded. `visibility` defaults to
  `community` (public); an explicit higher level may be set, since the
  operator has filesystem access and routes carry no secret (unlike channel
  keys). Example shape:
  ```yaml
  Ipswich ↔ Norwich:
    description: A140 corridor route
    visibility: community      # default; member/operator/admin also supported
    match_width: 1              # default: 1 (1/2/3)
    window_hours: 24
    packet_count_threshold: 3
    degraded_threshold: 10      # optional; omit/null = 2× threshold (default)
    max_hop_span: 8             # optional; omit/null = unlimited
    enabled: true               # default: true
    path:                       # ordered, ≥2, by public_key
      - a1b2c3d4e5f6...
      - 9a8b7c6d5e4f...
    observers:                  # optional; omit/empty = all observers
      - 010203040506...
  ```

### Technical Requirements

- **T1 — Denormalized hop index.** A new `packet_path_hops` table stores one
  row per `(reception, hop position)` with `node_hash`, denormalized
  `packet_hash`, `received_at`, and `observer_node_id`, populated at ingest
  inside `store_raw_packet` (reusing the already-computed normalized
  `path_hashes`). The `observer_node_id` denormalization lets observer-scoped
  routes (F3) filter directly on the hop table without a join back to
  `raw_packets` — consistent with the `packet_hash`/`received_at`
  denormalization rationale.
- **T2 — Per-reception matching.** The subsequence self-join keys on
  `raw_packet_id` (one observer's reception), **not** `packet_hash`, so hop
  positions are never compared across observers' divergent path arrays.
  Distinct logical packets are deduped via `COUNT(DISTINCT packet_hash)`.
- **T3 — Prefix matching.** Hops match by a **range scan** (`node_hash >=
  expected_hash AND node_hash < _hex_prefix_end(expected_hash)`), not `LIKE`,
  because Postgres with locale collations cannot use a btree index for `LIKE
  'prefix%'` (SQLite auto-optimizes it, but the range form is sargable on
  both backends unconditionally). `expected_hash` is **uppercased** at
  derivation (`public_key[:2*match_width].upper()`) to match the normalized
  (uppercase) `node_hash` column — the `Node` model lowercases `public_key`
  (`node.py:45-46`) while `_normalize_hash_list` uppercases path hashes
  (`letsmesh_normalizer.py:847`), so without `.upper()` no route would ever
  match. Defaulting to the 1-byte prefix catches a node regardless of the
  originating packet's width.
- **T4 — Background evaluator.** A collector daemon thread, line-for-line
  modeled on the spam re-scoring sweep (`subscriber.py:545-597`), runs at a
  configurable interval (default 60s, `0` disables), performs an immediate
  first run on startup, and upserts one row per route into `route_results`
  using a dialect-specific `on_conflict_do_update` (postgresql
  `pg_insert(...).on_conflict_do_update(...)` / sqlite
  `sqlite_insert(...).on_conflict_do_update(...)`), modeled on the existing
  dialect branch in `common/models/event_observer.py:143-158`. That branch
  currently uses `on_conflict_do_nothing`; no `do_update` variant exists in
  the codebase yet, so the evaluator authors it (standard SQLAlchemy idiom).
- **T5 — Indexing.** Every hop query is time-windowed, so `received_at`
  belongs in the leading index, not as a post-filter. `packet_path_hops`
  carries `INDEX (node_hash, received_at)` — drives the first-prefix + window
  range scan in `fetch_candidate_paths` (a two-range seek: prefix then
  recent) — and `INDEX (raw_packet_id, position)` — serves the per-reception
  ordered-hop fetch, the FK lookup, and the `ON DELETE CASCADE` (leftmost-
  prefix covers equality-on-`raw_packet_id`, so no separate FK index). The
  denormalized `packet_hash`/`received_at`/`observer_node_id` columns back
  the distinct count, the window, and the observer scope without a join back
  to `raw_packets`.
- **T6 — Backend-agnostic.** All DDL via Alembic **batch mode** (SQLite-safe);
  queries use SQLAlchemy Core/ORM with a Python-computed `window_since`
  datetime (never `NOW() - INTERVAL`).
- **T7 — Retention.** `packet_path_hops.raw_packet_id` uses `ON DELETE
  CASCADE`, so the existing cleanup in `cleanup.py` removes hop rows for free
  when aged `raw_packets` are deleted; no cleanup change required.
  `route_results` and `route_nodes`/`route_observers` cascade-delete with
  their parent `routes` row (standard FK cascade).
- **T8 — Feature gating.** New `feature_routes=True` UI flag and
  `route_evaluator_interval_seconds=60` collector knob in `common/config.py`,
  surfaced in `.env.example`. Hop extraction only runs when raw packet
  capture is enabled (`FEATURE_PACKETS=1`).
- **T9 — Seed loader.** A new `_import_routes` helper in `collector/cli.py`,
  wired into `_run_seed_import` so the existing `meshcore-hub seed` command
  (and the compose `seed` profile) loads `routes.yaml` automatically, plus a
  `routes_file` property on the settings resolving to `$SEED_HOME/routes.yaml`.
  Upsert is by `name`; on update the `route_nodes` and `route_observers`
  children are replaced wholesale. Path and observer entries are resolved by
  `public_key` — a missing **path** node is a hard error (the route can't be
  tested against a node the hub has never seen); a missing **observer** is
  skipped with a warning. `expected_hash` is computed by the importer (uppercased to match the
  normalized `node_hash` column), never hand-typed. Returns the `{created, updated, errors}` shape already used by
  the channel and tag seeders. `visibility` defaults to `community`; an
  explicit value is honored, since the operator has filesystem access and
  routes carry no secret (unlike channel keys).

## UI Design

Decisions captured during plan review. The build lives in Phase 7; this
section is the single source of truth for the design.

### Mental model: status board, not catalog
Channels is a catalog (CRUD list of static keys). Routes is a **status board**
— the page's primary job is glancing at health; configuration is secondary
admin work. Every layout choice below follows from that.

### List page (`/routes`)
- **Summary strip** at the top: `● N clear · ● M marginal · ● U failing · ◐ K
  no coverage · ◌ D disabled` (live counts from the embedded `quality`
  values).
- **Cards grouped by visibility** (`VISIBILITY_ORDER`, like channels), but
  within each group **sorted failing / no_coverage / marginal first** so
  broken or at-risk routes surface immediately.
- Header + admin "Add route" button + empty state mirror `channels.js`.

### The route card
- **Quality badge** — five states using daisyUI semantic classes: `clear`
  (green ● `badge-success`), `marginal` (amber ● `badge-warning`), `failing`
  (red ● `badge-error`, was `unhealthy`), `no_coverage` (blue ◐ `badge-info`
  — indeterminate, **not** a warning), and `disabled` (gray ◌ `badge-neutral`,
  from `route.enabled`). Recolouring `no_coverage` from amber to blue removes
  the original plan's clash between "watch this" (marginal) and "can't tell"
  (no_coverage).
- **Path chips** — the configured nodes as `[Ipswich RP] → … → [Norwich RP]`,
  conveying "ordered, gaps allowed".
- **Numbers line** — `matched / threshold [→ degraded] · window · quality ·
  evaluated Xm ago`; the `[→ degraded]` target is the result's snapshot
  `effective_degraded` (`2 × threshold` when the route hasn't set one).
- Admin edit/delete buttons (channels pattern).
- **Click → inline accordion expand** (not a modal, not a separate page).

### Card expand contents (lazy `GET /api/v1/routes/{id}`)
1. **Diagnosis line** — turns the blue/amber/red split (`no_coverage` /
   `marginal` / `failing`) into a sentence.
2. **Contributing observers with counts** — an empty list *is* the
   `no_coverage` signal.
3. **Latest match (~3) with the observed path** — configured nodes marked ✓,
   intermediates shown, so the operator can verify a real match vs a
   collision. Served by a new `recent_matches(route, limit)` engine helper.
4. **Config recap** (read-only) — width, span, window, observer scope,
   thresholds.
5. **"View packets" deep-link** — to the existing packet-groups page filtered
   to matched hashes + window (reuses built UI; no new packet browser).

### Create/edit modal (wider: `modal-box-lg`)
- `name`, `description`, `visibility` (select), `enabled` (checkbox) — as
  channels.
- **`match_width`** — **segmented control** `[ 1 byte | 2 bytes | 3 bytes ]`
  with a dynamic hint ("Matches all traffic · ~256 buckets" / "2-byte+ only ·
  ~65K" / "3-byte only · ~16M"). Chosen over a `<select>` because toggling it
  live-updates the collision badges and preview — the explore-by-tapping
  affordance is the point.
- **Path builder** (new shared component): search → `/api/v1/nodes`, selected
  nodes as ordered draggable chips (↑↓ for a11y), enforce ≥2 + distinct, each
  chip showing a **collision badge** ("unique" green / "N share prefix `a1`"
  amber). Warn on mixed-width intent (a node never observed at the chosen
  width) and suggest adding a 3rd node when collisions appear.
- **Observers** multi-picker (same component; empty = all observers).
- `window_hours`, `packet_count_threshold`, `degraded_threshold` (empty = 2×
  threshold default; placeholder hints "leave blank for 2× threshold"),
  `max_hop_span` (empty = unlimited) numeric fields.
- **Live "matches in 24h" preview** — debounced `POST /api/v1/routes/preview`
  as the path / width / observers / thresholds change; shows `~N matches in
  24h → quality: clear/marginal/failing` plus the per-node collision counts
  used by the chips.

### Data split (list vs detail vs preview)
- `GET /api/v1/routes` embeds the **lightweight** result per card: `state`,
  `quality`, `matched_count`, `threshold`, `effective_degraded`,
  `evaluated_at`. Keeps the list
  payload small.
- `GET /api/v1/routes/{id}` returns the **full detail**: the lightweight
  result plus contributing observers (with counts) and the latest ~3 matched
  paths. Fetched lazily on first expand and cached in page state.
- `POST /api/v1/routes/preview` (unsaved config → `{matched_count, quality,
  contributing_observers, collisions}`) powers the live preview + chip badges.

### i18n
- Feature strings under a new top-level **`routes.*`** block; nav label under
  `entities.routes` (value "Routes"). The `routes.*` token is collision-free.
  See Phase 7.

## Implementation Plan

### Phase 1: Data model + migration + backfill
- Add models in `src/meshcore_hub/common/models/`: `packet_path_hop.py`,
  `route.py` (with `RouteVisibility` mirroring the channel enum, plus config
  columns `match_width`, nullable `max_hop_span`, and nullable
  `degraded_threshold`), `route_node.py`, `route_observer.py`,
  `route_result.py`. Export all from `models/__init__.py`. `route_result`
  carries: `route_id` (FK `routes.id`, `ondelete=CASCADE`, unique — one row
  per route), `state` (enum `healthy` / `unhealthy` / `no_coverage` — the
  alerting axis), `quality` (enum `clear` / `marginal` / `failing` /
  `unknown` — the display axis, derived from `state` + `matched_count` + the
  route's thresholds at eval time and denormalized here so the list endpoint
  need not recompute), `matched_count` (int), `threshold` (int, snapshot at
  eval time for stable reporting), `effective_degraded` (int, snapshot of
  `effective_degraded_threshold(route)` at eval time — the comfort bar used
  for this result, so the `[→ degraded]` display and the `quality` band stay
  self-consistent if the operator later changes thresholds), `evaluated_at`
  (datetime). Per-observer breakdown and recent matched paths are **not**
  stored — they are computed
  on demand by `GET /api/v1/routes/{id}` (see UI Design → Data split).
- One Alembic revision (batch mode) creating the five tables + indexes.
- Backfill `packet_path_hops` from `raw_packets.decoded`, keyset-paginated
  (batch 1000), reusing the **frozen dual-path extraction** copied from
  migration `20260703_2250` (`_normalize_hash_list` + `decoded.path` →
  `payload.decoded.pathHashes` fallback), which yields a list of `node_hash`
  strings ordered origin-to-observer. The backfill enumerates this list
  (index = `position`) and emits one `PacketPathHop` row per
  `(position, node_hash)` with `packet_hash`/`received_at`/`observer_node_id`
  denormalized from the source `raw_packet` row.

### Phase 2: Ingest hook + tests
- In `collector/handlers/raw_packet.py::store_raw_packet`, the normalized
  `path_hashes` list is already computed at lines 106-111 (line 112 derives
  `path_hash_bytes` from it — the citable "available" point is 106-111). The
  hop bulk-insert goes inside the `with db.session_scope()` block (line 118)
  **after** the `RawPacket` is added. The current inline
  `session.add(RawPacket(...))` at lines 138-155 must be refactored to
  `raw_packet = RawPacket(...); session.add(raw_packet); session.flush()` so
  `raw_packet.id` is materialized, then bulk-insert one `PacketPathHop` per
  `(position, node_hash)` from `path_hashes`, denormalizing
  `packet_hash`/`received_at`/`observer_node_id` from the same values
  (`observer_node_id` is already in scope as `observer_node.id`). Zero extra decode; gated
  by the existing raw-capture flag (the caller,
  `Subscriber._perhaps_capture_raw_packet`, already checks
  `self._raw_packet_capture_enabled`).
- Extend `tests/test_collector/test_handlers/test_raw_packet.py` to assert
  hops are inserted with correct positions/hashes and skipped when the path is
  absent.

### Phase 3: Matching engine (pure, DB-tested)
- New `collector/routes.py` using a **fetch-and-check** strategy (not an N-way
  self-join). Rationale: the default 1-byte match width produces broad first-
  prefix candidate sets where a self-join's cost scales with (candidates ×
  depth); fetch-and-check scales with (candidates) only, on per-reception
  paths that are ≤8 hops. Core functions:
  - `fetch_candidate_paths(db, first_prefix, since, observer_ids=None,
    limit=None)`: one statement — `SELECT raw_packet_id, position, node_hash,
    packet_hash FROM packet_path_hops WHERE raw_packet_id IN (SELECT
    raw_packet_id FROM packet_path_hops WHERE node_hash >= :prefix AND
    node_hash < :prefix_end AND received_at >= :since [AND observer_node_id
    IN (:obs)]) ORDER BY raw_packet_id, position` — returns grouped ordered
    hop arrays. The prefix range (`>= :prefix AND < :prefix_end`) is
    sargable on both backends; the observer filter is a direct column
    condition (no join) thanks to T1's denormalization. A subquery (not a
    client `IN`-list) avoids the `SQLITE_MAX_VARIABLE_NUMBER` ceiling.
  - `is_subsequence(path, expected, max_hop_span=None)`: pure two-pointer
    prefix match (`node_hash.startswith(expected_hash)`), gaps allowed,
    `position(last) − position(first) <= max_hop_span` when set. ~8 lines,
    unit-trivial.
  - `DEGRADED_DEFAULT_MULTIPLIER = 2` (module constant) — the relative
    default used when a route leaves `degraded_threshold` null.
  - `effective_degraded_threshold(route)`: returns `route.degraded_threshold
    or (route.packet_count_threshold * DEGRADED_DEFAULT_MULTIPLIER)`.
    Centralises the relative default for the evaluator, preview, metrics, and
    UI.
  - `derive_quality(state, matched_count, threshold, effective_degraded)`:
    pure mapping implementing F4's `quality` axis (clear / marginal / failing
    / unknown). Unit-trivial.
  - `evaluate_route(db, route, since)`: fetch candidates for the route's
    first node prefix, run `is_subsequence` per reception, count **distinct**
    `packet_hash`, and **short-circuit as soon as the count reaches
    `effective_degraded_threshold(route)`** (the comfort bar — always ≥ the
    floor, so clearing it classifies `clear` vs `marginal` in one pass; a
    `healthy` early-exit). Below `packet_count_threshold`, run **one existence
    check** (any in-scope `packet_path_hops` row in the window) to choose
    `unhealthy` vs `no_coverage` per F4. Finally derive `quality` via
    `derive_quality(..., effective_degraded)`. Returns `(state, quality,
    matched_count)` (`matched_count` is `>= effective_degraded` when
    short-circuited).
  - `evaluate_all_routes`: iterates enabled routes, calls `evaluate_route`.
  - `recent_matches(db, route, limit=3)`: same fetch + subsequence check,
    returns the latest `limit` matching paths (positions/hashes) for the card
    expand's ✓-marked path view.
  - `preview_route(db, config, since)`: accepts an **unsaved** config (path
    nodes by `node_id`, width, observers, span, `packet_count_threshold`,
    nullable `degraded_threshold`) and returns `{matched_count, quality,
    contributing_observers, collisions}`. Resolves `effective_degraded` from
    the config (null ⇒ `2 × threshold`) before deriving `quality`. Applies the
    **candidate cap**: if `fetch_candidate_paths` exceeds the cap (default
    5000), stops and returns `{matched_count: null, quality: null, truncated:
    true, candidate_count}` so no preview call does unbounded work (see Phase
    4).
  - Helpers: `derive_expected_hash` (uppercases the public-key prefix to
    match the normalized `node_hash` column), `_hex_prefix_end(prefix)`
    (exclusive upper bound for the range scan — increments the last hex
    char, ~2 lines), `detect_observed_width`, `prefix_collision_counts`
    (`GROUP BY upper(public_key[:2*match_width])`).
- `tests/test_collector/test_routes.py`: subsequence (gaps allowed, order
  enforced, span cap), **per-reception isolation** (no cross-observer
  splice), multi-observer dedup to distinct packets, observer-scope filter,
  **threshold short-circuit** (at the floor when no band, at
  `effective_degraded` otherwise), **`no_coverage` vs `unhealthy`
  separation**, **quality-band derivation** (`clear` / `marginal` / `failing`
  / `unknown` incl. the null ⇒ `2 × threshold` relative default), **
  `recent_matches` ordering/limit**, and **preview truncation**.

### Phase 4: CRUD API + schemas
- New `api/routes/routes.py` + `common/schemas/routes.py` mirroring
  `api/routes/channels.py` (which uses `@cached` from `api/cache.py`,
  `RequireRead`/`RequireAdmin` from `api/auth.py`, and `DbSession` from
  `api/dependencies.py`): `GET /api/v1/routes` (RequireRead, role-filtered,
  `@cached`, embeds current `route_result`); `POST /api/v1/routes`
  (collection-level, like channels) and `GET/PUT/DELETE /api/v1/routes/{id}`
  (RequireAdmin writes; ≥2 **distinct** `route_nodes` validated in Pydantic,
  and `degraded_threshold` either null or `> packet_count_threshold` (null ⇒
  `2 × threshold` default); `expected_hash` auto-derived (uppercased) from
  `node_id` when omitted, and re-derived for all path nodes when `match_width`
  changes; observer set managed inline). Note: channels has no single-resource
  `GET`; routes adds one to serve the embedded result. Register router in
  `api/routes/__init__.py` (import `router as routes_router` +
  `api_router.include_router(routes_router, prefix="/routes", tags=["Routes"])`);
  `api/app.py:183` mounts the aggregate `api_router`.
- `POST /api/v1/routes/preview` (RequireRead — any authenticated user may
  preview; it computes no saved state): accepts an unsaved route config (path
  `node_id`s, `match_width`, observers, `max_hop_span`, `window_hours`,
  `packet_count_threshold`, `degraded_threshold`) and returns
  `{matched_count, quality, contributing_observers, collisions}` by
  delegating to `collector.routes.preview_route`. Not cached (inputs are
  arbitrary). `preview_route` applies a **candidate cap** (default 5000): on
  overflow it returns `{matched_count: null, quality: null, truncated: true,
  candidate_count}` and the UI shows "~many — narrow your path to preview",
  bounding every call to one scan. The client debounces (~400ms) and cancels
  in-flight via `AbortController` (the `signal` pattern) so typing never
  stacks calls.
- `GET /api/v1/routes/{id}` (RequireRead, role-scoped) returns the **full
  detail** per UI Design → Data split: the lightweight result plus
  contributing observers (with counts) and the latest ~3 matched paths (via
  `recent_matches`). The list `GET /api/v1/routes` embeds only the
  lightweight result (`state`, `quality`, `matched_count`, `threshold`,
  `effective_degraded`, `evaluated_at`).
- `tests/test_api/test_routes.py`: CRUD, role-scoping, visibility filter,
  min-2-nodes rejection, `degraded_threshold` validation (null or `>`
  threshold), result embedding, **the preview endpoint**, and the **`GET
  /{id}` detail shape** (observers + recent paths).

### Phase 5: Evaluator thread
- New `collector/route_evaluator.py` wrapping `collector/routes.py`.
  `evaluate_all_routes` iterates only enabled routes. In
  `collector/subscriber.py`, add `_start_route_evaluator_scheduler` /
  `_stop_route_evaluator_scheduler` (copy of the spam sweep), started in
  `start()` (after the spam scheduler at ~line 669) and stopped in `stop()`
  (after the spam stop at ~line 710); thread attr near line 114. Immediate
  first run on startup, 60s loop, dialect upsert, per-iteration error
  logging.
- `tests/test_collector/test_route_evaluator.py`: upsert idempotency,
  immediate-first-run, disabled when interval is 0.

### Phase 6: Prometheus
- In `api/metrics.py::collect_metrics`, read `route_results ⋈ routes` and
  emit `meshcore_route_healthy` (1 if `quality` ∈ {clear, marginal} else 0),
  `meshcore_route_quality` (0=clear, 1=marginal, 2=failing, 3=unknown —
  supersedes the originally-planned `meshcore_route_state`, giving the
  `marginal` band its own alertable value), `meshcore_route_matched_packets`
  (a lower bound when `quality == clear` — the evaluator short-circuits at
  `effective_degraded`; exact otherwise), `meshcore_route_threshold`, and
  `meshcore_route_degraded_threshold` (the effective comfort bar; `2 ×
  threshold` when the route hasn't set one), labelled by route name. Verify
  in `tests/test_api/test_metrics.py`.

### Phase 7: Web UI + i18n
- Build per the **UI Design** section above. New
  `src/meshcore_hub/web/static/js/spa/pages/routes.js` (mirror `channels.js`):
  summary strip + visibility-grouped cards sorted
  failing/no_coverage/marginal first; **five-state quality badge** (see UI
  Design → The route card for the daisyUI colour map); **inline accordion
  expand** (toggle `expandedId` in page state, lazy
  `GET /api/v1/routes/{id}` on first expand, cached) showing diagnosis /
  contributing observers / latest matched path (✓ markers via
  `recent_matches`) / config recap / "View packets" deep-link; wider
  (`modal-box-lg`) add/edit modal with the shared node path-builder +
  observer picker, segmented `match_width` control, a `degraded_threshold`
  numeric field (empty ⇒ `2 × threshold` default), and a debounced
  `POST /api/v1/routes/preview` driving the live "matches in 24h → quality"
  readout and collision badges.
- Register route in `src/meshcore_hub/web/static/js/spa/app.js`: add
  `routes: () => import('./pages/routes.js')` to the `pages` lazy-load map
  (~line 27); add a `if (features.routes !== false) { router.addRoute('/routes',
  pageHandler(pages.routes)); }` block (~line 92, next to the channels guard);
  add a `composePageTitle('entities.routes')` title entry (~line 178). Add a
  nav card in `src/meshcore_hub/web/static/js/spa/pages/home.js` (~line 99)
  among the existing `renderNavCard` blocks in `renderHeroSection`.
- Add `entities.routes` (value "Routes") plus a new **`routes.*`** top-level
  block (incl. the four quality-label strings: `quality_clear`,
  `quality_marginal`, `quality_failing`, `quality_unknown`) to
  `src/meshcore_hub/web/static/locales/en.json` and `nl.json`.

### Phase 8: Config + seed loader + docs
- Add `feature_routes=True` and `route_evaluator_interval_seconds=60` to
  `common/config.py` (as `feature_*` `Field(...)` declarations in the
  ~569-602 block), and a `"routes": self.feature_routes` entry in the
  `features` property's returned dict (dict body at ~lines 622-634); add a
  `routes_file` property mirroring the existing `channels_file` property at
  `config.py:367-372` (resolves to `Path(self.effective_seed_home) /
  "routes.yaml"`); update `.env.example`.
- New `_import_routes` in `collector/cli.py`, wired into `_run_seed_import`
  so `meshcore-hub seed` and the compose `seed` profile pick up `routes.yaml`
  automatically. Idempotent upsert by `name`; resolves path/observer nodes by
  `public_key`; derives `expected_hash` (uppercased to match the
  normalized `node_hash` column); replaces `route_nodes`/
  `route_observers` on update; honors seeded `visibility` and
  `degraded_threshold` (null ⇒ `2 × threshold` default); returns
  `{created, updated, errors}`.
- Add `example/seed/routes.yaml` documenting the format (mirrors the example
  in F8), alongside the existing `example/seed/channels.yaml`.
- Document in `SCHEMAS.md`, `README.md`, and cross-reference from
  `docs/seeding.md` and `docs/letsmesh.md`. Optional `meshcore-hub routes
  list|delete` CLI (create/edit stays in the UI or seed).

### Phase 9: Consolidate packet-detail path read onto the hop table
- Opportunistic consolidation riding on the populated `packet_path_hops`
  table. In `api/routes/packet_groups.py::get_packet_group`, replace the
  per-reception `_extract_path_hashes(packet.decoded)` call (~line 292) with
  a batched `SELECT raw_packet_id, position, node_hash FROM packet_path_hops
  WHERE raw_packet_id IN (:ids) ORDER BY raw_packet_id, position` (one query
  for the whole reception set), grouped into the same
  `receptions[i].path_hashes` shape. **Near-zero payload change** —
  `PacketReceptionInfo.path_hashes` stays `Optional[list[str]]` and the only
  renderer (`packet-group-detail.js`) is untouched, but hash values shift
  from **raw to normalized (uppercased)** because the hop table stores
  `_normalize_hash_list` output (`.upper()`) while `_extract_path_hashes`
  returns raw `decoded.path` (possibly lowercase). Cosmetically minor (hex
  case) but technically a payload change; the parity test should assert
  `upper()` equality, not byte-identity.
- Delete `_extract_path_hashes` (lines 36-51) — it becomes a dead third copy
  of the dual-path extraction (the live normalizer in `letsmesh_normalizer.py`
  and the frozen copy in migration `20260703_2250` remain the canonical
  sources). Note the list endpoint and dashboard charts already bypass JSON
  (they use the indexed `path_hash_bytes` column), so only the detail route
  changes.
- Depends on the Phase 1 backfill being complete (every existing `raw_packet`
  has its hops populated). For a row that somehow lacks hops, fall back to an
  empty list (the renderer already handles a missing/empty path).
- `tests/test_api/test_packet_groups.py`: assert the detail endpoint returns
  `path_hashes` per reception after the swap, uppercased to match the
  normalized hop-table values (golden-path parity up to case), including multi-observer divergence and packets with no path.

## Enabled Future Capabilities

The `packet_path_hops` index is built for Route matching, but it unlocks
packet-exploration features that are **impossible today** (each would require
a full-table JSON scan). This plan does **not** build them; they are noted
here as follow-on work, each likely its own plan:

- **Path-node filtering on `/packets`** — "show packets that passed through
  node X" via an indexed `(node_hash, received_at)` lookup. Today's path-node
  popover in `packet-group-detail.js` is read-only (resolves a hash to known
  nodes); this would turn it into an interactive filter
  (`/packets?path_node=…`) plus a new `list_packet_groups` query param.
- **Per-node relay statistics** — most active repeaters, common hop positions
  (`GROUP BY node_hash`).
- **List-page hop preview** — the `/packets` list currently shows no path
  content (per-row extraction in a GROUP BY is too costly); a cheap indexed
  lookup could show first-3-hops previews per group.

Phase 9 captures only the low-risk consolidation (the packet-detail endpoint
reading from the hop table). The filtering/stats features above are deferred.

## Open Questions

- **Collision tolerance.** At 1-byte matching (256 buckets) on a busy mesh,
  some first-byte prefixes will collide. The plan mitigates via unique-prefix
  node selection, 3-node paths, and the count threshold, but the acceptable
  false-healthy rate for the operator's alerting needs confirming once live
  data is available.
- **Cap on configured nodes per route (UX, not perf).** With the fetch-and-
  check strategy there is no N-way self-join — configured-node depth only
  affects the trivial `is_subsequence` two-pointer pass, so even 10+ nodes is
  cheap. The proposed cap of ~8 is therefore a **UX** limit (path-builder
  chip clutter), enforced as a soft Pydantic/UI cap, not a performance guard.
- **Observer coverage guidance.** Whether the UI should proactively recommend
  adding observers when a route reads unhealthy with zero contributing
  observers (route-dead vs no-coverage disambiguation).

## References

- `docs/plans/20260703-2338-path-hash-bytes-filter/plan.md` — adds
  `raw_packets.path_hash_bytes`; source of the frozen dual-path extraction
  logic reused verbatim for the `packet_path_hops` backfill.
- `docs/plans/20260622-2243-spam-detection/plan.md` — collector background
  sweep pattern, path semantics (origin-side shared, receiver-side divergent),
  and the `(prefix, received_at)` indexed-count technique this plan adapts.
- `docs/plans/20260612-2014-raw-packets-feature/plan.md` — `raw_packets` table
  and `FEATURE_PACKETS` gating that Routes piggybacks on.
- `docs/plans/20260519-2051-channel-model-db-decrypt/plan.md` — `Channel`
  model + `ChannelVisibility` role-scoping pattern copied for `routes`.
- Key sources: `collector/handlers/raw_packet.py`, `collector/subscriber.py`
  (spam sweep at lines 545-597), `api/routes/channels.py`,
  `api/metrics.py`, `meshcoredecoder` (`decoder/packet_decoder.py:155-160,
  505-514`; `decoder/payload_decoders/text_message.py:81-93`).
- Recent direction (git `main`): dashboard packet-breakdown charts
  (`0300609`), path-hash-bytes filter (`c029eae`), JSON tree / packet path
  flow (`f845830`) — all building on the raw-packet foundation this plan
  extends.

## Review

**Status**: Approved

**Reviewed**: 2026-07-12 (second pass; first pass 2026-07-06)

### Resolutions

**Conflicts** — None. Cross-checked against all 45 plans under `docs/plans/`,
all 7 source files the plan modifies, and `git log --oneline -20` on `main`.
No existing `packet_path_hops` table, `Route` model, or `/api/v1/routes`
endpoint exists. The plan builds on (not duplicates) spam-detection
(`20260622-2243`), path-hash-bytes-filter (`20260703-2338`),
raw-packets-feature (`20260612-2014`), and channel-model-db-decrypt
(`20260519-2051`); their cited commits (`c029eae`, `0300609`, `f845830`) all
landed on `main`.

**First-pass resolutions (content):**
- **F1 — Defaults**: `window_hours` defaults to 24 (range 1..720),
  `packet_count_threshold` to 3 (range 1..10000); `degraded_threshold`
  defaults null ⇒ effective `2 × packet_count_threshold`; `enabled` defaults
  `true`.
- **F2 — Duplicate path nodes**: entries must be distinct; validated in Pydantic.
- **F4 — Disabled routes**: excluded from evaluation, produce no
  `route_result`, omitted from Prometheus.
- **T7 — Cascade completeness**: `route_results`, `route_nodes`,
  `route_observers` all cascade-delete with their parent `routes` row.
- **Phase 1 — Backfill enumeration**: frozen extraction yields an ordered list;
  backfill enumerates index = `position`.

**Second-pass resolutions (factual corrections verified against source):**
- **T4 — Upsert citation was wrong on two counts.** The cited path
  `collector/handlers/event_observer.py` does not exist (the file is
  `common/models/event_observer.py`), and the cited method
  `on_conflict_do_update` does not exist anywhere in the repo — the branch at
  `:143-158` uses `on_conflict_do_nothing`. Corrected to point at the real
  dialect branch and clarify the evaluator authors the `do_update` variant.
- **Phase 2 — Insertion point was imprecise.** Line 138 is the start of
  `session.add(RawPacket(...))` (spans 138-155), not the hop-insert point.
  Hops need `raw_packet.id`, which requires assigning the inline `RawPacket`
  to a variable and calling `session.flush()` before the bulk-insert.
  `path_hashes` is computed at 106-111 (112 is the derived byte width).
  Corrected in place.
- **Phase 7 / Phase 8 — Web paths were missing the `src/meshcore_hub/`
  prefix.** There is no top-level `web/` directory; the real root is
  `src/meshcore_hub/web/`. All `web/...` citations corrected.
- **F5 — `VISIBILITY_LEVELS` location.** It lives in
  `api/channel_visibility.py:13`, not `models/channel.py`; import path added.
- **Phase 4 — Endpoint shape clarified.** Channels has no single-resource
  `GET` and its POST is collection-level (`""`); routes' POST mirrors that,
  and routes adds a `GET /{id}` to serve the embedded result. `@cached`/
  `RequireRead`/`RequireAdmin`/`DbSession` import paths confirmed.
- **Phase 8 — Config locations tightened.** Feature-flag `Field(...)` decls
  live at ~569-602; the `features` property's dict body is at ~622-634 (not
  ~611); the `routes_file` property mirrors `channels_file` at
  `config.py:367-372`.
- **Phase 5 — Line numbers confirmed.** Spam scheduler calls occupy 667/708
  exactly; ~669/~710 is the correct after-insertion point. Thread attr at 114
  confirmed.

**Decisions:**
- **i18n namespace** — `routes.*` for the feature's page strings; nav label
  under `entities.routes` (value "Routes"). The `routes.*` token is
  collision-free (unlike the original `links.*` footer block that first
  motivated a `mesh_` prefix; with the feature renamed to Routes that prefix
  is no longer needed).

### Naming amendment (2026-07-12)

Renamed the feature from **"Link" / "Mesh Link"** to **"Routes"** to avoid the
web-link ambiguity (the original plan's primary open question). The display
label is **"Routes"** (not "Mesh Routes") — the `Mesh` qualifier was dropped
because the feature lives in the nav alongside Nodes/Channels/Messages, where
the mesh context is already implicit. Naming map (single source of truth):

| Concern | Value |
|---|---|
| User-facing label (nav card, page title) | **Routes** |
| Entity / model class | `Route` |
| Tables | `routes`, `route_nodes`, `route_observers`, `route_results` |
| Visibility enum | `RouteVisibility` |
| API | `/api/v1/routes`, `/api/v1/routes/{id}`, `/api/v1/routes/preview` |
| Web page / module | `/routes`, `spa/pages/routes.js` |
| Feature flag / config | `feature_routes`, `route_evaluator_interval_seconds`, `routes_file` |
| Seed file / importer | `routes.yaml`, `_import_routes` |
| Prometheus metrics | `meshcore_route_healthy`, `meshcore_route_quality`, `meshcore_route_matched_packets`, `meshcore_route_threshold`, `meshcore_route_degraded_threshold` (label `{route}`) |
| i18n | `entities.routes` = "Routes"; feature strings under `routes.*` |
| Engine functions | `evaluate_route`, `evaluate_all_routes`, `preview_route`, `effective_degraded_threshold`, `derive_quality`, `recent_matches(db, route, …)` |
| Unchanged (not route-feature-specific) | `packet_path_hops` table, `raw_packets`, `trace_paths`, `max_hop_span`, `node_hash`, `path_hash_bytes` |

**Considered — `route_type` semantic overlap (accepted).** The word "Route"
is already user-visible via the per-packet **`route_type`** delivery
classification (`flood` / `direct`, shown as a "Route Type" column and filter
on the Packets/Advertisements pages, e.g. `advertisements.js:299`,
`packets.col_route_type`), and the `trace_paths` traceroute feature. The
overlap was accepted because (a) the scopes differ — a nav-level monitored-
route feature vs a per-packet delivery attribute; (b) i18n namespaces already
separate them (`routes.*` vs `packets.col_route_type` /
`advertisements.route_type_*`); and (c) context disambiguates — "Routes" is a
nav-level monitoring feature, while "Route Type" is a per-packet column/
filter on the Packets and Advertisements pages. A literal `routes` token is
collision-free across models, API routes, SPA pages, feature flags, i18n
blocks, metrics, and config (audited 2026-07-12 against `main`).

### Quality band amendment (2026-07-12)

Added a **route quality band** on top of the existing 3-state `state`
(alerting) axis, so a route shows amber (`marginal`) before it crosses the
red floor — the "is it alive or dead" answer is unchanged; the band adds
"how comfortably alive".

- **`Route.degraded_threshold`** (nullable int, default null) — the comfort
  bar. `matched_count` in `[packet_count_threshold, effective_degraded)` ⇒
  `marginal`; `≥ effective_degraded` ⇒ `clear`. **Null ⇒ relative default
  `effective_degraded = 2 × packet_count_threshold`** (module constant
  `DEGRADED_DEFAULT_MULTIPLIER = 2` in `collector/routes.py`), so every route
  gets a marginal/clear split out of the box; an operator only sets
  `degraded_threshold` explicitly to widen or tighten the band. Validated `>
  packet_count_threshold` in Pydantic when explicitly set (F1, Phase 4).
- **`RouteResult.quality`** (enum `clear` / `marginal` / `failing` /
  `unknown`) — the display axis, derived at eval time from `state` +
  `matched_count` + the effective comfort bar, denormalized into
  `route_results` so the list endpoint doesn't recompute. `state` (healthy /
  unhealthy / no_coverage) is kept as the stable alerting contract (F4).
- **Evaluator** (Phase 3) — new helpers `effective_degraded_threshold(route)`
  and `derive_quality(state, matched_count, threshold, effective_degraded)`;
  the short-circuit bar is `effective_degraded_threshold(route)`; below the
  floor the existing existence check splits `failing` vs `unknown`.
- **Badge** (Phase 7 / UI Design) — five daisyUI colours: `clear`
  `badge-success`, `marginal` `badge-warning`, `failing` `badge-error`,
  `no_coverage` `badge-info`, `disabled` `badge-neutral`. **Recoloured
  `no_coverage` from amber to blue** — it is indeterminate, not a warning,
  and this removes the original plan's clash with the `marginal`/warning
  band.
- **Metrics** (Phase 6) — replaced the planned `meshcore_route_state` ordinal
  with the richer `meshcore_route_quality` (0/1/2/3; alert recipes — "not
  clear" = `>= 1`, "page on failure" = `== 2`, "indeterminate" = `== 3`;
  `unknown`=3 carries the highest ordinal but is indeterminate, not more
  severe than `failing`); `meshcore_route_matched_packets` is a lower bound
  when `quality == clear` (short-circuit). `meshcore_route_degraded_threshold`
  emits the effective comfort bar (`2 × threshold` when unset).
  `meshcore_route_healthy` stays as the simple boolean (1 when `quality` ∈
  {clear, marginal}).

Normative detail lives in F4 / F7 / UI Design → The route card.

### Second-pass review (2026-07-12)

Re-verified all cited line numbers and functions against `main` (commit
`d60e2e8`). All citations are accurate. No new conflicts with the 45 sibling
plans or `git log --oneline -20`. One critical bug found and fixed; two
design decisions resolved.

**Critical fix — case mismatch (would have broken all matching):**
- `Node.public_key` is stored **lowercase** (`node.py:45-46`:
  `self.public_key = self.public_key.lower()`), while `_normalize_hash_list`
  **uppercases** path hashes (`letsmesh_normalizer.py:847`,
  migration `20260703_2250:52`: `token = item.strip().upper()`). The plan
  derived `expected_hash = public_key[:2*match_width]` without `.upper()`,
  so `LIKE 'a1%'` would never match `'A1B2'` (case-sensitive on both
  backends) — **every route would permanently read unhealthy**.
  **Fix**: `.upper()` added to every `expected_hash` derivation (F2, F8,
  T3, T9, Phase 3 `derive_expected_hash`, Phase 4 CRUD, Phase 8 seed).

**Design decision 1 — Postgres LIKE sargability (resolved: range query):**
- `node_hash LIKE 'prefix%'` defeats the btree index on Postgres with locale
  collations (the planner won't recognize LIKE-prefix as sargable, causing a
  seq scan). SQLite auto-optimizes it, but the range form is sargable on
  both backends unconditionally.
  **Resolution**: replaced `LIKE` with a range scan (`node_hash >= :prefix
  AND node_hash < :prefix_end`) throughout (T3, Phase 3
  `fetch_candidate_paths`). Added `_hex_prefix_end(prefix)` helper (~2 lines:
  increment last hex char) to Phase 3 helpers.

**Design decision 2 — observer denormalization (resolved: add column):**
- `packet_path_hops` denormalized `packet_hash` and `received_at` but not
  `observer_node_id`, forcing observer-scoped routes (F3) to join
  `raw_packets`. This broke T5's stated "no join back to `raw_packets`" goal.
  **Resolution**: added `observer_node_id` to the hop table (T1, T5, Phase 1
  backfill, Phase 2 ingest, Phase 3 `fetch_candidate_paths`). Storage cost
  ~36 bytes/row; ingest cost negligible (value already in scope at line 140).

**Factual corrections:**
- **Router registration** — plan said "Register router in `api/app.py`" but
  routers are registered in `api/routes/__init__.py` (import +
  `include_router`); `app.py:183` only mounts the aggregate `api_router`.
  Corrected in Phase 4.
- **Phase 9 payload change** — plan claimed "zero client-visible payload
  change" but the hop table stores normalized (uppercased) hashes while
  `_extract_path_hashes` returns raw (possibly lowercase) values. Corrected
  to "near-zero" with a note to assert `upper()` equality in the parity test.
- **`prefix_collision_counts`** — was hardcoded to 1-byte (`[:2]`,
  lowercase); parameterized to `[:2*match_width]` and uppercased for
  consistency with the `node_hash` column.

### Remaining Action Items

- ~~**Naming confirmation**~~ — **RESOLVED 2026-07-12**: feature is **Routes**;
  table `routes`, namespace `routes` (see Naming amendment above). No longer
  blocks Phase 1.
- ~~**Quality band default**~~ — **RESOLVED 2026-07-12**: `degraded_threshold`
  ships a **relative default** — null ⇒ `2 × packet_count_threshold` (module
  constant `DEGRADED_DEFAULT_MULTIPLIER = 2`), so every route has a marginal/
  clear split out of the box.
- **Cap on configured nodes** — confirm ~8 is comfortable; this is a **UX**
  limit (path-builder chip clutter), not a performance guard — fetch-and-
  check eliminated the N-way self-join, so depth only affects the trivial
  `is_subsequence` pass.
- **Collision tolerance** — validate the acceptable false-healthy rate with
  live data once the hop table is populated.
- **Observer coverage guidance** — UI decision during Phase 7 (recommend
  adding observers when a route reads unhealthy with zero contributing
  observers).

Only the last three items remain; none block starting Phase 1. The
second-pass review (2026-07-12) added no new action items — all findings
were resolved directly in the plan.
