# Config Source Guide

How to extract the complete environment variable inventory from Python source code.

## Source Files

These files contain the authoritative definition of all environment variables consumed by the MeshCore Hub application. Check them in this order:

### 1. Pydantic Settings — `src/meshcore_hub/common/config.py`

**Primary source of truth.** Contains four Settings classes that define env vars via Pydantic fields:

| Class | Inherits | Component | Env Vars |
|-------|----------|-----------|----------|
| `CommonSettings` | `BaseSettings` | All services | Base config (MQTT, logging, paths) |
| `CollectorSettings` | `CommonSettings` | Collector | Database, webhooks, retention, cleanup, channel keys |
| `APISettings` | `CommonSettings` | API server | Host, port, auth keys, metrics |
| `WebSettings` | `CommonSettings` | Web dashboard | Host, port, theme, locale, features, network info |

#### Extraction Method

Read each class and extract:
- **Field name** — the Python attribute name (e.g., `mqtt_host`)
- **Env var name** — the uppercased field name (e.g., `MQTT_HOST`), unless explicitly overridden via `Field(alias=...)` or `alias` in `model_config`
- **Default value** — the `= value` in the field declaration, or `Field(default=...)`
- **Type** — the type annotation (e.g., `str`, `int`, `bool`, `Optional[str]`, constrained types)
- **Description** — the `Field(description=...)` or docstring, if any
- **Constraints** — `Field(ge=1, le=100)`, `min_length`, `max_length`, etc.

#### Pydantic-to-Env Mapping Rules

- Field `mqtt_host` → env var `MQTT_HOST` (automatic uppercasing)
- Field `api_base_url` → env var `API_BASE_URL`
- `Optional[str]` fields with `None` default → env var is optional, no default
- `bool` fields use Pydantic's built-in coercion: `"true"`, `"1"`, `"yes"` → `True`; `"false"`, `"0"`, `"no"` → `False`
- Enum fields (e.g., `LogLevel`, `MQTTTransport`) accept their member values as strings

#### Computed Properties

Some settings have computed properties (e.g., `database_url` falls back to `sqlite:///{DATA_HOME}/collector/meshcore.db`). These should be documented as having a computed default.

#### Settings Inheritance

`CollectorSettings`, `APISettings`, and `WebSettings` all inherit from `CommonSettings`. The shared env vars (`MQTT_*`, `LOG_LEVEL`, `DATA_HOME`, etc.) should appear once under "Common Settings" in documentation, not repeated per component.

### 2. Click CLI `envvar` — CLI Entry Points

These files define Click commands that accept env var overrides via `envvar=` or `envvar=[...]`:

| File | CLI Group | Key Env Vars |
|------|-----------|--------------|
| `src/meshcore_hub/__main__.py` | Root CLI | `DATA_HOME`, `DATABASE_URL` (also sets into `os.environ` for Alembic) |
| `src/meshcore_hub/collector/cli.py` | `collector` | `DATA_HOME`, `DATABASE_URL`, `SEED_HOME` |
| `src/meshcore_hub/api/cli.py` | `api` | `DATA_HOME`, `DATABASE_URL`, `CORS_ORIGINS`, `MQTT_PREFIX`/`MQTT_TOPIC_PREFIX` |
| `src/meshcore_hub/web/cli.py` | `web` | `DATA_HOME`, `API_BASE_URL` |

#### Extraction Method

Grep for `envvar=` in each file. Each `envvar=` parameter maps a Click option to an environment variable.

#### Key Patterns

- **Single envvar:** `envvar="CORS_ORIGINS"` — maps `--cors-origins` flag to `CORS_ORIGINS` env var
- **Multiple envvars (alias):** `envvar=["MQTT_PREFIX", "MQTT_TOPIC_PREFIX"]` — first is primary, rest are backward-compat aliases
- **Setting os.environ:** `__main__.py` sets `os.environ["DATABASE_URL"]` from CLI args so Alembic can pick it up. This is a pass-through, not a new env var.

#### Edge Case: `CORS_ORIGINS`

`CORS_ORIGINS` exists only as a Click `envvar` in `api/cli.py` — it has **no** Pydantic Settings field. It should still be documented as an env var consumed by the API component, but note that it only works when launched via the CLI (not when running with `--reload` which bypasses Click).

### 3. Direct `os.getenv()` / `os.environ` Access

Some code bypasses Pydantic Settings entirely and reads env vars directly:

| File | Env Var | Default | Purpose |
|------|---------|---------|---------|
| `src/meshcore_hub/web/app.py` | `COLLECTOR_CHANNEL_KEYS` | `None` | Reads channel keys for web UI label building |
| `src/meshcore_hub/web/app.py` | `COLLECTOR_INCLUDE_TEST_CHANNEL` | `"false"` | Reads test channel flag for web UI |
| `src/meshcore_hub/common/health.py` | `HEALTH_DIR` | `/tmp/meshcore-hub` | Health status file directory |
| `src/meshcore_hub/alembic/env.py` | `DATABASE_URL` | Falls to config | Alembic migration DB URL |
| `src/meshcore_hub/alembic/env.py` | `DATA_HOME` | Falls to config | Alembic fallback for computing DB URL |

#### Extraction Method

Grep for these patterns across `src/meshcore_hub/`:
- `os.getenv(`
- `os.environ.get(`
- `os.environ[`
- `os.environ.setdefault(`

#### Key Observation

`HEALTH_DIR` is defined in `common/health.py` but has **no** Pydantic Settings field. It should be documented in AGENTS.md and .env.example if it's user-configurable, or noted as an internal variable if not.

## Classification: Hub Vars vs. Passthrough Vars

Not all env vars in `.env.example` are consumed by the Hub's Python code. Some are passed through to external containers via Docker Compose:

### Hub-Consumed Variables
Read by `meshcore-hub` Python code. Source: `config.py`, CLI modules, direct `os.getenv`.
These MUST be documented in all 5 doc files.

### Docker Passthrough Variables
Read by external containers (packet-capture, MQTT broker). Source: `docker-compose.yml` `environment:` blocks.
These MUST be in `.env.example` and `README.md` Docker sections, but NOT in AGENTS.md env var sections (since the Hub doesn't consume them).

Passthrough prefixes:
- `PACKETCAPTURE_*` — consumed by `ghcr.io/agessaman/meshcore-packet-capture`
- `MQTT_TOKEN_AUDIENCE` — consumed by `ghcr.io/ipnet-mesh/meshcore-mqtt-broker`
- `COMPOSE_PROJECT_NAME` — consumed by Docker Compose itself
- `IMAGE_VERSION`, `PACKETCAPTURE_IMAGE_VERSION` — Docker image tags
- `TRAEFIK_DOMAIN` — consumed by Traefik labels in `docker-compose.traefik.yml`
- `SERIAL_PORT` — device mapping for packet capture container
- `PROMETHEUS_PORT`, `ALERTMANAGER_PORT` — port mappings for monitoring stack

## Complete Extraction Checklist

For a full audit, run these extractions:

1. **Read `common/config.py`** — extract all fields from `CommonSettings`, `CollectorSettings`, `APISettings`, `WebSettings`
2. **Read `__main__.py`** — extract Click `envvar=` parameters and `os.environ` writes
3. **Read `collector/cli.py`** — extract Click `envvar=` parameters
4. **Read `api/cli.py`** — extract Click `envvar=` parameters (especially `CORS_ORIGINS`)
5. **Read `web/cli.py`** — extract Click `envvar=` parameters
6. **Read `web/app.py`** — extract `os.getenv()` calls (channel keys, test channel)
7. **Read `common/health.py`** — extract `os.environ.get()` calls (HEALTH_DIR)
8. **Read `alembic/env.py`** — extract `os.environ.get()` calls (DATABASE_URL, DATA_HOME)
9. **Deduplicate** — merge all sources, noting which vars appear in multiple places
10. **Classify** — tag each var as hub-consumed vs. Docker passthrough

## Three-Layer Config Precedence

When documenting defaults, understand the precedence:

1. **Click `envvar=` CLI option** — highest priority, overrides everything
2. **Pydantic Settings field default** — used when no CLI option or env var is set
3. **`.env` file** — loaded by `python-dotenv` at `__main__.py` startup, feeds into Pydantic Settings

The documented default should be the Pydantic Settings field default, since that's what applies in the general case.
