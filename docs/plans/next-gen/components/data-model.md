# Data Model

> **Related decisions:** D1 (TimescaleDB for history), D3 (row-level `instance_id` + RLS), D5 (fold `packet_path_hops` — spike), D8 (compress raw bytes in-DB)
>
> **Subsidiary decisions:** Q-A (`bigserial` PK on hypertables), Q-B (single `hops jsonb` array on `trace_paths`)
>
> **Source:** Restructured from `REWRITE.md` §6.3 (schema changes), §6.4 (schema sketch), §16 (Phase 0 DDL — preserved verbatim as the authoritative DDL).

---

## 1. Schema changes (structural)

These are the *structural* changes — column renames and feature additions are out of scope and belong to per-phase design tasks.

### 1.1 Identity & typing

- **Native `uuid` PKs** (Postgres `uuid`, default `gen_random_uuid()`). Every FK becomes `uuid`. Fixes W8 (the `String(36)` UUID join penalty).
- **Native enums** for `ChannelVisibility`, `RouteVisibility`, `RouteState`, `RouteQuality` (Postgres `CREATE TYPE`). Fixes "string enums."
- **`JSONB` everywhere** JSON is used today; add GIN indexes where queried (`telemetry.parsed_data`, `trace_paths` after restructuring).
- **SHA-256 (truncated) dedup hashes** instead of MD5. Fixes W5.

### 1.2 Collapse the dual-hash confusion (W4)

Standardize on **one** content identity column per event table:

- `event_hash` = content dedup key (stays).
- `wire_hash` = the LetsMesh on-air hash, stored **only on `raw_receptions`** (the history store) and joined when needed — not denormalized onto every structured row.

### 1.3 Restructure the high-volume tables

**`raw_receptions`** (renamed from `raw_packets` to reflect "one row per observer reception"):

- **D8 (deferred):** keep `raw_hex` (Text) on the row but lean on TimescaleDB compression; add a nullable `object_key` + `BlobStore` interface now so a later move to MinIO/local-volume/S3 is config-only, not a migration. Add `decoded_summary` JSONB (small, for list views) alongside the existing `decoded`.
- Keep queryable metadata columns (`packet_type`, `payload_type`, `event_type`, `channel_idx`, `source_pubkey_prefix`, `route_type`, `path_len`, `path_hash_width`, `snr`).
- **TimescaleDB hypertable** partitioned by `received_at` (1-day chunks), columnar compression after 24h, configurable retention (default 30d instead of 2d).
- Fewer, targeted indexes; compression makes scan-heavy queries cheap.

**`packet_path_hops`** (D5 spike — Phase 0):

- **Preferred target:** fold into a `path_hashes text[]` array column on `raw_receptions` + a GIN index. One insert per reception instead of 1+N; the matcher loads one array instead of joining N rows.
- **Fallback:** if the GIN-containment candidate query regresses perf, keep a separate hypertable but **stop denormalizing** `packet_hash`, `received_at`, `observer_node_id` (reachable via the FK).
- Decide with a benchmark in **Phase 0**, before this DDL is authored (rescheduled from Phase 2 — F5, since the benchmark shapes the schema); the array path is the default assumption in the DDL below.

**`telemetry`**: hypertable; `parsed_data` JSONB + GIN; raw LPP bytes follow the same D8 `object_key` pattern as `raw_receptions`.

**`event_logs`** (renamed from `events_log` for naming consistency; D2 locked): hypertable, compressed aggressively, 30d retention default.

### 1.4 Route health — corrected framing (W6)

Route matching is **subsequence logic** over packet paths, not pure time-bucketing — it cannot be a TimescaleDB continuous aggregate. So:

- `routes`, `route_nodes`, `route_observers` stay (definitions) — add the missing `UNIQUE(route_id, position)` and `UNIQUE(route_id, node_id)` constraints.
- `route_results`, `route_result_history`, `route_recent_matches` stay as **worker-maintained tables** — but maintained by the single `DerivedStateWorker`, not 2 inline background cadences. The matcher reads `raw_receptions.path_hashes` directly (D5 outcome).
- Continuous aggregates are reserved for the **dashboard** time-bucketing that sources from a hypertable — daily **packet** counts and the packet breakdown by type (both over `raw_receptions`). Daily message/advert counts and node-count history source from OLTP/entity tables, so they are **worker-maintained rollup tables** (§3.6a), not CAGGs — the same rule as route health.

Net: the route-health subsystem loses 2 background threads + the inline maintenance + the write-amplified hops table, but keeps its 3 derived tables. The CAGG win is the packet counts/breakdown; the dashboard's dedup'd-event counts move to cheap worker-maintained rollups.

### 1.5 Roles & security (S3, S4)

- `user_profile_roles` join table (one row per profile × role) instead of CSV text. Indexable, constrainable.
- **Row-level `instance_id` column** on every tenant-scoped table + Postgres RLS policies, **in addition to** `search_path`. Defense in depth: even a leaking connection cannot cross instances. (D3 locks row-level `instance_id` + RLS; schema-per-instance stays as an optional belt-and-braces layer.)
- **RLS must be forced and the app must not own the tables.** Postgres skips RLS for a table's owner. The migration/DDL role owns the tables; the application connects as a **separate non-owner role** (`meshcore_app`), and every table sets `FORCE ROW LEVEL SECURITY` so even a mistakenly-privileged connection is still policy-checked. Without both of these, RLS is silently inert.
- **All uniqueness is instance-scoped from Phase 0.** Every "unique" business key is `UNIQUE (instance_id, …)` — `nodes.public_key`, the dedup'd-event `event_hash` columns, `channels.name`/`key_hex`, `settings (instance_id, key)`. A physical node or a repeated on-air packet legitimately appears once *per tenant*; a global unique would let one tenant's row block another's insert. In single-tenant mode there is one instance, so this is behaviourally identical — but it is what makes Phase 7 genuinely additive (D21).

### 1.6 Naming consistency

- Pick one convention (plural tables) and apply it: `events_log` → `event_logs`, `route_result_history` stays singular-concept but rename for consistency.

---

## 2. Schema sketch (conceptual — full DDL in §3)

```
ENTITIES (Postgres OLTP)
  instances(id, name)                                   -- tenancy root (D3)
  nodes(id uuid, public_key, name, adv_type, flags, lat, lon, is_observer, ..., instance_id)
  node_tags(id, node_id, key, value, value_type, instance_id)
  user_profiles(id, user_id, name, callsign, description, url, instance_id)
  user_profile_roles(profile_id, role)                  -- replaces CSV (S4)
  user_profile_nodes(profile_id, node_id, adopted_at)   -- one-adopter UC
  channels(id, name, key_hex, key_hash, visibility, enabled, instance_id)
  routes(id, from_label, to_label, visibility, thresholds..., created_by, instance_id)
  route_nodes(route_id, node_id, position, expected_hash)      -- +UC(route,position)
  route_observers(route_id, node_id)                           -- +UC(route,node)

DEDUP'D EVENTS (Postgres OLTP, sha256-truncated hashes)
  messages(id, event_hash bytea, kind, pubkey_prefix, channel_idx, text, ..., spam_score, instance_id)
  advertisements(id, event_hash bytea, public_key, name, adv_type, route_type, advert_timestamp, ...)
  trace_paths(id, event_hash bytea, initiator_tag, hops jsonb, ...)   -- single array, not parallel

HYPERTABLES (TimescaleDB, compressed)
  raw_receptions(received_at, id bigserial, observer_node_id, wire_hash, event_hash,
                 raw_hex, object_key, decoded_summary, ...,
                 path_hashes text[], path_hash_width, snr, instance_id)  -- D5 folded
  event_observers(observed_at, event_hash, observer_node_id, ...)       -- hypertable junction
  telemetry(received_at, id, node_id, parsed_data jsonb, object_key, ...)
  event_logs(received_at, id, event_type, payload jsonb, ...)           -- D2 locked

CONTINUOUS AGGREGATES (only over the raw_receptions hypertable — the A7 win)
  cagg_daily_packet_counts, cagg_packet_breakdown_by_type

DASHBOARD ROLLUPS (worker-maintained — sources aren't hypertables, so NOT CAGGs)
  dashboard_daily_message_counts, dashboard_daily_advert_counts, dashboard_node_count_history

ROUTE HEALTH (worker-maintained — NOT CAGGs; subsequence logic)
  route_results(route_id PK, state, quality, quality_avg, matched_count, ..., instance_id)
  route_result_history(route_id, day, quality, state, matched_count, instance_id)   -- PK(route,day)
  route_recent_matches(route_id, raw_reception_rowid, first_pos, last_pos, instance_id)

OBJECT STORAGE (deferred — D8; only if measured necessary)
  packets/{date}/{wire_hash}.bin, telemetry/{date}/{id}.bin
```

---

## 3. Phase 0 — Schema DDL (target, authoritative)

Postgres-only (D10). Native `uuid`, native enums, `JSONB`, TimescaleDB hypertables. Every tenant-scoped table carries `instance_id` with an RLS policy (D3). PKs are `gen_random_uuid()` except for the hypertables, whose PK must include the time column (TimescaleDB requirement): `raw_receptions` uses a cheap **`bigint IDENTITY`** second column (Q-A), `telemetry`/`event_logs` pair the time column with a `uuid`, and `event_observers` uses a natural composite key — see §4. `trace_paths.hops` is a **single `jsonb` array** (Q-B).

### 3.1 Enums

```sql
CREATE TYPE channel_visibility AS ENUM ('community', 'member', 'operator', 'admin');
CREATE TYPE route_visibility   AS ENUM ('community', 'member', 'operator', 'admin');
CREATE TYPE route_state        AS ENUM ('healthy', 'unhealthy', 'no_coverage');
CREATE TYPE route_quality      AS ENUM ('clear', 'marginal', 'failing', 'unknown');
CREATE TYPE message_kind       AS ENUM ('contact', 'channel');   -- replaces free-form message_type string
-- adv_type stays TEXT (SCHEMAS.md: values are open-ended: chat/repeater/room/companion + upstream drift)
```

### 3.2 Tenancy

```sql
CREATE TABLE instances (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  deleted_at  timestamptz                 -- soft-delete (Phase 7): application-enforced, not RLS-enforced.
);                                        -- Hostname cache + JWT expiry gate access; data stays until purge.
```

A single-row seed (`INSERT INTO instances ...`) is created by the initial migration derived from `NETWORK_NAME`. Every tenant-scoped table below gets `instance_id uuid NOT NULL REFERENCES instances(id)` and:

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;          -- also enforce for the table owner
CREATE POLICY tenant_isolation ON <t>
  USING       (instance_id = current_setting('app.instance_id', true)::uuid)
  WITH CHECK  (instance_id = current_setting('app.instance_id', true)::uuid);   -- block cross-instance writes too
```

Roles: the DDL/migration role owns the tables; the application connects as a **non-owner role**
(`meshcore_app`, granted DML only). Owner-bypass is why `FORCE` is required.

The app issues `SET LOCAL app.instance_id = '<uuid>';` at the start of **every transaction — reads
included**. Because `SET LOCAL` is transaction-scoped, any statement run in autocommit sees a NULL GUC
and the policy returns 0 rows. The API therefore wraps **each request** in a transaction (a Fastify
`preHandler`/`onRequest` hook opens the tx and issues the `SET LOCAL` before the handler runs); the
`DerivedStateWorker` and `IngestWorker` already do this per job/batch. This is the one RLS footgun to
guard in review — a read path that bypasses the request transaction silently loses tenant scoping.
This is defense-in-depth on top of the existing schema-per-instance option.

### 3.3 Entities (OLTP)

```sql
CREATE TABLE nodes (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_key   char(64) NOT NULL,
  name         text,
  adv_type     text,
  flags        int,
  lat          double precision,
  lon          double precision,
  is_observer  boolean NOT NULL DEFAULT false,
  first_seen   timestamptz NOT NULL DEFAULT now(),
  last_seen    timestamptz,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, public_key)   -- per-tenant: the same physical node exists once per instance
);

CREATE TABLE node_tags (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id      uuid NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  key          text NOT NULL,
  value        text,
  value_type   text NOT NULL DEFAULT 'string',
  instance_id  uuid NOT NULL REFERENCES instances(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (node_id, key)
);

CREATE TABLE user_profiles (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      text NOT NULL,          -- OIDC sub
  name         text,
  callsign     text,
  description  text,
  url          text,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, user_id)
);

-- Replaces the CSV-text roles column (S4): indexable, constrainable.
CREATE TABLE user_profile_roles (
  profile_id   uuid NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  role         text NOT NULL,
  PRIMARY KEY (profile_id, role)
);

CREATE TABLE user_profile_nodes (
  user_profile_id uuid NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  node_id         uuid NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  adopted_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_profile_id, node_id),
  UNIQUE (node_id)             -- one adopter per node; node_id is already instance-specific (per-tenant node rows)
);

CREATE TABLE channels (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL,
  key_hex      text NOT NULL,
  key_hash     smallint NOT NULL,        -- first byte of sha256(key); API exposes as 2-hex
  visibility   channel_visibility NOT NULL DEFAULT 'community',
  enabled      boolean NOT NULL DEFAULT true,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, name),
  UNIQUE (instance_id, key_hex)
);
```

### 3.4 Routes (definitions only — derived tables in §3.7)

```sql
CREATE TABLE routes (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_label             text NOT NULL,
  to_label               text NOT NULL,
  description            text,
  visibility             route_visibility NOT NULL DEFAULT 'community',
  match_width            int NOT NULL DEFAULT 1,
  window_hours           int NOT NULL DEFAULT 6,    -- app clamps to ≤12
  packet_count_threshold int NOT NULL DEFAULT 5,
  clear_threshold        int,
  max_hop_span           int DEFAULT 8,
  max_path_length        int,
  enabled                boolean NOT NULL DEFAULT true,
  reversible             boolean NOT NULL DEFAULT true,
  created_by             text,                      -- user_id; INDEXED this time
  instance_id            uuid NOT NULL REFERENCES instances(id),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, from_label, to_label)
);
CREATE INDEX ix_routes_created_by ON routes(created_by);   -- fixes the unindexed-creator pain

CREATE TABLE route_nodes (
  route_id      uuid NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  node_id       uuid NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  position      int NOT NULL,
  expected_hash text,
  PRIMARY KEY (route_id, position)        -- adds the previously-missing uniqueness
);
CREATE INDEX ix_route_nodes_node ON route_nodes(node_id);

CREATE TABLE route_observers (
  route_id      uuid NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  node_id       uuid NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  PRIMARY KEY (route_id, node_id)         -- adds the previously-missing uniqueness
);
```

### 3.5 Dedup'd events (OLTP) — SHA-256 truncated hashes

```sql
CREATE TABLE messages (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_hash        bytea NOT NULL,           -- sha256(content) truncated to 16 bytes
  kind              message_kind NOT NULL,    -- 'contact' | 'channel'
  pubkey_prefix     char(12),
  channel_idx       int,
  text              text NOT NULL,
  path_len          int,
  txt_type          int,
  signature         text,
  snr               real,
  sender_timestamp  timestamptz,
  -- spam scoring (kept; rescoring moves to a DB function in Phase 3)
  path_prefix       text,
  sender_normalized text,
  spam_score        real,
  received_at       timestamptz NOT NULL DEFAULT now(),
  instance_id       uuid NOT NULL REFERENCES instances(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, event_hash)     -- dedup is per-tenant (multi-tenancy.md §10)
);
CREATE INDEX ix_messages_kind_received     ON messages(kind, received_at);
CREATE INDEX ix_messages_prefix_received   ON messages(pubkey_prefix, received_at);
CREATE INDEX ix_messages_channel_received  ON messages(channel_idx, received_at);
CREATE INDEX ix_messages_sender_received   ON messages(sender_normalized, received_at);
CREATE INDEX ix_messages_pathprefix_received ON messages(path_prefix, received_at) WHERE path_prefix IS NOT NULL;

CREATE TABLE advertisements (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_hash       bytea NOT NULL,
  public_key       char(64) NOT NULL,
  name             text,
  adv_type         text,
  flags            int,
  route_type       text,
  advert_timestamp timestamptz,
  received_at      timestamptz NOT NULL DEFAULT now(),
  instance_id      uuid NOT NULL REFERENCES instances(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, event_hash)     -- per-tenant dedup
);
CREATE INDEX ix_adverts_pubkey ON advertisements(public_key);
CREATE INDEX ix_adverts_route_type_received ON advertisements(route_type, received_at);  -- previously unindexed
CREATE INDEX ix_adverts_received ON advertisements(received_at);

CREATE TABLE trace_paths (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_hash    bytea NOT NULL,
  initiator_tag bigint NOT NULL,
  path_len      int,
  flags         int,
  auth          int,
  hops          jsonb,                 -- [{hash, snr}, ...] — kills the parallel-array antipattern (W9)
  hop_count     int,
  received_at   timestamptz NOT NULL DEFAULT now(),
  instance_id   uuid NOT NULL REFERENCES instances(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, event_hash)     -- per-tenant dedup
);
CREATE INDEX ix_trace_initiator ON trace_paths(initiator_tag);
CREATE INDEX ix_trace_received  ON trace_paths(received_at);
```

### 3.6 Hypertables (high-volume) + continuous aggregates

TimescaleDB. Note: hypertables require the time column in the PK.

```sql
-- raw_receptions (renamed; D5 default = path_hashes folded in as array)
CREATE TABLE raw_receptions (
  received_at          timestamptz NOT NULL,
  id                   bigint GENERATED ALWAYS AS IDENTITY,   -- cheap, hypertable-friendly
  observer_node_id     uuid,                      -- loose ref to nodes.id; NO FK (see note below)
  wire_hash            char(32),                  -- LetsMesh on-air hash; Nats-Msg-Id source
  event_hash           bytea,                     -- backlink to dedup'd event, filled post-dispatch
  instance_id          uuid NOT NULL REFERENCES instances(id),
  -- D8: raw_hex stays for now (TimescaleDB compresses it); object_key nullable for a later move
  raw_hex              text,
  object_key           text,
  decoded_summary      jsonb,                     -- small, for list views
  decoded              jsonb,                     -- full decoder output, detail views
  packet_type          int,
  payload_type         int,
  event_type           text,
  channel_idx          int,
  source_pubkey_prefix char(12),
  route_type           text,
  path_len             int,
  path_hashes          text[],                    -- D5 folded array (replaces packet_path_hops)
  path_hash_width      int,
  snr                  real,
  PRIMARY KEY (received_at, id)
);
SELECT create_hypertable('raw_receptions', 'received_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ix_raw_event_type_received   ON raw_receptions(event_type, received_at);
CREATE INDEX ix_raw_channel_received      ON raw_receptions(channel_idx, received_at);
CREATE INDEX ix_raw_source_received       ON raw_receptions(source_pubkey_prefix, received_at);
CREATE INDEX ix_raw_wirehash_received     ON raw_receptions(wire_hash, received_at);
CREATE INDEX ix_raw_event_hash            ON raw_receptions(event_hash);
CREATE INDEX ix_raw_pathhash_gin          ON raw_receptions USING gin(path_hashes);  -- D5 route matching
ALTER TABLE raw_receptions SET (timescaledb.compress, timescaledb.compress_segmentby = 'observer_node_id');
SELECT add_compression_policy('raw_receptions', INTERVAL '24 hours');
SELECT add_retention_policy('raw_receptions', INTERVAL '30 days');
-- NOTE (F6): the four hypertables reference nodes.id as a LOOSE uuid (no FK, no ON DELETE action).
-- A real FK with ON DELETE SET NULL/CASCADE would force cross-chunk DML — including on COMPRESSED
-- chunks, where DML is restricted/expensive — every time hourly node cleanup deletes a node. A dangling
-- node id is harmless here (same tolerance the plan already accepts for orphaned event_observers rows):
-- history repopulates and ages out on retention. RLS still scopes rows by instance_id.

-- event_observers (junction, also hypertable)
CREATE TABLE event_observers (
  observed_at       timestamptz NOT NULL,
  event_hash        bytea NOT NULL,
  event_type        text NOT NULL,
  observer_node_id  uuid NOT NULL,               -- loose ref to nodes.id; NO FK (hypertable, see F6 note)
  snr               real,
  path_len          int,
  instance_id       uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (observed_at, event_hash, observer_node_id)
);
SELECT create_hypertable('event_observers', 'observed_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ix_event_obs_type_hash ON event_observers(event_type, event_hash);
-- segmentby = 'event_type' (not observer_node_id): the hot query is
-- "which observers saw these events?" filtered by event_type + event_hash
-- (observer_utils.fetch_observers_for_events, called on every list endpoint).
-- Segmenting by event_type lets TimescaleDB skip non-matching compressed batches.
ALTER TABLE event_observers SET (timescaledb.compress, timescaledb.compress_segmentby = 'event_type');
SELECT add_compression_policy('event_observers', INTERVAL '24 hours');
SELECT add_retention_policy('event_observers', INTERVAL '30 days');

-- telemetry
CREATE TABLE telemetry (
  received_at      timestamptz NOT NULL,
  id               uuid DEFAULT gen_random_uuid(),
  node_id          uuid,                    -- loose ref to nodes.id; NO FK (hypertable, see F6 note)
  node_public_key  char(64) NOT NULL,
  parsed_data      jsonb,
  object_key       text,
  event_hash       bytea,                   -- backlink to dedup'd event; NOT UNIQUE (hypertable constraint).
                                            -- Dedup is BEST-EFFORT: Nats-Msg-Id window dedup suppresses
                                            -- redelivery, but two worker replicas can still both insert a
                                            -- telemetry row (no unique to catch the race). Residual
                                            -- duplicates are de-duplicated on read by (instance_id, event_hash).
  instance_id      uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (received_at, id)
);
SELECT create_hypertable('telemetry', 'received_at', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ix_telemetry_node_received ON telemetry(node_id, received_at);
CREATE INDEX ix_telemetry_parsed_gin    ON telemetry USING gin(parsed_data);
ALTER TABLE telemetry SET (timescaledb.compress, timescaledb.compress_segmentby = 'node_id');
SELECT add_compression_policy('telemetry', INTERVAL '24 hours');
-- Optional retention (telemetry is otherwise unbounded). Enabled when tuning.telemetry_retention_days
-- is set; the retention job (derived-state.md) keeps the policy in sync with the setting.
-- SELECT add_retention_policy('telemetry', INTERVAL '90 days');

-- event_logs (renamed from events_log for naming consistency; D2 locked)
CREATE TABLE event_logs (
  received_at       timestamptz NOT NULL,
  id                uuid DEFAULT gen_random_uuid(),
  observer_node_id  uuid,                       -- loose ref to nodes.id; NO FK (hypertable, see F6 note)
  event_type        text NOT NULL,
  payload           jsonb,
  instance_id       uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (received_at, id)
);
SELECT create_hypertable('event_logs', 'received_at', chunk_time_interval => INTERVAL '1 day');
ALTER TABLE event_logs SET (timescaledb.compress, timescaledb.compress_segmentby = 'event_type');
SELECT add_compression_policy('event_logs', INTERVAL '24 hours');
SELECT add_retention_policy('event_logs', INTERVAL '30 days');
```

Continuous aggregates (the dashboard win — replaces fan-out COUNTs).

**A continuous aggregate can only be built over a hypertable.** `messages` and `advertisements` are
deliberately plain OLTP tables (content-hash dedup needs a global `event_hash` unique that a hypertable
can't provide). So **only the two `raw_receptions`-sourced counts are true CAGGs**; the dedup'd-event and
node-count rollups the dashboard needs are **worker-maintained tables** (see §3.6a) — the same
"can't be a CAGG, so the worker owns it" rule the route-health tables follow (§1.4).

```sql
-- Valid CAGGs (source = raw_receptions, a hypertable):
CREATE MATERIALIZED VIEW cagg_daily_packet_counts
WITH (timescaledb.continuous) AS
  SELECT date_trunc('day', received_at) AS day, instance_id, count(*) AS cnt
  FROM raw_receptions GROUP BY 1, 2
  WITH NO DATA;
SELECT add_continuous_aggregate_policy('cagg_daily_packet_counts',
  start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '5 minutes');

CREATE MATERIALIZED VIEW cagg_packet_breakdown_by_type
WITH (timescaledb.continuous) AS
  SELECT date_trunc('day', received_at) AS day, instance_id, event_type, count(*) AS cnt
  FROM raw_receptions GROUP BY 1, 2, 3
  WITH NO DATA;
SELECT add_continuous_aggregate_policy('cagg_packet_breakdown_by_type',
  start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '5 minutes');
```

**RLS note:** RLS policies on the underlying hypertable do **not** propagate to a continuous aggregate.
Dashboard reads of these CAGGs must therefore carry an explicit `WHERE instance_id = current_setting(
'app.instance_id')::uuid` predicate (the API adds it from the `Principal`) — the CAGG is not a
tenant-safe surface on its own.

### 3.6a Dashboard rollups (worker-maintained — the counts that can't be CAGGs)

Daily **message** counts, **advert** counts, and **node-count history** are sourced from OLTP tables
(`messages`, `advertisements`) or from entity state (`nodes`) that has no append-only time column — none
can be a continuous aggregate. They are refreshed by the `dashboard-rollups` DerivedStateWorker job
(see [derived-state.md](derived-state.md#job-manifest)) as instance-scoped, RLS'd tables:

```sql
CREATE TABLE dashboard_daily_message_counts (
  day          date NOT NULL,
  kind         message_kind NOT NULL,
  channel_idx  int NOT NULL DEFAULT -1,   -- -1 = the "no channel" bucket (contact messages); a PK column can't be nullable and ON CONFLICT can't match NULL
  cnt          int NOT NULL,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (instance_id, day, kind, channel_idx)
);
ALTER TABLE dashboard_daily_message_counts ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_daily_message_counts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dashboard_daily_message_counts
  USING (instance_id = current_setting('app.instance_id', true)::uuid);

CREATE TABLE dashboard_daily_advert_counts (
  day          date NOT NULL,
  route_type   text NOT NULL DEFAULT '',   -- '' = the "no route_type" bucket; a PK column can't be nullable and ON CONFLICT can't match NULL
  cnt          int NOT NULL,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (instance_id, day, route_type)
);
ALTER TABLE dashboard_daily_advert_counts ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_daily_advert_counts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dashboard_daily_advert_counts
  USING (instance_id = current_setting('app.instance_id', true)::uuid);

CREATE TABLE dashboard_node_count_history (
  day            date NOT NULL,
  active_nodes   int NOT NULL,        -- nodes with last_seen on `day`
  total_nodes    int NOT NULL,        -- cumulative known nodes as of `day`
  instance_id    uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (instance_id, day)
);
ALTER TABLE dashboard_node_count_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_node_count_history FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dashboard_node_count_history
  USING (instance_id = current_setting('app.instance_id', true)::uuid);
```

The job upserts completed-day buckets (`INSERT … ON CONFLICT (…) DO UPDATE`) each run — idempotent,
cheap (a handful of `GROUP BY` queries), and RLS-scoped like every other tenant table. The worker
`COALESCE`s the nullable source columns into the sentinel (`channel_idx → -1`, `route_type → ''`)
before the upsert so every bucket — including the "no channel"/"no route_type" bucket — matches on a
total primary key (NULL ≠ NULL would otherwise break idempotency for exactly those rows).

### 3.7 Route health (worker-maintained, not CAGGs)

Route matching is subsequence logic — it cannot be a CAGG. Three derived tables are maintained by the `route-evaluator` (300s) and `route-history` (3600s) jobs in the [DerivedStateWorker](derived-state.md#route-quality-averaging-route-history-job). `quality` is the current snapshot; `quality_avg` is the rolling 7-day average that the frontend prefers (see the [quality averaging algorithm](derived-state.md#route-quality-averaging-route-history-job) for the ordinal mapping and thresholds).

```sql
CREATE TABLE route_results (
  route_id         uuid PRIMARY KEY REFERENCES routes(id) ON DELETE CASCADE,
  state            route_state NOT NULL,
  quality          route_quality NOT NULL,        -- current-snapshot quality (latest evaluation)
  quality_avg      route_quality,                 -- rolling 7-day average quality tier (refreshed by the route-history job from route_result_history; the frontend prefers this over the snapshot)
  matched_count    int NOT NULL,
  threshold        int NOT NULL,
  effective_clear  int NOT NULL,
  evaluated_at     timestamptz NOT NULL DEFAULT now(),
  instance_id      uuid NOT NULL REFERENCES instances(id)   -- denormalized for RLS (1:1 with routes)
);
ALTER TABLE route_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE route_results FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON route_results
  USING (instance_id = current_setting('app.instance_id', true)::uuid);

CREATE TABLE route_result_history (
  route_id     uuid NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  day          date NOT NULL,
  quality      route_quality NOT NULL,
  state        route_state NOT NULL,
  matched_count int NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  instance_id  uuid NOT NULL REFERENCES instances(id),   -- denormalized for RLS
  PRIMARY KEY (route_id, day)     -- also serves as the index; no separate redundant one
);
ALTER TABLE route_result_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE route_result_history FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON route_result_history
  USING (instance_id = current_setting('app.instance_id', true)::uuid);

CREATE TABLE route_recent_matches (
  route_id        uuid NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  raw_reception_rowid bigint NOT NULL,   -- references raw_receptions.id (loose; hypertable, no FK)
  raw_reception_received_at timestamptz NOT NULL,  -- store the partition key so match lookups get chunk
                                                   -- exclusion (raw_receptions PK is (received_at, id))
  first_position  int NOT NULL,
  last_position   int NOT NULL,
  instance_id     uuid NOT NULL REFERENCES instances(id),   -- denormalized for RLS
  PRIMARY KEY (route_id, raw_reception_rowid)
);
ALTER TABLE route_recent_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE route_recent_matches FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON route_recent_matches
  USING (instance_id = current_setting('app.instance_id', true)::uuid);
-- Capped at 3/route by the worker (ROUTE_RECENT_MATCHES_LIMIT), as today.
```

### 3.8 Auth & settings (cross-referenced from component docs)

These tables are designed in their respective component docs but belong in the authoritative DDL:

```sql
-- Local password store (D12 — see auth.md)
CREATE TABLE local_users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_profile_id uuid NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  username        text NOT NULL,
  password_hash   text NOT NULL,           -- argon2id
  enabled         boolean NOT NULL DEFAULT true,
  failed_attempts smallint NOT NULL DEFAULT 0,
  locked_until    timestamptz,
  last_login      timestamptz,
  instance_id     uuid NOT NULL REFERENCES instances(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, username)
);

-- Runtime settings (D11 — see api.md)
CREATE TABLE settings (
  key         text NOT NULL,
  value       jsonb NOT NULL,
  category    text NOT NULL,              -- 'branding' | 'features' | 'tuning' | 'webhooks' | 'radio'
  description text,
  updated_by  text,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  instance_id uuid NOT NULL REFERENCES instances(id),
  PRIMARY KEY (instance_id, key)          -- per-tenant settings (one row per key PER instance)
);

-- Custom pages (D20 — moved from file-based CONTENT_HOME to DB)
CREATE TABLE custom_pages (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug         text NOT NULL,
  title        text NOT NULL,
  content      text NOT NULL DEFAULT '',   -- markdown body
  menu_order   int NOT NULL DEFAULT 100,
  enabled      boolean NOT NULL DEFAULT true,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, slug)
);

-- Precomputed Prometheus gauges (derived-state.md metrics-gauges job).
-- instance_id here is a gauge LABEL (one row per (key, instance)), NOT a tenancy guard: the
-- metrics-gauges job computes per-instance values so the platform can emit instance-labeled series.
-- Deliberately NO RLS policy on this table — a Prometheus scrape has no per-request tenant context,
-- so the /metrics endpoint reads it as the RLS-bypassing owner role and aggregates across ALL
-- instances (one series per instance_id). Access is controlled at the scrape layer
-- (network policy / basic-auth on /metrics), not by RLS.
CREATE TABLE _metrics_cache (
  key         text NOT NULL,
  instance_id uuid NOT NULL REFERENCES instances(id),
  value       double precision NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (key, instance_id)
);
```

### 3.9 What this schema drops vs today

- `packet_path_hops` table (folded into `raw_receptions.path_hashes` — D5 default).
- The CSV-text `user_profiles.roles` (→ `user_profile_roles`).
- Redundant indexes (`ix_user_profile_nodes_node_id`, `ix_route_result_history_route_id_date`).
- Every `String(36)` UUID → native `uuid`; every `String(20)` enum → native enum; every `JSON` → `JSONB`.
- All dialect branches (`if conn.dialect.name == ...`) and `batch_alter_table` wrappers.

---

## 4. Subsidiary decisions: Q-A (bigserial PK) and Q-B (single `hops jsonb` array)

Two structural sub-decisions were agreed during iteration 3 and are baked into the DDL above. They are narrower than the D-numbered decisions but worth surfacing explicitly because they shape the high-volume tables.

### Q-A — hypertable primary keys (time-column composite; `bigint IDENTITY` on `raw_receptions`)

TimescaleDB hypertables **must include the time column in the primary key**, so none of them can use a bare `uuid` PK. The four hypertables satisfy this differently, by volume and access pattern:

- **`raw_receptions`** (the highest-volume table — one row per observer reception) uses a **`bigint GENERATED ALWAYS AS IDENTITY`** second PK column: `PRIMARY KEY (received_at, id)`. A sequential 8-byte `bigint` is the cheapest possible second PK column — 8 bytes vs 16 bytes per `uuid`, on a table that grows by millions of rows/day, so the storage + index savings compound. `GENERATED ALWAYS AS IDENTITY` is the SQL-standard spelling of "let Postgres manage this sequence"; no `SERIAL` pseudo-type, no manual `nextval`. Reflected in §3.6: `raw_receptions.id bigint GENERATED ALWAYS AS IDENTITY`.
- **`event_observers`** (junction) uses a **natural composite key** `PRIMARY KEY (observed_at, event_hash, observer_node_id)` — no surrogate id at all, because `(event_hash, observer_node_id)` already identifies a reception uniquely and the junction is never FK-referenced.
- **`telemetry` and `event_logs`** (lower volume) pair the time column with a **`uuid`**: `PRIMARY KEY (received_at, id)` where `id uuid DEFAULT gen_random_uuid()`. At their volume the 8-byte saving isn't worth the FK-uniformity loss, and `event_logs` rows are occasionally referenced by id.

OLTP entity tables (`nodes`, `messages`, `advertisements`, `trace_paths`, …) keep bare `uuid` PKs — they're low-volume, and FK uniformity + natural-key usability matter more than 8 bytes.

### Q-B — single `hops jsonb` array on `trace_paths`

`trace_paths` replaces today's **parallel-array JSON antipattern** (`trace_path.py:52-59`: `path_hashes[]` + `snr_values[]` indexed in lockstep) with a single `hops jsonb` column holding `[{hash, snr}, ...]` objects.

- One array, one source of truth — no risk of the parallel arrays drifting out of length.
- `jsonb` (not `json`) so it can be GIN-indexed and queried with containment operators.
- Each hop is a self-contained object: hash + SNR + (future) any per-hop metadata, without a schema migration.
- This is reflected verbatim in §3.5: `hops jsonb, -- [{hash, snr}, ...] — kills the parallel-array antipattern (W9)`.
- This is distinct from D5 (which is about the per-*reception* `path_hashes text[]` on `raw_receptions`, used for route matching). Q-B is about the per-*trace-path event* `hops` array on the dedup'd-events `trace_paths` table.
