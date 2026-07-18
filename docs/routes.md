# Route Health Monitoring

The **Routes** page (`/routes`) lets operators define monitored multi-hop mesh routes and track each one's health over time. A background evaluator on the collector matches captured packet paths against each route's configured node sequence within a rolling time window and rolls the result up into a traffic-light status card, with a per-day history strip and a list of recent matching transmissions.

For the environment-variable reference, see [configuration.md → Feature Flags](configuration.md#feature-flags) (`FEATURE_ROUTES`) and [→ Collector](configuration.md#collector) (`ROUTE_EVALUATOR_INTERVAL_SECONDS`). To define routes from YAML, see [seeding.md → Routes](seeding.md#routes).

> **Prerequisite:** route matching reads from the `packet_path_hops` table, which is populated by **Raw Packet Capture**. Keep `FEATURE_PACKETS=true` (the default) so packet paths continue to be captured; with capture off, route cards stay at `unknown` once the existing window of hops ages out.

## How health is evaluated

A route is an ordered list of two or more nodes (the configured path). For each captured packet reception, the evaluator walks the reception's path-hash sequence and checks whether the route's nodes appear **in order, as a subsequence** (intermediate hops are allowed). When `reversible` is set (the default), the reverse-ordered path is also accepted, so a packet travelling `B → ... → A` counts toward an `A → B` route.

Matches are deduplicated by their **underlying event identity**, not per on-air transmission. The collector denormalizes the structured event's `event_hash` (the same key used to dedup advertisements, messages, telemetry, and traces at the structured-event layer) onto each captured raw packet at ingest time. The evaluator prefers `event_hash` when set, so retransmissions or floods of the same underlying advert/message count once toward `packet_count_threshold` instead of once per on-air copy. Packets captured before this column existed (and any unclassified wire packets) have `event_hash IS NULL` and fall back to the wire `packet_hash`, preserving the previous behaviour until they age out of the configured `window_hours`.

Each route carries these knobs:

| Field | Default | Description |
| --- | --- | --- |
| `match_width` | `1` | Path-hash prefix width in bytes (1/2/3). Higher widths disambiguate nodes that share a short public-key prefix. |
| `window_hours` | `24` | Rolling lookback window for the live status card. |
| `packet_count_threshold` | `3` | Distinct matching packets at/above which the route is `healthy`. "Distinct" is per underlying event, not per transmission — see [How health is evaluated](#how-health-is-evaluated) above. |
| `clear_threshold` | _(2× threshold)_ | Comfort bar for the `clear`/`marginal` split. Omit/null to use twice the threshold. |
| `max_hop_span` | _(unlimited)_ | Caps the position gap between the first and last matched node, to reject matches that wander too far. |
| `reversible` | `true` | Also match the path in reverse direction. |
| `enabled` | `true` | When `false`, the route is skipped by the evaluator and reports `unknown`/`no_coverage`. |

The result is reported on two axes:

- **State** — `healthy` (≥ threshold distinct matches in the window), `unhealthy` (some packets were observed but too few matched the configured path), or `no_coverage` (no in-scope packets at all in the window).
- **Quality** — `clear` (≥ effective clear bar), `marginal` (healthy but below the comfort bar), `failing` (unhealthy), or `unknown` (no coverage / route disabled).

The state/quality split lets the dashboard render a single traffic-light band while keeping the underlying reason visible: a `marginal` route is technically up but losing margin, and a `failing` route has traffic in the window but the configured path isn't completing.

### Observer scoping

By default every observer's receptions contribute to every route. A route may instead scope itself to an explicit **observer allow-list** (`route_observers`); when set, only receptions from those observer nodes are matched. Use this to ignore noisy or off-path observers that would otherwise drown out the signal. Observer nodes that don't yet exist in the database are skipped with a warning rather than failing the seed.

### Background evaluator

The collector runs a background thread that re-evaluates every enabled route on a fixed cadence and upserts the result into `route_results` (one row per route, holding the latest `state`, `quality`, `matched_count`, and the threshold snapshots used). The cadence is controlled by `ROUTE_EVALUATOR_INTERVAL_SECONDS` (default `60`); set it to `0` to disable the evaluator, in which case route cards remain at `unknown` until it is re-enabled. The per-route history strip and the `/api/v1/routes/{id}/history` endpoint evaluate on demand over the raw `packet_path_hops` table and are not dependent on the background evaluator.

## Visibility

Routes carry the same role-based visibility levels as channels — `community`, `member`, `operator`, `admin`. A user only sees routes whose visibility is at or below their role's maximum level. Seeded routes default to `community` (visible to everyone); set a higher level to restrict a route to operators/admins only. Visibility is enforced on both the list and detail endpoints, so a hidden route's existence is not leaked.

## Defining routes

Routes are keyed by their `from`/`to` endpoint labels and upserted by that pair. There are two ways to create them:

- **Seed YAML** — add a `routes.yaml` to your `SEED_HOME` and run the seed process. See [seeding.md → Routes](seeding.md#routes) for the format and rules (path nodes must already exist in the database; the `(from, to)` pair must be unique).
- **API** — `POST /api/v1/routes` (admin only) creates a route, with a `/preview` endpoint that dry-runs matching against an unsaved configuration so you can tune thresholds before committing. See `SCHEMAS.md` for the request/response shapes.

The `/routes` page renders the live status card, the per-day history strip, recent matching transmissions (with observer attribution), and — for admins — inline edit/delete controls.
