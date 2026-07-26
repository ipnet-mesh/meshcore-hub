# Infrastructure

> **Related decisions:** D1 (TimescaleDB for history), D4 (NATS JetStream for ingest + fan-out), D10 (drop SQLite), D14 (5-day parallel-stack window)
>
> **Source:** Restructured from `REWRITE.md` §5.2 (target topology), §6.1–6.2 (store breakdown + rationale),
> §7.2 (NATS JetStream), §11.1 (observability), §18.5 (provisioning sequence).

---

## 1. Target topology

```mermaid
flowchart TB
    subgraph Edge
        PCAP[meshcore-packet-capture<br/>per observer]
    end
    PCAP -->|MQTT WSS| MQTT[(MQTT Broker)]

    subgraph "Ingest plane (write-optimized)"
        INGEST[MqttIngester<br/>decode + normalize + produce<br/>no DB writes]
    end
    MQTT --> INGEST
    INGEST -->|produce envelope| NATS[(NATS JetStream<br/>durable ingest stream)]

    subgraph "Write workers (scale horizontally, consumer group)"
        W1[IngestWorker]
        W2[IngestWorker]
        W3[IngestWorker]
    end
    NATS --> W1 & W2 & W3

    W1 & W2 & W3 --> PG[(PostgreSQL + TimescaleDB<br/>entities + dedup'd events<br/>+ hypertables + CAGGs)]
    W1 & W2 & W3 -.->|raw bytes, only if D8 on| OBJ[BlobStore<br/>local / MinIO / S3]

    W1 & W2 & W3 -->|after commit: events.new| NATSBUS[(NATS core<br/>realtime fan-out)]
    DERIVED[DerivedStateWorker<br/>single scheduler] --> PG

    subgraph "Read plane (query-optimized)"
        API[API: Fastify<br/>Drizzle ORM + JWT verify]
        WEB[Web: static shell +<br/>OIDC + JWT issuer]
    end
    PG --> API
    NATSBUS -.->|SSE| API
    WEB -->|signed JWT| API
    REDIS[(Redis<br/>optional, response cache)] -.-> API
    API --> SPA[React SPA<br/>generated client]

    classDef external fill:none,stroke:#999,stroke-dasharray:4 3;
    classDef datastore fill:#e8f5e9,stroke:#388e3c;
    classDef deferred fill:#fff3e0,stroke:#f57c00,stroke-dasharray:4 3;
    class PCAP,MQTT,SPA external;
    class NATS,PG,NATSBUS,REDIS datastore;
    class OBJ deferred;
```

### Structural changes vs today

- **NATS JetStream as the durable queue** between MQTT receipt and DB write (W1, P1). NATS core (non-durable) doubles as the realtime fan-out bus (D4 locked).
- **Hypertables in the same Postgres** for the high-volume append-only streams (W2, W3, W7) — TimescaleDB, not a separate store (D1 locked).
- **Raw bytes Stay in-DB (compressed) by default** — object storage is behind a `BlobStore` interface and only activated if D8 measurement demands it.
- **One derived-state worker** instead of 6 threads (P3, W6).
- **Async API** end-to-end (A5).
- **Static shell + JWT** instead of inlined-config + header injection (F5, S1).
- **Redis narrowed** to optional API response cache — no longer on the ingest or fan-out paths.

None of these services are exotic — they're all commodity infrastructure. The question is how many to adopt; the locked decision set (D1, D4, D10, D14) is the answer.

---

## 2. Store breakdown (locked)

| Store | Workload | Holds | Technology |
|---|---|---|---|
| **PostgreSQL + TimescaleDB** (primary) | transactional + hypertables + continuous aggregates | entities, dedup'd events, route-health derived tables; `raw_receptions`/`telemetry`/`event_logs`/`event_observers` as hypertables | **Postgres 17 + TimescaleDB** (D1 locked) |
| **NATS JetStream** | durable queue + pub/sub fan-out | ingest envelopes (MQTT→worker); realtime event notifications (worker→SSE) | **NATS 2.10+** (D4 locked) |
| **Redis** (optional, narrowed) | ephemeral API response cache | ETag/304 store, role-scoped response bodies | **Redis 7/8** (D4 narrows role — no longer on the ingest path) |
| **Blob storage** (deferred) | immutable raw bytes — *only if D8 measurement demands it* | on-air `raw_hex` per packet, raw LPP bytes | Behind a `BlobStore` interface: local-volume (default), MinIO, or S3 |
| **MQTT broker** (already external) | edge ingest | unchanged | `meshcore-mqtt-broker` |

---

## 3. Why Postgres + TimescaleDB (locked D1)

The single highest-leverage change. Today, one Postgres/SQLite holds *everything*, and the high-volume tables are the ones that hurt. Splitting workloads lets each store do what it's good at — and the cheapest way to do that here is to keep one Postgres, add the TimescaleDB extension, and use hypertables + continuous aggregates for the time-series workload.

- Same process, same connection pool, same transaction semantics — no two-phase anything.
- Hypertables give automatic time partitioning; compression policies replace the 2-day retention ceiling (keep weeks/months of raw packets at similar disk cost).
- **Continuous aggregates** are the right tool for the *dashboard* time-bucketing workloads (daily counts, breakdowns, node-count history) — incremental refresh, query the precomputed buckets instead of fan-out COUNTs.
- One backup, one monitoring target, one set of credentials. TimescaleDB community edition (Apache-2.0) covers everything we need.

### Why drop SQLite (locked D10)

Phase 0 starts Postgres-only. Removing SQLite:

- Eliminates every `if conn.dialect.name ==` branch.
- Removes the `batch_alter_table` wrapper.
- Removes the `postgresql_include` conditional.
- Removes the dual-driver `[postgres]` extra.
- Unblocks native `uuid`, native enums, and `JSONB` unconditionally.

Existing operators migrate via the `db migrate-to-postgres` runbook before upgrading.

---

## 4. NATS JetStream (locked D4)

NATS JetStream owns two roles in the target architecture:

1. **Durable ingest stream** — a single platform-wide `INGEST` stream capturing `meshcore.ingest.>` (per-instance subject tokens `meshcore.ingest.<inst>.<feed>`). The MqttIngester produces decoded envelopes; the shared `IngestWorker` consumer group reads them. One stream (not one-per-instance) so the Phase 7 wildcard consumer group works — see [D4](../decisions/D04-nats-jetstream-ingest.md) (F8). JetStream gives at-least-once delivery, disk persistence, and **server-side dedup** via the `Nats-Msg-Id` header (packet `wire_hash`) within a configurable duplicate window — so MQTT redelivery does not double-process.
2. **Realtime fan-out bus** (`events.new.<instance_id>`) — workers publish a small "new event" notification after commit; the API's SSE endpoint subscribes and pushes to clients.

### Why NATS over the alternatives

| Option | Verdict |
|---|---|
| **NATS JetStream** | **Chosen.** Single binary, lightweight, built-in stream persistence + dedup + consumer groups + core (non-durable) pub/sub for fan-out. One tool covers both roles. |
| Redis Streams | Rejected — would force Redis onto the critical ingest path and couldn't double as the fan-out bus as cleanly. Redis stays optional, API-cache-only. |
| Kafka | Rejected — operationally heavy for this scale; NATS covers the same guarantees at a fraction of the ops cost. |
| Postgres queue | Rejected — puts more load on the DB we're trying to protect. |

### Stream configuration

The default Compose stack gains a `nats` service with a JetStream persistence volume. Operators of the existing bundled-Redis cache keep Redis; the ingest path no longer touches it. One `INGEST` stream is created at provisioning (subject `meshcore.ingest.>`) with one durable consumer `workers` that all IngestWorker replicas bind to.

- `duplicate_window = 5m` — server-side dedup on `Nats-Msg-Id` = packet `wire_hash` (tenant-prefixed in multi-tenant mode).
- `max_age = 7d` — replay window for worker restarts.
- `storage = file`.
- `retention = limits`.

---

## 5. Observability

- **Structured logs** (JSON) with `instance_id`, `event_hash`, `observer` correlation fields.
- **Prometheus metrics** kept, but the "one COUNT per role string" pattern (A7) replaced by precomputed gauges updated by the worker.

### Alerting rules (recommended defaults)

| Alert | Expression | Severity | Notes |
|---|---|---|---|
| **IngestWorker stalled** | `rate(ingest_worker_batches_total[5m]) == 0` for 10m | critical | No batches processed — MQTT backlog growing |
| **NATS stream backlog** | `jetstream_stream_msgs > 10000` for 5m | warning | Consumers falling behind |
| **DerivedStateWorker job overdue** | `derived_job_last_success_timestamp` older than `3 × interval` | warning | A job hasn't run in 3× its cadence |
| **CAGG refresh stale** | `cagg_refresh_lag_seconds > 600` | warning | Dashboard data >10 min stale |
| **Postgres connection pool exhausted** | `pg_stat_activity.count / pool_max > 0.9` for 5m | warning | Pool nearing capacity |
| **Disk usage** | `node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.15` | critical | <15% free on the data volume |
| **API error rate** | `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05` | warning | >5% 5xx rate |

These are starting points — operators tune thresholds for their deployment size. Exported via `/metrics` on the API and worker processes.

---

## 6. Services, Docker & development workflow

### Service inventory

The stack is one image (`meshcore-hub`) with multiple commands, plus four infrastructure services.

**Infrastructure (third-party images):**

| Service | Image | Ports | Required | Notes |
|---|---|---|---|---|
| **postgres** | `timescale/timescaledb:latest-pg17` | 5432 | Yes | TimescaleDB extension pre-installed |
| **nats** | `nats:2.10-alpine` | 4222 (client), 8222 (monitor) | Yes | `--jetstream --store_dir /data` |
| **redis** | `redis:8-alpine` | 6379 | **No** | Optional API response cache; stack works without it (no caching) |
| **mqtt** | `meshcore-mqtt-broker` | 1883, 9001 (WSS) | Yes* | *Or an external broker (`MQTT_HOST` env) |

**Application (meshcore-hub image, one command per service):**

| Service | Command | Ports | Depends on | Replicas | Notes |
|---|---|---|---|---|---|
| **migrate** | `db upgrade` | — | postgres | 1 (one-shot) | Runs drizzle-kit + raw SQL migrations, exits 0 |
| **ingester** | `ingester run` | — | nats, mqtt | 1 | MqttIngester: decode + produce to NATS. No DB writes. |
| **worker** | `worker run` | — | postgres, nats | 2 | IngestWorker: batched DB writes. Consumer group scales horizontally. |
| **derived** | `derived run` | — | postgres | 2 | DerivedStateWorker: periodic jobs. HA via advisory locks (D16). |
| **webhook** | `webhook run` | — | nats | 1 | WebhookWorker: NATS subscriber, HTTP dispatch. Optional. |
| **api** | `api run` | 3000 | postgres, nats, redis? | 1 | Fastify API. `/metrics` endpoint for Prometheus. |
| **web** | `web run` | 8080 | api | 1 | Fastify web tier: static shell, JWT issuer, OIDC, SSE proxy. |

**Minimum viable deployment:** postgres + nats + mqtt + ingester + worker + derived + api + web (8 services). Redis and webhook are optional.

### Dockerfile

Multi-stage Node build. Single image, all commands.

```dockerfile
# ---- Build stage ----
FROM node:22-alpine AS build
WORKDIR /app

# Backend deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Frontend build
COPY spa-react/ ./spa-react/
RUN npm run build --prefix spa-react    # -> static/dist/ + assets.json

# Backend compile
COPY src/ ./src/
COPY tsconfig.json drizzle.config.ts ./
RUN npx tsc                             # -> dist/

# ---- Runtime stage ----
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/node_modules/ ./node_modules/
COPY --from=build /app/dist/ ./dist/
COPY --from=build /app/spa-react/static/dist/ ./static/dist/
COPY --from=build /app/spa-react/static/assets.json ./static/assets.json
COPY package.json ./

# CLI entrypoint (commander)
ENTRYPOINT ["node", "dist/cli.js"]
CMD ["--help"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node dist/cli.js health || exit 1
```

**Image size target:** <200 MB (node:22-alpine ~130 MB + deps ~50 MB + app ~20 MB). No Python runtime, no native build tools (argon2 ships prebuilt binaries for linux/amd64 + linux/arm64).

### Development workflow

D22 (Node/TS) fundamentally changes the dev loop. **Infrastructure runs in Docker; the application runs on the host with hot reload.** No Docker rebuild to test a backend change.

```bash
# 1. Start infrastructure only (postgres, nats, redis, mqtt)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 2. Run migrations
npx drizzle-kit migrate

# 3. Start the backend services (one terminal each, or a process manager)
npx tsx watch src/cli.ts ingester run    # MqttIngester — restarts on file change
npx tsx watch src/cli.ts worker run      # IngestWorker
npx tsx watch src/cli.ts derived run     # DerivedStateWorker
npx tsx watch src/cli.ts api run         # API (port 3000)
npx tsx watch src/cli.ts web run         # Web tier (port 8080)

# 4. Start the frontend dev server (separate terminal)
npm run dev --prefix spa-react           # Vite HMR (port 5173, proxies /api -> 3000)

# 5. Run tests
npx vitest                               # backend + frontend (one runner, D22)
```

**What changed vs the Python stack:**
- No `docker compose build` to test a code change — `tsx watch` restarts in <1s.
- No venv/pip — `npm install` once, `node_modules` is the environment.
- Frontend and backend share one test runner (vitest), one `tsconfig`, one linter.
- The Dockerfile is a production concern, not a dev concern.

**Dev compose file (`docker-compose.dev.yml`):**

```yaml
# Infrastructure only — app services run on the host
services:
  postgres:
    image: timescale/timescaledb:latest-pg17
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: meshcore
      POSTGRES_PASSWORD: meshcore
      POSTGRES_DB: meshcore
    volumes: [pg_data_dev:/var/lib/postgresql/data]

  nats:
    image: nats:2.10-alpine
    command: --jetstream --store_dir /data
    ports: ["4222:4222", "8222:8222"]
    volumes: [nats_data_dev:/data]

  redis:
    image: redis:8-alpine
    ports: ["6379:6379"]

  # MQTT broker — omit if using an external broker
  mqtt:
    image: meshcore-mqtt-broker
    ports: ["1883:1883", "9001:9001"]

volumes:
  pg_data_dev:
  nats_data_dev:
```

**Dev `.env` (host-side, read by `tsx`):**

```bash
DATABASE_URL=postgres://meshcore:meshcore@localhost:5432/meshcore
NATS_URL=nats://localhost:4222
REDIS_URL=redis://localhost:6379
MQTT_HOST=localhost
MQTT_PORT=1883
JWT_SESSION_SECRET=dev-secret-not-for-production
LOG_LEVEL=debug
```

### Production Compose

```yaml
# docker-compose.yml (core profile)
services:
  postgres:
    image: timescale/timescaledb:latest-pg17
    profiles: [core]
    environment:
      POSTGRES_USER: ${DATABASE_USER}
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
      POSTGRES_DB: ${DATABASE_NAME}
    volumes: [pg_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DATABASE_USER}"]
      interval: 10s
      retries: 5

  nats:
    image: nats:2.10-alpine
    profiles: [core]
    command: --jetstream --store_dir /data
    volumes: [nats_data:/data]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8222/healthz"]
      interval: 10s
      retries: 5

  redis:
    image: redis:8-alpine
    profiles: [core]

  migrate:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: db upgrade
    restart: "no"
    depends_on:
      postgres: { condition: service_healthy }

  ingester:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: ingester run
    depends_on:
      postgres: { condition: service_healthy }
      nats: { condition: service_healthy }
    restart: unless-stopped
    stop_grace_period: 30s

  worker:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: worker run
    depends_on:
      postgres: { condition: service_healthy }
      nats: { condition: service_healthy }
    deploy:
      replicas: 2
    restart: unless-stopped
    stop_grace_period: 30s

  derived:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: derived run
    depends_on:
      postgres: { condition: service_healthy }
    deploy:
      replicas: 2
    restart: unless-stopped
    stop_grace_period: 60s    # let long-running jobs finish

  webhook:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: webhook run
    depends_on:
      nats: { condition: service_healthy }
    restart: unless-stopped
    stop_grace_period: 15s

  api:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: api run
    depends_on:
      postgres: { condition: service_healthy }
      nats: { condition: service_healthy }
    restart: unless-stopped
    stop_grace_period: 15s

  web:
    image: meshcore-hub:${IMAGE_VERSION:-latest}
    profiles: [core]
    command: web run
    depends_on: [api]
    ports: ["8080:8080"]
    restart: unless-stopped
    stop_grace_period: 15s

volumes:
  pg_data:
  nats_data:
```

**Multi-tenant (Phase 7):** no additional services. The shared worker pool ([multi-tenancy.md §9](multi-tenancy.md#9-shared-worker-pool-dynamic-tenant-discovery)) handles all tenants. The only additions are the `PLATFORM_DOMAIN` env var and the wildcard DNS/TLS config on the reverse proxy.

### Tier-1 env vars (bootstrap — the complete list)

Needed to start the process; can't be read from the DB. ~20 vars. Everything else is Tier-2 (DB) or Tier-3 (entity).

| Var | Required | Default | Service(s) |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | all (Postgres connection) |
| `NATS_URL` | Yes | `nats://localhost:4222` | ingester, worker, webhook, api |
| `MQTT_HOST` | Yes | — | ingester |
| `MQTT_PORT` | No | `1883` | ingester |
| `MQTT_USERNAME` | No | — | ingester |
| `MQTT_PASSWORD` | No | — | ingester |
| `MQTT_TLS` | No | `false` | ingester |
| `REDIS_URL` | No | — (disabled) | api |
| `JWT_SESSION_SECRET` | Yes | — | web, api — **platform** JWT + session-cookie signing key, shared across all tenants (the trust anchor; cannot be per-tenant) |
| `OIDC_CLIENT_ID` | No | — | web — platform-default IdP (fallback when a tenant has no own config in `tenant_oidc_configs`) |
| `OIDC_CLIENT_SECRET` | No | — | web — platform-default IdP secret |
| `OIDC_DISCOVERY_URL` | No | — | web — platform-default IdP discovery URL |
| `AUTH_MODE` | No | `hybrid` | web — platform-default `local`/`oidc`/`hybrid`; per-tenant override in `tenant_oidc_configs.auth_mode` |
| `API_HOST` | No | `0.0.0.0` | api |
| `API_PORT` | No | `3000` | api |
| `WEB_HOST` | No | `0.0.0.0` | web |
| `WEB_PORT` | No | `8080` | web |
| `LOG_LEVEL` | No | `info` | all |
| `NETWORK_NAME` | No | `MeshCore Network` | seed only (then `branding.network_name`) |
| `DEFAULT_INSTANCE_ID` | No | — | all (single-tenant fallback, Phase 7) |
| `PLATFORM_DOMAIN` | Phase 7 | — | web (wildcard subdomain registration) |
| `ADMIN_USERNAME` | No | — | web (headless admin bootstrap) |
| `ADMIN_PASSWORD` | No | — | web |
| `FIELD_ENCRYPTION_KEY` | Phase 7 | — | api (encrypts `tenant_oidc_configs.client_secret`) |
| `BLOB_STORE_TYPE` | No | — (noop) | worker (D8: `local`/`s3` to activate) |
| `BLOB_STORE_PATH` | No | — | worker (`BLOB_STORE_TYPE=local`) |
| `BLOB_STORE_ENDPOINT` | No | — | worker (`BLOB_STORE_TYPE=s3`) |
| `BLOB_STORE_BUCKET` | No | — | worker |

**Platform-scope vs tenant-scope auth config.** `JWT_SESSION_SECRET` is genuinely platform-wide: one key signs the JWT/session cookie for *every* tenant, and the API trusts the `instance_id` claim because the platform signed it (it cannot be per-tenant — the API learns the tenant *from* the JWT this key signs). The `OIDC_CLIENT_*` and `AUTH_MODE` vars are **platform defaults only**: in multi-tenant mode (D21, Phase 7) each tenant overrides them via `tenant_oidc_configs` (their own IdP + `auth_mode`), resolved per hostname; the env vars are the fallback when a tenant hasn't configured their own (multi-tenancy.md §6).

### CLI commands

Run via `docker compose run --rm <service>` in production, or `npx tsx src/cli.ts` in development.

| Command | Purpose |
|---|---|
| `db upgrade` | Apply migrations (the `migrate` service) |
| `db export-config --out <file>` | Export preserved config (old stack) |
| `db import-config <file>` | Import preserved config (new stack) |
| `db migrate-to-postgres` | SQLite to Postgres migration (old stack, D10) |
| `admin create-user --username <u> --role <r>` | Headless admin bootstrap |
| `admin create-instance --name <n> --hostname <h>` | Tenant creation (CLI fallback, Phase 7) |
| `admin delete-instance --name <n>` | Soft-delete tenant |
| `admin undelete-instance --name <n>` | Reverse soft-delete |
| `admin purge-instance --name <n>` | Hard-delete tenant (multi-table) |
| `admin list-instances` | List tenants (active + deleted) |
| `admin backfill-blobs` | D8: migrate `raw_hex` to object storage |
| `admin diff-stacks --old-api <url> --new-api <url>` | Parallel-stack validation (D14) |
| `health` | Docker healthcheck |
| `settings reset --category=<cat>` | Escape hatch for bad settings |
| `cleanup --now` | Force-run the retention job |
| `routes --rebuild` | Force-run the route evaluator |

### Graceful shutdown

Every service handles `SIGTERM` (Docker `stop`) with a drain-then-exit sequence. `stop_grace_period: 30s` in Compose; after that, `SIGKILL`.

| Service | On SIGTERM |
|---|---|
| **MqttIngester** | Stop accepting new MQTT messages (`client.end()`). Flush any in-flight envelope to NATS. Exit 0. |
| **IngestWorker** | Stop calling `sub.fetch()`. Finish the current batch (commit + publish + ack). Drain the NATS subscription (`sub.drain()`). Exit 0. |
| **DerivedStateWorker** | Stop the scheduler loop. If a job is running, let it finish (advisory lock releases on commit/rollback). Exit 0. |
| **WebhookWorker** | Drain the NATS subscription. Finish in-flight HTTP dispatches (with a 10s timeout per request). Exit 0. |
| **API** | Stop accepting new connections. Drain in-flight requests (Fastify `close()` with a 10s timeout). Exit 0. |
| **Web** | Same as API (Fastify). |

**Key invariant:** the IngestWorker never acks a message it hasn't committed. A SIGTERM mid-batch means the un-acked messages are redelivered by JetStream to another worker (or the same worker after restart). No data loss, possible duplicate processing (idempotent — `ON CONFLICT DO NOTHING`).

### Backup & restore

| Store | Backup | Restore | RPO |
|---|---|---|---|
| **Postgres+TimescaleDB** | `pg_basebackup` (daily) + WAL archiving (continuous) to a volume or S3. `pg_dump` weekly for a logical backup. | `pg_restore` from base backup + WAL replay. Or `pg_restore` from logical dump. | 5 min (WAL) |
| **NATS JetStream** | File-backed persistence volume. Snapshot the volume alongside the Postgres backup. | Restore the volume. JetStream replays from the stream's `max_age` window (7d). | 0 (durable) |
| **Redis** | Not backed up. Ephemeral cache — rebuilds on restart. | N/A (cold start = cache misses until warm). | N/A |
| **BlobStore** (if D8 on) | Local volume: snapshot alongside Postgres. S3/MinIO: provider-managed versioning. | Restore volume or re-upload from S3. | Provider-dependent |

**What's recoverable without backups:** all RF-repopulatable data (messages, adverts, packets, telemetry, event_logs) rebuilds from live traffic within hours. The `db export-config` bundle (preserved config) is the critical artifact — operators should store it alongside their Postgres backups.

**Multi-tenant:** one Postgres cluster = one backup covers all tenants. Per-tenant restore is possible via RLS-scoped `pg_dump --where="instance_id='<uuid>'"` but is a Phase 7+ refinement.

---

## 7. Provisioning sequence (greenfield)

The end-to-end "stand up the new stack" order. This is a **greenfield** deployment — fresh Postgres+TimescaleDB, NATS, new schema; no historical data migration. The few days of parallel-stack validation ([migration.md](migration.md#parallel-stack-validation-ship-gate); D14 locked at 5 days) give the new stack a continuous data view at cutover.

1. **D5 benchmark** runs, decision recorded, data-model.md §3 schema frozen.
2. **New infrastructure provisioned:** Postgres 17 + TimescaleDB extension, NATS with JetStream persistence volume, (optional Redis for API cache).
3. **`drizzle-kit migrate`** on the fresh DB — creates the full schema (entities, hypertables, CAGGs, RLS policies, retention policies).
4. **`db import-config config-bundle.json`** — loads the preserved config (user_profiles + roles, routes + nodes + observers, node_tags, adoptions, channels) + node identity stubs.
5. **Bring up services:** MqttIngester + IngestWorkers + DerivedStateWorker + API + Web.
6. **Parallel-stack validation** begins — both stacks ingest live MQTT.
7. **Validate for 3–7 days** (D14: 5 days): diff harness confirms parity; CAGGs populate; DerivedStateWorker rebuilds route health.
8. **Cut over** DNS / MQTT exclusivity to the new stack.
9. **Decommission** the old stack after the grace period.

Steps 6–9 are where D14 (5-day parallel-stack window) is exercised. The diff harness compares per-hour event counts and `wire_hash` coverage between the old API and the new API — it matches on the on-air `wire_hash` (identical in both stacks), **not** `event_hash`, which differs because the old stack hashes with MD5 and the new with SHA-256 (see migration.md → diff harness). Any divergence blocks cutover.
