# Mesh Link Monitoring (Route Health)

## How it works (overview)

> This section is a plain-language explainer for sharing and discussion. The
> detailed PRD follows below.

MeshCore packets travel across the network by hopping through repeater nodes.
Every packet the hub captures already records the sequence of nodes it passed
through (its **path**). This feature turns that recorded path data into a way
to **monitor whether a route you care about is actually working**.

**The idea, with an example.** Suppose there are known repeaters near Ipswich
and Norwich, and you want to know when traffic stops getting between them.
You'd create a **Link** named "Ipswich ↔ Norwich", pick those two repeater
nodes in order, set a window of "last 24 hours" and a threshold of "3
packets". The hub then continuously asks: *in the last 24 hours, did at least
3 distinct packets travel along a path that passed through the Ipswich
repeater and then the Norwich repeater?* If yes, the link is **healthy**; if
not, it's **unhealthy** and something along that route may be down.

The two nodes don't need to be directly adjacent — a packet counts if it went
Ipswich → …some other repeaters… → Norwich, **in that order**. You can also add
a midpoint node (say, a Cambridge repeater) to make the route more specific
and reduce accidental matches.

**Health, in one line:** a link is healthy when **≥ N distinct packets**, each
seen within the time window, each travelled a path that contains your
configured nodes in the right order (gaps allowed).

**Where the numbers come from.** Each packet's path is a list of short node
identifiers (the first byte or two of each node's public key). Links match on
those identifiers. Most traffic on our network today uses 1-byte identifiers,
so links default to matching on that one byte — which catches every packet
regardless of how detailed its path is, at the cost of occasional collisions
(two different nodes sharing a first byte). Several levers keep that
manageable: prefer nodes with a rare first byte, add a midpoint node, require
enough packets, and (optionally) cap how far apart the endpoints may be on the
path.

**How it runs day-to-day:**

- A small background task in the collector re-evaluates every link once a
  minute and stores the result.
- The web UI shows a list of links with green/red health badges and lets admins
  create and edit them.
- Prometheus exposes `meshcore_link_healthy` (0 or 1) and
  `meshcore_link_matched_packets` per link, so external alerts can be wired up
  (e.g. "page me if Ipswich ↔ Norwich has been unhealthy for 10 minutes").
- Each link has a visibility level (community / member / operator / admin), so
  sensitive links are only shown to the right roles — exactly like channel keys
  today.

**Things to know before configuring one.** Links rely on the hub capturing raw
packets (`FEATURE_PACKETS` on), and on at least one observer hearing enough of
a packet's path to recognise your configured nodes. A link that reads
unhealthy might mean the route is down **or** that no observer is well-placed
to see it — the UI shows which observers contributed so you can tell the two
apart.

## Summary

A new **Link** entity lets operators define an ordered sequence of mesh nodes
(a route, e.g. an Ipswich repeater → a Norwich repeater) and have the hub
continuously test whether packets are traversing that route. Each link carries
a time window (e.g. 24h) and a packet-count threshold (e.g. 3); when enough
distinct packets whose path contains the configured nodes *in order, with gaps
allowed* are observed within the window, the link is **healthy**.

Health is computed by a background evaluator inside the collector (mirroring
the existing spam re-scoring sweep) and cached in a results table. The API/UI
read those cached results; `/metrics` exposes `meshcore_link_healthy` and
`meshcore_link_matched_packets` gauges for external Prometheus alerting. The
feature is instance-wide and role-scoped per link (community/member/operator/
admin), exactly like channels.

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
specificity, (3) the count threshold, and (4) an optional per-link **hop-span
cap** (`max_hop_span`) that rejects matches where the configured nodes'
first bytes co-occur far apart on an unrelated long flood path.

## Goals

- Let operators configure ordered multi-node routes ("Links") and have the hub
  report whether each is healthy over a configurable window + packet-count
  threshold.
- Make matching **performant** regardless of window size via a denormalized
  hop index populated at ingest, not by scanning/parsing JSON on demand.
- Expose link health to **Prometheus** for external monitoring/alerting, and to
  a dedicated admin UI for configuration and human check-in.
- Reuse existing patterns (channel-style role-scoped CRUD, spam-style
  collector sweep, raw-packet dual-path extraction) so the feature is
  consistent with the codebase.
- Keep the feature **backend-agnostic** (SQLite + Postgres) and **retention-
  safe** (hop rows cascade-delete with their `raw_packets`).

## Non-Goals

- Historical link-health time series (only the latest result is cached in
  `link_results`; retention of trend points is future work).
- In-app alert rule authoring — operators write Prometheus alert expressions
  against the emitted gauges.
- Auto-selecting the match width from the observed wire distribution (the width
  is an explicit per-link knob; auto-selection is future work).
- Trace-route-specific analysis — Links keys off all packet types via
  `raw_packets`/the hop table, not the `trace_paths` table.
- Decoupling hop extraction from raw packet capture (Links requires
  `FEATURE_PACKETS=1`; extraction piggybacks on `store_raw_packet`).

## Requirements

### Functional Requirements

- **F1 — Link configuration.** An operator with the `admin` role can create,
  update, and delete Links. Each Link has: a unique name, optional description,
  a `visibility` (community/member/operator/admin), a `match_width` (1/2/3,
  default 1), `window_hours`, `packet_count_threshold`, `max_hop_span`
  (nullable int, default `null` = unlimited), an `enabled` flag, an ordered
  list of **≥2** path node specs, and an optional observer scope.
- **F2 — Path node specs.** Each path entry selects a known Node (from
  `nodes`); the system derives `expected_hash = public_key[:2*match_width]` at
  save time. Entries are ordered; the subsequence match preserves that order
  with gaps allowed (intermediary nodes may sit between configured entries).
  `match_width` is **per-link**: an operator who knows the traffic in a given
  area is uniformly 2- or 3-byte can widen that link's width to drop from 256
  to 65 536 / 16 777 216 buckets (far fewer collisions), at the cost of
  becoming blind to narrower-width traffic — the UI's live "matches in 24h"
  preview confirms coverage before save.
- **F2b — Optional hop-span cap (collision lever).** A Link may set
  `max_hop_span` (nullable, default `null` = unlimited): the maximum number of
  hops allowed between the first and last configured node in a matched
  subsequence (`position(last) − position(first) ≤ max_hop_span`). This is the
  primary locality-based collision reducer — it rejects first-byte
  co-occurrences that are far apart on an unrelated long flood path, without
  the false negatives a total-`path_len` cap would introduce on long packets
  that contain a short genuine sub-path. It needs no new hop-table column
  (positions are already stored).
- **F3 — Observer scope.** Each Link selects **all observers** (default) or a
  specific set of observer nodes. When scoped, only receptions by those
  observers are considered.
- **F4 — Health semantics.** A Link is **healthy** when the number of
  **distinct packets** (`packet_hash`) whose path, in at least one observer's
  reception (within the observer scope, if set), contains the configured
  ordered subsequence within the window and within `max_hop_span` (if set), is
  greater than or equal to `packet_count_threshold`.
- **F5 — Visibility scoping.** The link list is filtered by the requesting
  user's role exactly like channels (`VISIBILITY_LEVELS`). Reads are role-
  scoped; writes are admin-only.
- **F6 — UI.** A dedicated `/links` page lists links with health badges,
  grouped by visibility, with admin CRUD modals (mirror of `channels.js`). The
  node picker shows prefix-collision badges and a live "matches in 24h"
  preview; it warns on mixed-width intent and recommends 3-node paths.
- **F7 — Prometheus.** `/metrics` emits `meshcore_link_healthy{link}`,
  `meshcore_link_matched_packets{link}`, and `meshcore_link_threshold{link}`
  for **all** enabled links (no visibility filtering on the monitoring feed).

### Technical Requirements

- **T1 — Denormalized hop index.** A new `packet_path_hops` table stores one
  row per `(reception, hop position)` with `node_hash`, denormalized
  `packet_hash` and `received_at`, populated at ingest inside
  `store_raw_packet` (reusing the already-computed normalized `path_hashes`).
- **T2 — Per-reception matching.** The subsequence self-join keys on
  `raw_packet_id` (one observer's reception), **not** `packet_hash`, so hop
  positions are never compared across observers' divergent path arrays.
  Distinct logical packets are deduped via `COUNT(DISTINCT packet_hash)`.
- **T3 — Prefix matching.** Hops match by `node_hash LIKE expected_hash || '%'`
  (range-sargable), defaulting to the 1-byte prefix so a node is matched
  regardless of the originating packet's width.
- **T4 — Background evaluator.** A collector daemon thread, line-for-line
  modeled on the spam re-scoring sweep (`subscriber.py:545-597`), runs at a
  configurable interval (default 60s, `0` disables), performs an immediate
  first run on startup, and upserts one row per link into `link_results` using
  the existing dialect-specific `on_conflict_do_update` pattern
  (`event_observer.py:143-158`).
- **T5 — Indexing.** `packet_path_hops` carries `INDEX (node_hash,
  raw_packet_id, position)` (drives the chain), `INDEX (raw_packet_id)` (FK +
  per-reception lookup + cascade), and the denormalized `packet_hash` for the
  dedup count.
- **T6 — Backend-agnostic.** All DDL via Alembic **batch mode** (SQLite-safe);
  queries use SQLAlchemy Core/ORM with a Python-computed `window_since`
  datetime (never `NOW() - INTERVAL`).
- **T7 — Retention.** `packet_path_hops.raw_packet_id` uses `ON DELETE
  CASCADE`, so the existing cleanup in `cleanup.py` removes hop rows for free
  when aged `raw_packets` are deleted; no cleanup change required.
- **T8 — Feature gating.** New `feature_links=True` UI flag and
  `link_evaluator_interval_seconds=60` collector knob in `common/config.py`,
  surfaced in `.env.example`. Hop extraction only runs when raw packet capture
  is enabled (`FEATURE_PACKETS=1`).

## Implementation Plan

### Phase 1: Data model + migration + backfill
- Add models in `src/meshcore_hub/common/models/`: `packet_path_hop.py`,
  `link.py` (with `LinkVisibility` mirroring the channel enum, plus config
  columns `match_width` and nullable `max_hop_span`), `link_node.py`,
  `link_observer.py`, `link_result.py`. Export all from `models/__init__.py`.
- One Alembic revision (batch mode) creating the five tables + indexes.
- Backfill `packet_path_hops` from `raw_packets.decoded`, keyset-paginated
  (batch 1000), reusing the **frozen dual-path extraction** copied from
  migration `20260703_2250` (`_normalize_hash_list` + `decoded.path` →
  `payload.decoded.pathHashes` fallback), emitting one row per
  `(position, node_hash)` with `packet_hash`/`received_at` denormalized.

### Phase 2: Ingest hook + tests
- In `collector/handlers/raw_packet.py:138` (after `path_hashes` is computed at
  lines 106-112), bulk-insert `PacketPathHop` rows from the normalized list.
  Zero extra decode; gated by existing raw-capture flag.
- Extend `tests/test_collector/test_handlers/test_raw_packet.py` to assert
  hops are inserted with correct positions/hashes and skipped when the path is
  absent.

### Phase 3: Matching engine (pure, DB-tested)
- New `collector/links.py`: `build_subsequence_query(link, since)` (dynamic
  chain of indexed self-joins on `raw_packet_id` with strictly-increasing
  `position`, each filtering `node_hash LIKE expected_hash || '%'`, optional
  observer filter, and optional `max_hop_span` predicate
  `(ph_last.position − ph0.position) <= max_hop_span` when set), `evaluate_link`,
  `evaluate_all_links`, plus helpers `derive_expected_hash`,
  `detect_observed_width`, and `prefix_collision_counts`
  (`GROUP BY lower(public_key[:2])`) for UI badges.
- `tests/test_collector/test_links.py`: subsequence (gaps allowed, order
  enforced), **per-reception isolation** (no cross-observer splice),
  multi-observer dedup to distinct packets, observer-scope filter, **hop-span
  cap rejects wide co-occurrences and keeps close ones on long packets**,
  threshold boundary, prefix-match across widths.

### Phase 4: CRUD API + schemas
- New `api/routes/links.py` + `common/schemas/links.py` mirroring
  `api/routes/channels.py`: `GET /api/v1/links` (RequireRead, role-filtered,
  `@cached`, embeds current `link_result`); `GET/POST/PUT/DELETE
  /api/v1/links/{id}` (RequireAdmin writes; ≥2 `link_nodes` validated in
  Pydantic; `expected_hash` auto-derived from `node_id` when omitted; observer
  set managed inline). Register router in `api/app.py`.
- `tests/test_api/test_links.py`: CRUD, role-scoping, visibility filter,
  min-2-nodes rejection, result embedding.

### Phase 5: Evaluator thread
- New `collector/link_evaluator.py` wrapping `collector/links.py`. In
  `collector/subscriber.py`, add `_start_link_evaluator_scheduler` /
  `_stop_link_evaluator_scheduler` (copy of the spam sweep), started in
  `start()` (~line 667) and stopped in `stop()` (~line 708); thread attr near
  line 114. Immediate first run, 60s loop, dialect upsert, per-iteration error
  logging.
- `tests/test_collector/test_link_evaluator.py`: upsert idempotency,
  immediate-first-run, disabled when interval is 0.

### Phase 6: Prometheus
- In `api/metrics.py::collect_metrics`, read `link_results ⋈ links` and emit
  the three gauges labelled by link name. Verify in
  `tests/test_api/test_metrics.py`.

### Phase 7: Web UI + i18n
- New `web/static/js/spa/pages/links.js` (mirror `channels.js`): list grouped
  by visibility with health badges; admin CRUD modal with the node multi-picker
  (collision badges + observed width + live preview), observer multi-picker,
  and an optional "within N hops" field (`max_hop_span`, empty = unlimited).
- Register route in `web/static/js/spa/app.js` (~lines 27, 90), add a nav card
  in `home.js` (~line 99) and page titles; add `entities.links` + `links.*`
  strings to `web/static/locales/en.json` and `nl.json`.

### Phase 8: Config + docs + optional CLI
- Add `feature_links=True` and `link_evaluator_interval_seconds=60` to
  `common/config.py` (and the `features` dict ~line 611); update `.env.example`.
- Document in `SCHEMAS.md`, `README.md`, and cross-reference from
  `docs/letsmesh.md`. Optional `meshcore-hub links list|create|delete` CLI
  mirroring the channel/seed commands.

## Open Questions

- **Collision tolerance.** At 1-byte matching (256 buckets) on a busy mesh,
  some first-byte prefixes will collide. The plan mitigates via unique-prefix
  node selection, 3-node paths, and the count threshold, but the acceptable
  false-healthy rate for the operator's alerting needs confirming once live
  data is available.
- **Cap on configured nodes per link (join depth).** Subsequence join depth
  equals the number of configured nodes per link (distinct from `max_hop_span`,
  which caps the gap between endpoints). The plan proposes capping `link_nodes`
  at ~8; confirm this is comfortable for the realistic longest route.
- **Observer coverage guidance.** Whether the UI should proactively recommend
  adding observers when a link reads unhealthy with zero contributing
  observers (route-dead vs no-coverage disambiguation).
- **Naming confirmation.** "Link" was chosen over "Route"/"Mesh Link"; table
  `links`. Confirm before migration is authored, since renaming later is
  costly.

## References

- `docs/plans/20260703-2338-path-hash-bytes-filter/plan.md` — adds
  `raw_packets.path_hash_bytes`; source of the frozen dual-path extraction
  logic reused verbatim for the `packet_path_hops` backfill.
- `docs/plans/20260622-2243-spam-detection/plan.md` — collector background
  sweep pattern, path semantics (origin-side shared, receiver-side divergent),
  and the `(prefix, received_at)` indexed-count technique this plan adapts.
- `docs/plans/20260612-2014-raw-packets-feature/plan.md` — `raw_packets` table
  and `FEATURE_PACKETS` gating that Links piggybacks on.
- `docs/plans/20260519-2051-channel-model-db-decrypt/plan.md` — `Channel`
  model + `ChannelVisibility` role-scoping pattern copied for `links`.
- Key sources: `collector/handlers/raw_packet.py`, `collector/subscriber.py`
  (spam sweep at lines 545-597), `api/routes/channels.py`,
  `api/metrics.py`, `meshcoredecoder` (`decoder/packet_decoder.py:155-160,
  505-514`; `decoder/payload_decoders/text_message.py:81-93`).
- Recent direction (git `main`): dashboard packet-breakdown charts
  (`0300609`), path-hash-bytes filter (`c029eae`), JSON tree / packet path
  flow (`f845830`) — all building on the raw-packet foundation this plan
  extends.
