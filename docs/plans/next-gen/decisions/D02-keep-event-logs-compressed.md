# D02: Keep `event_logs` as a Compressed Hypertable

- **Status:** Locked
- **Iteration:** 2

## Context

Today `events_log` is the catch-all audit sink — every event that doesn't match a structured handler lands here as an unbounded JSON payload (W7), roughly doubling per-event storage. It is high-volume (one row per non-structured event across all topics) but carries real diagnostic value: it is where unknown payload types, internal MQTT topics, and operational oddities are inspectable after the fact. The question (this record) was whether to keep it at all in the rewrite, or drop it on the assumption that structured handlers + `raw_receptions` coverage made it redundant.

## Decision

**Keep** `events_log`, **renamed to `event_logs`** for plural-table naming consistency (data-model.md §1.6; cf. code-warts DM9). It becomes a TimescaleDB hypertable (1-day chunks, partitioned by `received_at`) with aggressive compression after 24h and a 30-day default retention policy. Schema: `(received_at, id, observer_node_id, event_type, payload jsonb, instance_id)`. Compression + chunk-drop retention mean it costs a fraction of its current footprint while staying queryable for diagnostic detail views.

## Consequences

**Positive:** Diagnostic coverage for unknown payload types and internal feeds is preserved without an additional store — the fallback handler path stays intact. Compression (10–20×) + chunk-drop retention resolve W7's "unbounded doubling" complaint at the storage layer. One consistent naming convention (`event_logs`) removes the singular/plural confusion.

**Negative:** Some storage cost remains (vs dropping it entirely). Compression `segmentby` choice matters — `observer_node_id` is the right one but a mis-choice degrades scan cost. A retention shorter than 30d may be wanted under disk pressure (configurable via the Tier-2 tuning settings — see D11).

## Alternatives considered

| Option | Verdict |
|---|---|
| **Compressed hypertable** (chosen) | Preserves diagnostic value; storage cost amortised by TimescaleDB compression. |
| Drop entirely | Rejected — loses the catch-all for unknown payload types and internal MQTT feeds; operators lose post-hoc debuggability. |
| Separate append-only audit store (Loki / ELK) | Rejected — adds a new datastore and query language for a workload Postgres + compression handles fine. |
| Keep as plain OLTP table | Rejected — re-introduces W7's unbounded growth; no compression or chunk-drop retention. |
