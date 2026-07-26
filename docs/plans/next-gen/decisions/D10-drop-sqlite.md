# D10: Drop SQLite — Postgres-Only From Phase 0

- **Status:** Locked
- **Iteration:** 2

## Context

Today the project supports two database backends: SQLite (default, deprecated ~3 months) and Postgres (opt-in via `DATABASE_BACKEND=postgres`). The cost of the dual-backend surface is substantial: every migration carries an `if conn.dialect.name ==` branch, `batch_alter_table` wrappers for SQLite's ALTER limitations, `postgresql_include` conditional indexes, and a dual-driver `[postgres]` extra. More structurally, supporting SQLite blocks unconditional adoption of native `uuid` PKs, Postgres enums, and `JSONB` — the typing upgrades (data-model.md §3.1) the rewrite relies on. SQLite was already deprecated; the question was when to actually drop it.

## Decision

**Drop SQLite immediately.** Phase 0 starts **Postgres-only**. Native `uuid` PKs (`gen_random_uuid()`), native Postgres enums (`channel_visibility`, `route_visibility`, `route_state`, `route_quality`, `message_kind`), `JSONB` everywhere JSON is used today, and `node-postgres` (`pg`) as the unconditional driver (per the D22 TypeScript stack — this iteration-2 decision originally named the Python `asyncpg`). All dialect branches, `batch_alter_table`, and the dual-driver packaging disappear.

Existing SQLite operators migrate via a documented `db migrate-to-postgres` runbook **before** upgrading to the rewrite. There is no in-place SQLite path in the new schema.

## Consequences

**Positive:** Every `if dialect.name ==` branch goes away — materially cleaning Phase 0. Native types everywhere: `uuid` joins are faster than `String(36)` across ~25 FK columns (W8); enums are constrainable; `JSONB` enables GIN indexes (W9). `node-postgres` becomes the unconditional driver, simplifying the async API path (A5). Migrations are Postgres-native (no batch wrapper).

**Negative:** Operators on SQLite must migrate before upgrading — a real one-time cost. Development now requires a local Postgres (mitigated: docker compose). The zero-config "just write to a file" deployment story is gone.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Drop SQLite now** (chosen) | Unblocks native types + `node-postgres`; eliminates dialect-branch maintenance. |
| Keep SQLite as a tier-2 supported backend | Rejected — blocks native `uuid`/enums/`JSONB`; preserves every dialect branch; SQLite was already deprecated. |
| Defer the drop until after Phase 0 | Rejected — the native-types decision is upstream of every Phase 0 schema choice (data-model.md §3); deferring pushes the cost into every later phase. |
| SQLite for dev, Postgres for prod | Rejected — the dialect branches are the cost being eliminated; a split-env model reintroduces them. |
