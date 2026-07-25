# D16: Two-Replica `DerivedStateWorker` HA via Advisory Locks

- **Status:** Locked
- **Iteration:** 4

## Context

The §19.1 manifest consolidates six daemon threads into one `DerivedStateWorker` process owning every periodic job (route evaluator, route history, spam rescore, retention, metrics gauges, CAGG health). A single process is a SPOF — a crash stops all derived-state maintenance until restart. The §19.2 / §13-D16 question: how to provide HA without introducing a separate coordinator service (etcd/Consul) or a clustering framework?

## Decision

**Two-replica deployment with `pg_advisory_xact_lock` per job.** Each `PeriodicJob` carries a `lock_key: int`. The worker's `_run_one` acquires `SELECT pg_advisory_xact_lock(:k)` at the start of the job's transaction:

```typescript
await db.transaction(async (tx) => {
    // Two-arg lock: (job key, stable per-instance key). In multi-tenant mode use
    // hashtext(instanceId) as the second arg — NOT a positional instance_index, which shifts as
    // tenants come/go and can double-execute across replicas (F7).
    await tx.execute(sql`SELECT pg_advisory_xact_lock(${job.lockKey}, hashtext(${instanceId}))`);
    await tx.execute(sql`SET LOCAL app.instance_id = ${instanceId}`);
    try {
        await job.run(tx);
        await tx.commit();
    } catch (err) {
        await tx.rollback();
    }
});
```

Run two replicas; for any given job interval, **only one executes** (the one that acquires the lock first), the other blocks briefly then no-ops when its `fetch` returns nothing. This is the cheap version of distributed scheduling — no separate coordinator service, no clustering framework, just Postgres.

## Consequences

**Positive:** Worker crash ≠ derived-state staleness — the second replica keeps executing jobs on its next due tick. Zero new infrastructure (Postgres advisory locks are built-in). Per-job `lock_key` means both replicas can run *different* jobs concurrently if their intervals align, improving throughput vs strict leader-election. Same pattern composes with D3's `SET LOCAL app.instance_id`.

**Negative:** Both replicas must reach the same Postgres cluster (advisory locks are per-cluster, not global). A locked-but-crashed transaction releases the lock at rollback/commit (transaction-scoped), so no stale-lock cleanup is needed — but a long-running job holds the lock for its duration. Two replicas is the cap; more replicas just waste cycles blocking on locks.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Two-replica + advisory locks** (chosen) | HA without a coordinator; cheap; built on Postgres primitives. |
| Single replica | Rejected — SPOF; a crash stops all derived-state maintenance. |
| External coordinator (etcd / Consul leader election) | Rejected — adds infra for a problem advisory locks already solve. |
| APScheduler / node-cron clustering | Rejected — heavier dependency; advisory locks cover the same guarantee. |
| Application-level distributed lock (Redis Redlock) | Rejected — would re-introduce a Redis dependency on the worker path. |
