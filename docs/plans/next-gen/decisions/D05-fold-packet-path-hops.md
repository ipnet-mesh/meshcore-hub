# D05: Fold `packet_path_hops` Into `raw_receptions.path_hashes` (Research Spike)

- **Status:** Locked (spike — decision lands in Phase 2)
- **Iteration:** 2

## Context

`packet_path_hops` is the worst write-amplification offender (W3): one row per (reception × hop), so a 6-hop packet seen by 4 observers = 24 rows, each denormalizing 4 columns from `raw_packets`. It already required a Postgres covering-index rebuild (HEAD migration `a59611449e2a`) and a `window_hours` clamp as a perf band-aid. The route matcher reads it as a joined scan. The §6.3.3 proposed target is to fold the path hashes into a `path_hashes text[]` array column on `raw_receptions` with a GIN index — one insert per reception instead of 1+N — but the GIN-containment candidate query's selectivity under high hash commonality is the unknown.

## Decision

**Phase 2 research spike.** Prototype the folded schema (`raw_receptions.path_hashes text[]` + GIN index, no hops table) and benchmark the route matcher against the separate-hypertable alternative using the harness in §18.3. **Default assumption: fold.** Keep folded if the D17 gate is met:

- At the **High** dataset shape (1M receptions, 200 routes, 40% hash commonality),
- `sweep_ms(F) ≤ 1.5 × sweep_ms(S)`, AND
- `p95_route_ms(F) ≤ 500ms`.

**Fallback if the gate fails:** keep a separate `packet_path_hops` hypertable (still better than today because TimescaleDB-partitioned) **but stop denormalizing** `packet_hash`, `received_at`, `observer_node_id` (reachable via the FK to `raw_receptions`). The `raw_receptions.path_hashes` column stays either way (it backs the packet-group detail view). Budget half a day; record results in `docs/plans/<date>-d5-fold-benchmark/`. Run **before** the §16 schema is frozen.

## Consequences

**Positive (if folded):** Eliminates W3's write amplification at the source — 24 rows → 1. The matcher loads one array column instead of joining N rows. One fewer table in the schema, one fewer retention policy, one fewer compression policy.

**Negative:** GIN indexes are larger and slower to update than btree; high hash commonality (40% of packets containing a given route hash) inflates candidate sets and shifts cost from candidate-fetch to the Python subsequence pass. If the gate fails we carry the hops table forward, slightly complicating the matcher.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Fold into `path_hashes text[]` + GIN** (preferred, default) | Resolves W3 at the source; benchmark validates the read side. |
| Separate hypertable, denormalized (today's shape) | Rejected — preserves W3's write amplification. |
| Separate hypertable, **not** denormalized (fallback) | Acceptable — partitioned + FK-reachable, no duplicate columns; chosen only if D17 gate fails. |
| JSONB column instead of `text[]` | Rejected — GIN-over-array is cheaper and the path hashes are flat strings. |
