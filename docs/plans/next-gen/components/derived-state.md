# Derived State & Background Work

> **Related decisions:** D15, D16
>
> **Note:** Code examples are illustrative pseudocode showing design patterns (shapes, flows, contracts).
> The implementation uses the TypeScript stack (D22): Drizzle ORM, node-postgres. SQL functions (PL/pgSQL) are language-agnostic.

## Overview

One `DerivedStateWorker` process (or a sidecar mode of the collector) owns all periodic work. The wins:

- One set of metrics, one shutdown path, one retry policy.
- **Dashboard aggregations are precomputed** instead of fan-out COUNTs (A7). Two of them — daily **packet** counts and the **packet breakdown by type** — source from the `raw_receptions` hypertable and are true TimescaleDB **continuous aggregates**. The other three — daily **message** counts, **advert** counts, and **node-count history** — source from OLTP/entity tables (`messages`, `advertisements`, `nodes`) that are *not* hypertables, so a CAGG cannot be built over them; the `dashboard-rollups` job maintains them as plain rollup tables (data-model.md §3.6a). Either way the API reads precomputed buckets, not live COUNTs.
- **Route health stays as 3 derived tables** (`route_results`, `route_result_history`, `route_recent_matches`) maintained by the worker — *not* CAGGs. Route matching is subsequence logic over `raw_receptions.path_hashes`, which cannot be expressed as a fixed time-bucket aggregate. The wins here are (a) the matcher reads one array column instead of a write-amplified hops table (D5), and (b) one worker maintains all three tables + the preview endpoint instead of 2 background cadences + inline maintenance.
- Spam rescoring can become a **DB function** invoked on insert (for the online score) plus a periodic sweep (for the symmetric hindsight score), instead of a Python loop issuing per-row queries.
- Retention becomes **chunked** (drop-old-chunks for hypertables via TimescaleDB retention policies) — no multi-second exclusive locks (W10).

## Job manifest

One process — `DerivedStateWorker` — owns every periodic job. Replaces the six daemon threads. The channel-refresh thread is **gone entirely** (replaced by the ChannelKeyCache NATS event mechanism). The webhook processor thread is replaced by a separate **`WebhookWorker`** NATS subscriber (D19 — see [ingest.md §12](ingest.md#12-webhook-delivery-d19)). What remains is four periodic jobs + two health checks.

| Job | Cadence | Replaces (today) | What it does | Idempotency |
|---|---|---|---|---|
| `route-evaluator` | 300s | `route-evaluator` thread (300s) | Refresh `route_results` + `route_recent_matches` from `raw_receptions.path_hashes`; recomputes each enabled route's state/quality + top-3 matches. | Per-route: re-evaluation is a pure overwrite of the 1:1 result row + capped match rows. |
| `route-history` | 3600s | `route-history-backfill` thread (3600s) | Refresh completed UTC-day buckets in `route_result_history` over the raw retention window, then recompute `route_results.quality_avg` (rolling 7-day average quality tier from the updated history + current snapshot). | Per (route, day): upsert keyed on the composite PK. |
| `spam-rescore` | 120s | `spam-rescore` thread (120s) | Symmetric-window rescore of recent `messages.spam_score` (see Spam rescoring below). | Per message: only writes when the score changes. |
| `retention` | hourly | `cleanup` thread (hourly) | Drop expired hypertable chunks (`raw_receptions`, `event_logs`, `event_observers` at 30d); `cleanup_inactive_nodes`; `recompute_observer_flags`. Chunked (see Chunked retention). | Chunk drops are idempotent; node cleanup is keyed on `last_seen`. |
| `dashboard-rollups` | 300s | (new — the counts that can't be CAGGs, F2) | Upsert completed-day buckets into `dashboard_daily_message_counts`, `dashboard_daily_advert_counts`, `dashboard_node_count_history` (data-model.md §3.6a). These source from OLTP/entity tables, so they cannot be TimescaleDB continuous aggregates. | Per (instance, day, …): `INSERT … ON CONFLICT DO UPDATE`. |
| `metrics-gauges` | 60s | (new — replaces the metrics COUNT fan-out A7) | Precompute the Prometheus gauge values into a `_metrics_cache` table; `/metrics` reads the cache (TTL-cached today, but the computation moves here). | Overwrite. |
| `cagg-health` | 300s | (new) | Assert each CAGG's `refresh_status` is recent; log + alert if stale. Read-only check. | — |

> **CAGGs vs rollups:** only `cagg_daily_packet_counts` and `cagg_packet_breakdown_by_type` (over the
> `raw_receptions` hypertable) are true continuous aggregates. Daily message/advert counts and node-count
> history come from OLTP/entity tables and are maintained by the `dashboard-rollups` job above — the same
> "can't be a CAGG, so the worker owns it" rule route health follows.

## Scheduler implementation

A small home-grown loop (no APScheduler dependency). Each job is a registered `PeriodicJob` with: name, interval, `async def run(session)`, and a `pg_advisory_lock` key.

```typescript
@dataclass
class PeriodicJob:
    name: str
    interval: timedelta
    lock_key: int          # pg_advisory_xact_lock key — prevents double-execution across replicas
    run: Callable[[AsyncSession], Awaitable[None]]

class DerivedStateWorker:
    constructor(private db: DbPool, private jobs: PeriodicJob[]) {}

    async def run(self) -> None:
        # One loop, tracks per-job next_run time. On each tick, due jobs run sequentially
        # (these are DB-heavy; parallelism just adds contention). A crash restarts the
        # process and all jobs self-heal on their next due time.
        while self._running:
            now = utcnow()
            for job in self.jobs:
                if now >= self._next_run[job.name]:
                    await self._run_one(job)
                    self._next_run[job.name] = now + job.interval
            await asyncio.sleep(1)

    async def _run_one(self, job: PeriodicJob) -> None:
        async with self.sessions() as s:
            # Two-arg advisory lock: (job key, stable per-instance key). Use hashtext(instance_id) — NOT a
            # positional instance_index, which shifts as tenants come/go and can differ between replicas,
            # letting the same (job, instance) run twice (F7). The two-arg form also avoids cross-job
            # collisions that `base_key + index` risks.
            await s.execute(text("SELECT pg_advisory_xact_lock(:j, hashtext(:iid))"),
                            {"j": job.lock_key, "iid": str(self.instance_id)})
            await s.execute(text("SET LOCAL app.instance_id = :id"), {"id": self.instance_id})
            try:
                await job.run(s)
                await s.commit()
                self._record(job.name, status="ok")
            except Exception:
                await s.rollback()
                self._record(job.name, status="error")
                logger.exception("job %s failed", job.name)
                # do NOT re-raise; a failed job shouldn't kill the worker
```

The `pg_advisory_xact_lock` makes the worker **HA-safe**: run two replicas, only one executes a given job per interval (the other blocks briefly then no-ops). This is the cheap version of distributed scheduling — no separate coordinator service.

## Spam rescoring as a SQL function (online + sweep)

Move the scoring logic out of Python-per-row into a Postgres function, so the online score (computed at insert in the IngestWorker) and the symmetric sweep (the `spam-rescore` job) share one implementation:

```sql
-- Computes the spam score for a message given its (path_prefix, sender_normalized)
-- and the windowed counts of prior/surrounding rows. Called once at insert, again
-- during the rescore sweep. Pure function of its inputs → idempotent.
CREATE OR REPLACE FUNCTION compute_spam_score(
    p_msg_id uuid,
    p_window interval,
    p_min_path_hops int,
    p_path_threshold int,
    p_name_threshold int,
    p_w_path float,
    p_w_name float
) RETURNS float AS $$
DECLARE
    v_msg messages%ROWTYPE;
    v_path_count int; v_name_count int; v_path_score float; v_name_score float;
BEGIN
    SELECT * INTO v_msg FROM messages WHERE id = p_msg_id;
    IF v_msg.path_prefix IS NOT NULL AND v_msg.path_len >= p_min_path_hops THEN
        SELECT count(*) INTO v_path_count FROM messages
        WHERE path_prefix = v_msg.path_prefix AND sender_normalized = v_msg.sender_normalized
          AND received_at BETWEEN v_msg.received_at - p_window AND v_msg.received_at + p_window
          AND id <> p_msg_id;
        v_path_score := least(1.0, v_path_count::float / p_path_threshold);
        RETURN p_w_path * v_path_score + p_w_name * (least(1.0, (
          SELECT count(*) FROM messages WHERE sender_normalized = v_msg.sender_normalized
            AND received_at BETWEEN v_msg.received_at - p_window AND v_msg.received_at + p_window
            AND id <> p_msg_id)::float / p_name_threshold));
    ELSE
        -- path ineligible → name signal stands alone at full weight (preserves today's behaviour)
        RETURN least(1.0, (SELECT count(*) FROM messages WHERE sender_normalized = v_msg.sender_normalized
          AND received_at BETWEEN v_msg.received_at - p_window AND v_msg.received_at + p_window
          AND id <> p_msg_id)::float / p_name_threshold);
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;
```

- **At insert** (IngestWorker): `UPDATE messages SET spam_score = compute_spam_score(id, ...) WHERE id = ?;`
- **Sweep** (`spam-rescore` job): compute the score **once per candidate** in a subquery, then filter and
  write from that single value — do **not** call the function in both `WHERE` and `SET` (it is COUNT-heavy
  and would run twice per row every 120s):

```sql
UPDATE messages m
SET    spam_score = s.new_score
FROM (
  SELECT id, compute_spam_score(id, :window, :min_path_hops, :path_threshold,
                                :name_threshold, :w_path, :w_name) AS new_score
  FROM   messages
  WHERE  received_at > now() - INTERVAL '1 hour'
) s
WHERE m.id = s.id
  AND m.spam_score IS DISTINCT FROM s.new_score;   -- only rows whose score actually changed
```

This kills the asymmetric-online / symmetric-sweep split's Python implementation (`spam.py` ~315 LOC collapses to the function + two call sites) while preserving the documented behaviour.

## Route quality averaging (`route-history` job)

The `route-history` job does two things: (1) upserts completed UTC-day buckets into `route_result_history`, then (2) recomputes `route_results.quality_avg` — the rolling 7-day average quality tier that the frontend uses as the **primary** route health indicator.

### Algorithm

For each enabled route:

1. **Read** the last 7 completed UTC days from `route_result_history` (strictly before today).
2. **Append** today's current-snapshot `quality` from `route_results` (the value the `route-evaluator` job just wrote).
3. **Map** each day's quality to an ordinal: `clear = 2`, `marginal = 1`, everything else (`failing`, `no_coverage`, `unknown`) = `0`.
4. **Average** the ordinals.
5. **Map back** to a tier: `mean ≥ 1.5 → clear`, `mean ≥ 0.75 → marginal`, `else failing`.

```sql
-- Step 1: fetch history rows for the last 7 completed days
SELECT day, quality FROM route_result_history
WHERE route_id = :route_id AND day < CURRENT_DATE AND day >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY day;
```

```typescript
// Steps 2–5: compute the average in TS (the "append today" step is awkward in pure SQL)
function computeQualityAvg(
    history: { day: Date; quality: string }[],
    todayQuality: string | null,
): string | null {
    if (!todayQuality) return null;
    if (history.length === 0) return null;  // brand-new route → null → frontend falls back

    const allDays = [...history.map(h => h.quality), todayQuality];
    const total = allDays.reduce((sum, q) => {
        if (q === 'clear') return sum + 2;
        if (q === 'marginal') return sum + 1;
        return sum;  // failing / no_coverage / unknown → 0
    }, 0);
    const mean = total / allDays.length;

    if (mean >= 1.5) return 'clear';
    if (mean >= 0.75) return 'marginal';
    return 'failing';
}
```

### Edge cases

- **Brand-new route** (no history rows): returns `null`. The frontend's `qualityOf()` helper falls back to the current-snapshot `quality` (or `"unknown"` if that's also null). This prevents a fresh route from flashing a misleading "failing" badge before its first evaluation cycle.
- **Disabled route**: the job skips it (the `route-evaluator` only evaluates `WHERE enabled = true`). `quality_avg` retains its last-computed value until the route is re-enabled.
- **Missing today quality**: returns `null` (shouldn't happen in practice — `route-evaluator` runs at 300s, `route-history` at 3600s, so today's snapshot always exists before the average runs).

### Frontend fallback priority

The frontend resolves the displayed quality tier as:

```typescript
route.quality_avg || route.route_result?.quality || "unknown";
```

`quality_avg` is the **primary** signal because a single bad evaluation (snapshot `quality = 'failing'`) shouldn't alarm the operator if the route has been clear for 6 days. The snapshot is the **fallback** for routes too new to have a 7-day average.

### Threshold sync

The clear/marginal thresholds (`1.5` / `0.75`) must be kept in sync with the frontend chart helper that colors the per-route trend line (`averageRouteTier` in `utils/charts.ts`). Both the backend computation and the frontend helper hardcode these constants with a cross-reference comment. In the single-language TS stack, a shared `constants.ts` could eliminate the sync risk, but two constants don't justify the import coupling.

## Chunked retention (no giant DELETE)

Today's `cleanup_old_data` issues one `DELETE FROM <table> WHERE received_at < cutoff` per table (§4.1-W10) — a multi-second exclusive lock on large tables. TimescaleDB makes this free:

```sql
-- Retention policies (set once, enforced automatically by chunk drops):
SELECT add_retention_policy('raw_receptions', INTERVAL '30 days');
SELECT add_retention_policy('event_logs',    INTERVAL '30 days');
SELECT add_retention_policy('event_observers', INTERVAL '30 days');
-- (telemetry: no default retention; keep indefinitely unless configured)
```

**Retention alignment:** the 30-day default for `event_observers` matches the default `settings.data_retention_days` (30) that drives the OLTP chunked DELETE for `messages`/`advertisements`/`trace_paths`. If an operator increases `data_retention_days` beyond 30, the worker's `retention` job should also update the hypertable retention policies (`remove_retention_policy` → `add_retention_policy` with the new interval). Without this alignment, events older than 30 days would show "0 observers" — their `event_observers` rows were chunk-dropped while the OLTP event rows survive. For Phase 0–6, both default to 30 and the alignment is automatic. Making the hypertable policies dynamically track the setting is a Phase 3+ enhancement.

**Orphaned rows:** `event_observers.event_hash` is a loose content-hash reference (no FK — the event could be in `messages`, `advertisements`, `trace_paths`, or `telemetry`). When the OLTP chunked DELETE removes old events, their `event_observers` rows are NOT cascade-deleted. They persist as orphans until the hypertable retention policy drops the containing chunk. This is harmless: orphaned rows are never queried (no event to join to), are compressed, and self-clean within the retention window.

For the OLTP tables that aren't hypertables (`messages`, `advertisements`, `trace_paths`), retention stays a worker job but **chunked**:

```typescript
async def retention_job(session: AsyncSession) -> None:
    cutoff = utcnow() - timedelta(days=settings.data_retention_days)
    for table in ("messages", "advertisements", "trace_paths"):
        # Chunked delete: 5000 rows per statement, loop until 0 affected.
        # Each statement is short-lived → no long lock.
        while True:
            result = await session.execute(text(f"""
                DELETE FROM {table} WHERE id IN (
                    SELECT id FROM {table} WHERE received_at < :cutoff LIMIT 5000
                ) FOR UPDATE SKIP LOCKED
            """), {"cutoff": cutoff})
            if result.rowcount < 5000:
                break
```

`cleanup_inactive_nodes` and `recompute_observer_flags` follow the same chunked pattern.

**Node cleanup does not touch the hypertables (F6).** The hypertable columns that point at `nodes`
(`raw_receptions.observer_node_id`, `event_observers.observer_node_id`, `telemetry.node_id`,
`event_logs.observer_node_id`) are **loose `uuid` references with no FK** (data-model.md §3.6). If they were
real FKs with `ON DELETE SET NULL/CASCADE`, deleting an inactive node would force DML across hypertable
chunks — including compressed ones, where DML is restricted/costly — turning an hourly cleanup into a
decompress storm. Instead, a deleted node simply leaves a dangling id in history (harmless, like the
orphaned `event_observers` rows above); it compresses and ages out on retention.

## Observability

Each job emits:
- A Prometheus gauge `derived_job_last_success_timestamp{job="..."}`.
- A counter `derived_job_iterations_total{job="...",status="ok|error"}`.
- A histogram `derived_job_duration_seconds{job="..."}`.
- The `cagg-health` job additionally exports `cagg_refresh_lag_seconds{name="..."}`.

These replace the collector's `HealthReporter` (which today just tracks MQTT/DB connectivity). The worker's health endpoint (`/health/derived`) reports whether any job is overdue beyond `2 × interval`.
