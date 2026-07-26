# Migration — Greenfield Provisioning & Parallel-Stack Validation

> **Related decisions:** D10 (drop SQLite), D13 (channels in export), D14 (5-day parallel window)

## Pre-rewrite: SQLite → Postgres runbook (D10)

Operators still on SQLite must migrate to Postgres **before** upgrading to the rewrite. This is a one-time operation on the **old stack** — the new stack is Postgres-only from Phase 0.

```bash
# 1. Stop the collector (pause ingest)
docker compose --profile core stop collector

# 2. Start the bundled Postgres (if not already running)
docker compose --profile postgres up -d postgres

# 3. Run the migration tool (copies SQLite → Postgres, table by table)
docker compose --profile core run --rm migrate meshcore-hub db migrate-to-postgres

# 4. Switch the backend
#    .env: DATABASE_BACKEND=postgres + DATABASE_* credentials

# 5. Restart all services
docker compose --profile core up -d

# 6. Verify: check node/message/advert counts match the SQLite backup
docker compose --profile core exec api meshcore-hub health
```

**What the tool does:** reads every table from the SQLite file (`${DATA_HOME}/collector/meshcore.db`), casts types (`String(36)` → `uuid`, `JSON` → `JSONB`, string enums → native enums), and inserts into the Postgres schema. Idempotent (`ON CONFLICT DO NOTHING`). The SQLite file is preserved as a cold backup — not deleted.

**This runbook is for the old stack only.** The rewrite's greenfield strategy (below) starts from an empty Postgres+TimescaleDB; the only data carried forward is the preserved-config export.

---

## Greenfield strategy

**No historical data migration.** The new stack starts with an empty database. The parallel-stack validation window — both stacks ingesting the same live MQTT for 3–7 days — is what gives the new stack a continuous data view at cutover. By the time DNS flips, the new stack holds a few days of fresh adverts/messages/packets and the users see no gap.

This eliminates the entire backfill problem: no MD5→SHA-256 coexistence, no parallel schemas, no `_backfill_state` checkpoints, no validation gate on historical rows, no 7-day rollback window for data. The only migration is a small **config export/import** (below).

## Preserved-config export/import

The three categories of data that cannot be repopulated from RF, plus one borderline case, carried from the old stack to the new:

| Preserved | Why it can't repopulate | Volume | Transform |
|---|---|---|---|
| **user_profiles** + **user_profile_roles** | OIDC identities; user-authored name/callsign/description/url; roles assigned by admins | tens of rows | CSV `roles` → `user_profile_roles` join table (S4); `id::uuid` cast |
| **routes** + **route_nodes** + **route_observers** | operator-defined route definitions + matched node/observer sets | tens of rows | cast; add missing UCs (no data effect) |
| **node_tags** | operator-authored key/value metadata on nodes | hundreds of rows | cast |
| **user_profile_nodes** (adoptions) | user→node adoption claims | tens of rows | cast; one-adopter UC preserved |
| **channels** | channel name + decryption key + visibility tier. Keys are operator secrets, **never transmitted over RF** — without them the ingester can't decrypt channel messages | 2–5 rows | cast; recompute `key_hash` |

### The FK-dependency: node identity stubs

Routes, tags, and adoptions all reference `nodes.id`. Since nodes themselves are **not** migrated (they repopulate from adverts), these FK references would dangle on import. Resolution: export carries **node identity stubs** (just `public_key` + any known `name`) for every node referenced by a preserved row, and the import creates stub `nodes` rows. RF adverts then enrich those stubs (name, adv_type, flags, gps, last_seen) as they arrive — the existing upsert path already handles this.

```
export carries:
  user_profiles, user_profile_roles, user_profile_nodes
  routes, route_nodes, route_observers
  node_tags
  channels                 (D13 — locked: channels are exported)
  custom_pages             (D20 — read from old CONTENT_HOME/pages/*.md via PageLoader)
  node_stubs               (distinct public_keys referenced by any of the above)
```

A node referenced only by preserved config (e.g. a tagged node that hasn't advertised recently) appears as a stub with `name` from the tag and nulls elsewhere — it fills in next time it advertises. This matches today's behaviour for rarely-seen nodes.

### The export/import commands

```bash
# On the OLD stack — dumps a portable JSON bundle (one file, ~KB–low-MB):
meshcore-hub db export-config --out config-bundle.json

# Contents (JSON, human-readable, diffable):
#   { "version": 1, "exported_at": "...", "instances": [...],
#     "user_profiles": [...], "user_profile_roles": {...},
#     "user_profile_nodes": [...], "routes": [...],
#     "route_nodes": [...], "route_observers": [...],
#     "node_tags": [...], "channels": [...], "node_stubs": [...] }

# On the NEW stack — idempotent import into the fresh schema:
meshcore-hub db import-config config-bundle.json
#   - creates the instance row
#   - inserts node_stubs (ON CONFLICT (public_key) DO NOTHING — safe to re-run)
#   - inserts user_profiles + roles, routes + nodes + observers, tags, adoptions, channels
#   - resolves FKs by public_key (stubs already exist)
#   - report: N rows imported, 0 conflicts expected on a clean DB
```

Idempotent and re-runnable: `import-config` is safe to invoke multiple times (upserts on natural keys). This lets operators iterate if they tweak a route in the old stack during the validation window and re-export.

### What is explicitly thrown away

| Discarded | Why it's safe to lose |
|---|---|
| `messages`, `advertisements`, `trace_paths`, `telemetry` | repopulate from RF within hours–days |
| `raw_packets` / `raw_receptions`, `packet_path_hops` | repopulate immediately; today's 2-day retention means there's little history anyway |
| `event_observers`, `event_logs` | repopulate from RF |
| `route_results`, `route_result_history`, `route_recent_matches` | **rebuilt by the DerivedStateWorker** from fresh `raw_receptions.path_hashes` within the first evaluation tick |
| `nodes` (all but stubs) | repopulate from adverts; stubs preserve the config-referenced ones |

## Parallel-stack validation (ship gate)

Because the target is **greenfield infrastructure**, validation is parallel-stack, not parallel-schema. Two complete stacks ingest the same live MQTT feed:

1. **Stand up the new stack** (fresh Postgres+TimescaleDB, NATS, ingester, workers, API) alongside the old, subscribed to the **same MQTT broker/topics**. Both ingest live RF traffic simultaneously.
2. **Diff harness** (below): a CLI job compares per-hour event counts and `wire_hash` coverage between the old API and the new API (match on `wire_hash`, not `event_hash` — see the note below). Any divergence blocks cutover.
3. **Validate for N days** (3–7) until confidence is high — the new stack has now repopulated a few days of fresh data, so there's no missing-history gap at cutover.
4. **Cut over** DNS / reverse-proxy / MQTT subscription exclusivity to the new stack. The old stack stops ingesting.
5. **Decommission** the old stack once the new one has served live traffic cleanly for a grace period.

No historical data migration is needed — the few days of parallel ingestion give the new stack enough live data that users see a continuous view.

### Diff harness (`meshcore-hub admin diff-stacks`)

A CLI command that queries both stacks' APIs and reports divergence. Run manually or via cron during the validation window.

```bash
meshcore-hub admin diff-stacks \
  --old-api http://old-stack:8000 \
  --new-api http://new-stack:8000 \
  --window 24h \
  --api-key <read-key>
```

> **Match on `wire_hash`, not `event_hash`.** The two stacks compute the content dedup hash with
> different algorithms (old = MD5, new = SHA-256 truncated), so the *same* event has a different
> `event_hash` in each stack — a coverage check keyed on `event_hash` would always report 0%. The
> LetsMesh on-air `wire_hash` is identical in both stacks, so it is the correct join key for verifying the
> new pipeline decoded the same packets.

**What it compares (per hour bucket, per event type):**

| Check | Query | Pass condition |
|---|---|---|
| **Event count parity** | `GET /api/v1/messages?since=<hour>&until=<hour>` (and adverts, packets) — compare `total` | Counts match within ±2 (tolerance for race at hour boundaries) |
| **Hash coverage** | Sample 100 `wire_hash` values from the old stack's hour; verify each exists in the new stack (`GET /api/v1/packet-groups/<wire_hash>`) | 100% coverage |
| **Observer parity** | For the sampled events, compare observer counts (`event_observers` junction) | Counts match exactly |
| **Node count** | `GET /api/v1/nodes` — compare `total` | Within ±5 (nodes appear/disappear on advert timing) |

**Output:** a table per hour bucket with per-event-type counts, divergence flags, and the sampled hash coverage. Exit code 0 = clean, 1 = divergence found.

```
Hour                  messages  adverts  packets  nodes  hash_cov  observers  status
2026-07-25T00:00      142/142   89/89    1204/1204  67/65  100/100   match      OK
2026-07-25T01:00      156/155   94/94    1387/1387  67/67  100/100   match      DIVERGENCE (messages: 156 vs 155)
```

**Cutover gate:** 3 consecutive days of exit-code-0 runs (D14). The harness is a validation tool, not a runtime component — it's removed from the image after cutover.
