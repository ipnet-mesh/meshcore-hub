# D14: 5-Day Parallel-Stack Validation Window

- **Status:** Locked
- **Iteration:** 4

## Context

The rewrite is **greenfield infrastructure** ([migration.md](../components/migration.md)) — fresh Postgres+TimescaleDB, NATS, new codebase, empty database. No historical data is migrated; instead, the new stack ingests live MQTT *alongside* the old for a validation window, so that by cutover the new stack holds enough fresh data that users see a continuous view. The question: how long is that window? Too short and the diff harness hasn't covered a representative traffic pattern (bursty days, weekend variance); too long and the cutover is delayed unnecessarily.

## Decision

**5-day parallel-stack validation window.** Both stacks ingest the same live MQTT broker/topics simultaneously. A diff harness compares per-hour event counts by `event_hash` between the old API and the new API; any divergence blocks cutover. Cutover proceeds when the diff reports **0 divergence for 3 consecutive days** within the 5-day window. Cut over DNS / reverse-proxy / MQTT subscription exclusivity to the new stack; decommission the old after a grace period.

## Consequences

**Positive:** 5 days covers a workweek + weekend variance, capturing bursty traffic patterns and any weekly cyclicality in advert/message volume. The 3-consecutive-clean-days rule gives confidence without requiring the full window to be clean (one bad hour doesn't reset the clock entirely). No historical backfill means no MD5→SHA-256 coexistence, no parallel schemas, no validation gate on historical rows.

**Negative:** Running two full stacks for 5 days doubles infra cost briefly. A divergence forces investigation before cutover, potentially extending the window. The old stack must keep running cleanly during validation (if it breaks, the diff harness loses its reference).

## Alternatives considered

| Option | Verdict |
|---|---|
| **5 days** (chosen) | Covers weekly variance; 3-clean-days gate balances confidence vs speed. |
| 3 days | Rejected — faster, but risks missing weekend traffic patterns; thinner statistical confidence. |
| 7 days | Rejected — more conservative but slower cutover; 5 days + 3-clean-days gate is sufficient. |
| No parallel window (cold cutover) | Rejected — users see an empty dashboard on day one; no parity evidence. |
