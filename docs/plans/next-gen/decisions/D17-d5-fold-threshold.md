# D17: D5 Fold Threshold (1.5× / 500ms / 40% Commonality)

- **Status:** Locked
- **Iteration:** 4

## Context

D5 defers the fold-vs-separate decision to a Phase 2 benchmark because the GIN-containment candidate query's behaviour under high hash commonality is the unknown. To make the spike produce a decision rather than a debate, §18.3.4 / §13-D17 needed a quantitative gate: what read-cost regression is acceptable in exchange for the write-cost win?

## Decision

**Keep folded (F) if, at the High dataset shape** (1M `raw_receptions` in window, 200 routes, 80 distinct node hashes, avg path length 10 hops, 8 observers/packet, **40% hash commonality**):

- `sweep_ms(F) ≤ 1.5 × sweep_ms(S)`, **AND**
- `p95_route_ms(F) ≤ 500ms`.

If either fails, fall back to the separate hypertable (still better than today because TimescaleDB-partitioned and no longer denormalized). The `raw_receptions.path_hashes` column stays either way (backs the packet-group detail view); the hops table is additive only in the fallback.

**Rationale:** the folded schema eliminates the hops table's write amplification (a 6-hop packet × 4 observers = 24 rows today → 1 row folded). That write-cost win is worth up to a **1.5× read-cost tradeoff** because reads happen on a 300s evaluator cadence while writes happen on every packet. The **500ms p95 guard** prevents any single route becoming a latency outlier. The **40% commonality** test level is the documented "breaker" — high commonality inflates GIN candidate sets, shifting cost from candidate-fetch to the Python subsequence pass.

## Consequences

**Positive:** The gate is measurable and unambiguous — the spike produces a binary decision, not a judgment call. Either outcome is acceptable: folded wins on writes, separate-partitioned wins on reads, both are strictly better than today.

**Negative:** The 1.5× factor is a judgment itself — too tight and we lose a worthwhile fold; too loose and we accept a real read regression. The 40% commonality level assumes worst-case traffic; real traffic may be lower (in which case the gate is conservative) or shift over time.

## Alternatives considered

| Threshold | Verdict |
|---|---|
| **1.5× + 500ms p95 at 40%** (chosen) | Balances write-win value against read-cost guard at the documented breaker commonality. |
| Tighter (1.2× / 300ms) | Rejected — too tight; risks losing the fold when the write win is real. |
| Looser (2.0× / no p95 guard) | Rejected — accepts a meaningful read regression and latency outliers. |
| Single-metric only (sweep_ms, no p95) | Rejected — average hides outlier routes; p95 guard is necessary. |
