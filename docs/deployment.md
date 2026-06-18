# Deployment

This document covers production deployments of MeshCore Hub: reverse-proxy setup, multi-instance routing, API scaling, and the optional Redis response cache. For the full environment-variable reference, see [configuration.md](configuration.md).

## Production Setup

For production deployments, use `docker-compose.prod.yml` which connects services to an external proxy network. No ports are exposed directly — all traffic goes through your reverse proxy.

**Prerequisites:**

1. A reverse proxy (Nginx Proxy Manager, Caddy, Traefik, etc.)
2. Docker network for proxy communication

**Steps:**

```bash
# Create proxy network (once)
docker network create proxy-net

# Download compose files and config
mkdir meshcore-hub && cd meshcore-hub
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/refs/heads/main/docker-compose.yml
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/refs/heads/main/docker-compose.prod.yml
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/refs/heads/main/.env.example
cp .env.example .env
# Edit .env: set COMPOSE_PROJECT_NAME, MQTT credentials, API keys, etc.

# Start core services
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile core up -d

# Or include local MQTT broker
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile mqtt --profile core up -d

# Or include packet capture on the same host
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile mqtt --profile core --profile observer up -d
```

Configure your reverse proxy to forward to the containers:

| Service        | Container                     | Port | Path                             |
| -------------- | ----------------------------- | ---- | -------------------------------- |
| Web Dashboard  | `{COMPOSE_PROJECT_NAME}-web`  | 8080 | `/`                              |
| API            | `{COMPOSE_PROJECT_NAME}-api`  | 8000 | `/api`, `/metrics`, `/health`    |
| MQTT WebSocket | `{COMPOSE_PROJECT_NAME}-mqtt` | 1883 | `/` (only if using local broker) |

> **Important:** Do not host under a subpath (e.g., `/meshcore`). Proxy at `/`.

### Reverse Proxy

MeshCore Hub is designed to run behind a reverse proxy in production. A Traefik override file is provided with pre-configured labels:

```bash
# Download the Traefik override
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/refs/heads/main/docker-compose.traefik.yml

# Set your domain in .env
echo "TRAEFIK_DOMAIN=meshcore.example.com" >> .env

# Start with Traefik labels
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.traefik.yml --profile core up -d
```

This routes the web dashboard and API to `TRAEFIK_DOMAIN` with automatic TLS.

### Multi-Instance Deployments

To run multiple Hub instances (e.g., production + staging) on the same Docker host, set `TRAEFIK_PRIORITY` to control which router wins when domains overlap. Higher values are matched first:

```bash
# Production (.env)
COMPOSE_PROJECT_NAME=hub
TRAEFIK_DOMAIN=example.com
TRAEFIK_PRIORITY=10

# Staging (.env) — separate directory with its own config
COMPOSE_PROJECT_NAME=hub-beta
TRAEFIK_DOMAIN=beta.example.com
TRAEFIK_PRIORITY=20
```

This ensures `beta.example.com` (priority 20) is matched before the production wildcard `*.example.com` (priority 10). For other services on the same network (e.g., an MQTT broker at `mqtt.example.com`), use an even higher priority (e.g., 30).

> **Shared Postgres cluster:** the setup above runs each instance in its own directory with its own volumes (the default SQLite path). To instead run several instances (e.g. `prod` + `stg`) against **one** PostgreSQL cluster — isolated via a per-instance schema (`search_path`) — see [database.md](database.md#schema-per-instance-search_path).

## Scaling the API

The API is read-mostly and holds no per-process state — the response cache lives in Redis and authentication is stateless — so it scales across multiple worker processes. Set `API_WORKERS` to run more than one worker in a single container:

```bash
# .env
API_WORKERS=4
```

Each worker is an independent process sharing one listening socket, so the kernel balances connections across them and CPU-bound work (JSON serialisation, validation) spreads over multiple cores. Workers read their configuration from **environment variables** (CLI flags are not propagated to forked workers), which is how Docker Compose already supplies config. Enabling Redis (`REDIS_ENABLED=true`) is recommended so all workers share one cache.

Pick a worker count around the number of CPU cores available to the container; start with `2`–`4` and measure under realistic load.

**SQLite caveat:** all workers share one SQLite file on the same host (WAL mode lets concurrent readers coexist with the single writer), but writes do not scale and this does not extend across hosts. To scale the API across hosts, switch to PostgreSQL (`DATABASE_BACKEND=postgres`) — the API requires no code changes. See [database.md](database.md) for backend setup and the SQLite → Postgres migration runbook.

> Prefer `API_WORKERS` over running multiple `api` containers (`--scale api=N`): the `api` service uses a fixed `container_name`, and one process-managed container per stack keeps logs, health checks, and monitoring simple.

## Redis Caching

Optional Redis-backed caching for API responses. When disabled or unavailable, the API queries the database directly.

**Docker:** Redis is included in the `cache` profile. Disabled by default — set `REDIS_ENABLED=true` to enable.

```bash
docker compose --profile cache up    # Start with bundled Redis
docker compose --profile core up     # Start without Redis
```

**Bare-metal:** Install Redis separately, then set `REDIS_ENABLED=true` and `REDIS_HOST=localhost`.

**Multi-instance:** Use different `REDIS_KEY_PREFIX` values per instance to share one Redis without key collisions.

For the full list of `REDIS_*` environment variables, see [configuration.md → Caching](configuration.md#caching).
