# D01: TimescaleDB for High-Volume History Store

- **Status:** Locked
- **Iteration:** 2

## Context

A single Postgres/SQLite database holds everything today, and the high-volume append-only tables are exactly the ones that hurt: W2 (`raw_packets` write amplification — 16 cols, 9 indexes, one row per observer reception), W3 (`packet_path_hops` write-amplified per reception × hop), W7 (`events_log` as an unbounded audit sink roughly doubling per-event storage), and W6 (route-health subsystem as a hand-rolled materialized-view layer of 7 tables). The 2-day raw retention ceiling and the HEAD migration that rebuilt a Postgres covering index are symptoms of forcing OLTP-shaped storage onto timeseries-shaped workloads. Dashboard aggregations (A7) fan out one COUNT per visible channel per request because nothing is pre-bucketed.

The §13-D1 decision had to land before the §16 schema could be drafted — every later phase depends on which store holds the high-volume streams.

## Decision

**PostgreSQL 17 + TimescaleDB** (community edition, Apache-2.0). The high-volume append-only streams (`raw_receptions`, `event_observers`, `telemetry`, `event_logs`) become TimescaleDB hypertables partitioned by `received_at` (1-day chunks), with columnar compression policies after 24h and retention policies (default 30d, up from 2d). The five dashboard time-bucketing workloads become **continuous aggregates** (`cagg_daily_message_counts`, `cagg_daily_advert_counts`, `cagg_daily_packet_counts`, `cagg_packet_breakdown_by_type`, `cagg_node_count_history`) refreshed on a 5-minute policy — replacing the fan-out COUNTs.

Route-health derived tables stay worker-maintained (subsequence logic is not a pure time-bucket aggregate — see §6.3.4 and D5).

## Consequences

**Positive:** Same process, same connection pool, same transaction semantics as the OLTP store — no two-phase anything, one backup, one monitoring target, one set of credentials. Hypertables dissolve W2/W3/W7 by making scan-heavy queries cheap under compression. CAGGs eliminate A7. Retention stretches from 2 days to 30+ at similar disk cost. Apache-2.0 community edition covers every feature used.

**Negative:** TimescaleDB extension is a Postgres dependency (an additional install + version-coupling). Compression is asymmetric (decompress-on-update is costly) — acceptable here because the history tier is append-mostly. Operators must learn chunk/compression-policy ops.

## Alternatives considered

| Option | Verdict |
|---|---|
| **TimescaleDB** (chosen) | One process with CAGGs; least operational surface for the dashboard win. |
| ClickHouse | Rejected — separate process, separate connection pool, no shared transactions with OLTP, heavier ops for this scale. |
| Plain Postgres declarative partitioning | Rejected — no continuous aggregates, no built-in compression policy, no chunk-drop retention; would re-derive all of it by hand. |
| Dedicated timeseries DB (InfluxDB / Prometheus) | Rejected — splits the data model across two query languages; CAGGs already cover the timeseries-shaped reads. |
