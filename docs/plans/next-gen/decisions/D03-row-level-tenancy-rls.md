# D03: Row-Level `instance_id` + RLS for Multi-Tenancy

- **Status:** Locked
- **Iteration:** 2

## Context

Today multi-tenant isolation is **connection-level only**: `SET search_path = instance_<id>` is the entire guard (S3). A connection that leaks out of its pool — a misconfigured worker, a query logged with the wrong session, a future async-session bug — silently crosses instances. The schema-per-instance model is operationally nice (one dump per instance, simple restore) but it is not defense in depth. The §13-D3 question: keep schema-per-instance as the *only* boundary, harden it with row-level `instance_id` + RLS, or move to a database-per-instance model?

## Decision

**Row-level `instance_id` column on every tenant-scoped table + Postgres Row Level Security policies**, in addition to the existing schema-per-instance *option*. Every tenant-scoped table in the §16 schema (`nodes`, `node_tags`, `user_profiles`, `channels`, `routes`, `messages`, `advertisements`, `raw_receptions`, etc.) carries `instance_id uuid NOT NULL REFERENCES instances(id)`. Each table gets:

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING (instance_id = current_setting('app.instance_id', true)::uuid);
```

The app issues `SET LOCAL app.instance_id = '<uuid>';` at the start of every transaction (connection-pool hook + async-session `before_commit` hook). Schema-per-instance remains available as a belt-and-braces layer for operators who want physical separation; it is no longer the *only* boundary.

## Consequences

**Positive:** Defense in depth — a leaking connection cannot cross instances even if `search_path` is wrong. One schema, one connection pool, simpler backup/restore vs database-per-instance. RLS policies are declarative and auditable. Pairs naturally with D11's instance-scoped `settings` table and the `instance_id` claim embedded in the JWT (D6).

**Negative:** Every query pays a `current_setting(...)` predicate; index design must include `instance_id` where selective. Developers must remember `SET LOCAL` at transaction start (the framework hook makes this automatic, but it is a footgun if bypassed). RLS doesn't compose cleanly with superuser connections — operational scripts must `SET ROLE` appropriately.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Row-level `instance_id` + RLS** (chosen) | Best for shared clusters; defense in depth beyond `search_path`; one pool, one backup. |
| Database-per-instance | Rejected as primary — simplest mental model but heavier on connection pools, more moving parts for backup/restore, no advantage over RLS for the shared-cluster case. |
| Schema-per-instance only (today's model) | Rejected — connection-level isolation is not a security boundary; a leaking connection = cross-instance exposure. |
| Application-level `instance_id` filter in every query | Rejected — relies on developer discipline; one missed `WHERE` is a cross-instance leak. |
