# Database

MeshCore Hub runs on **PostgreSQL** — the only supported database backend since v0.19. The bundled container is part of the default `core` compose profile, so a standard `docker compose up` works with zero configuration; managed/external Postgres and multiple schema-isolated instances sharing one cluster are equally supported.

> [!NOTE]
> SQLite support (the pre-v0.14 default) was **removed in v0.19**. Existing SQLite deployments can migrate in place with the built-in `meshcore-hub db migrate-to-postgres` command — see [Upgrading from SQLite](#upgrading-from-sqlite) below and the [v0.19 upgrade guide](upgrading.md).

## Docker (bundled container)

Postgres ships with the stack and starts with the `core` profile — no extra flags:

```bash
# Default stack: bundled Postgres starts alongside the app services
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core up -d
```

The container derives `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME`, and ships a **dev-only default password** (`meshcorehub`) so a default `up` initializes out of the box. **Production deployments must override `DATABASE_PASSWORD`** — the container is not published outside the compose network, but the default password is public knowledge (it is in the repo).

The `migrate` service waits for Postgres to be healthy and runs `db upgrade` before `collector` and `api` start.

## Production provisioning (role and database)

The bundled container provisions the role and database for you on first start from the `DATABASE_*` values. For a **managed or external** Postgres, create them once before pointing Hub at it. This mirrors the init script used in the [ipnet-mesh/infrastructure](https://github.com/ipnet-mesh/infrastructure/blob/main/etc/postgres/init/02_meshcorehub_db.sh) cluster:

```sql
-- Run once as a superuser/admin role on the target cluster
CREATE DATABASE meshcorehub;
CREATE ROLE meshcorehub LOGIN PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE meshcorehub TO meshcorehub;
```

The application **schema** and tables are created automatically by `db upgrade` (run by the `migrate` service on startup); the role just needs `CREATE` privilege on the database. Hub only ever connects as `DATABASE_USER` — no admin or bootstrap credentials are needed at runtime.

## Managed or external Postgres

To point Hub at an already-running Postgres (e.g. a managed cloud instance), set the `DATABASE_*` connection variables. The bundled container still starts with the `core` profile (it simply runs idle if the services point elsewhere); to skip it entirely, start a narrower profile set, e.g. `--profile collector --profile api`:

```bash
DATABASE_HOST=your-managed-postgres.example.com
DATABASE_PORT=5432
DATABASE_NAME=meshcorehub
DATABASE_USER=meshcorehub
DATABASE_PASSWORD=your-password
```

For advanced cases (custom driver, extra query params), set a full SQLAlchemy URL instead — it takes precedence over all the component variables:

```bash
DATABASE_URL=postgresql+psycopg2://meshcorehub:your-password@host:5432/meshcorehub
```

Missing connection configuration (no `DATABASE_URL` and no `DATABASE_*` components) fails fast at startup with an error naming the missing variables — Hub never silently falls back to a default.

## Schema-per-instance (`search_path`)

Each Hub instance is isolated to its own Postgres **schema** via the connection's `search_path`, rather than its own database. This lets several instances (e.g. `prod`, `stg`) share **one** Postgres cluster without colliding — each gets its own tables and its own `alembic_version`.

Give every instance a distinct `DATABASE_SCHEMA`:

```bash
# Production (.env)
COMPOSE_PROJECT_NAME=hub
DATABASE_SCHEMA=meshcorehub_prod

# Staging (.env, separate directory)
COMPOSE_PROJECT_NAME=hub-beta
DATABASE_SCHEMA=meshcorehub_stg
```

The schema is created automatically on `db upgrade` if it does not exist, so no manual `CREATE SCHEMA` is required. Connect both instances to the same `DATABASE_HOST` / `DATABASE_NAME` / `DATABASE_USER`; only `DATABASE_SCHEMA` (and `COMPOSE_PROJECT_NAME`) differ.

> **Note:** This is the database-level isolation for instances sharing a Postgres cluster. For running multiple instances on the same Docker host (separate volumes, Traefik routing), see [Multi-Instance Deployments](deployment.md#multi-instance-deployments).

## Upgrading from SQLite

Deployments still on SQLite (the pre-v0.14 default, deprecated in v0.14 and removed in v0.19) can be moved to Postgres in place with a single built-in command (`meshcore-hub db migrate-to-postgres`), which copies every table in foreign-key order through the ORM and prints a per-table row-count reconciliation. Downtime is required while writers are stopped; the source SQLite file is never modified. The command is retained through v0.19 and scheduled for removal in v0.20.

See the **v0.19 upgrade guide** in [upgrading.md](upgrading.md) for the full step-by-step runbook (backup, stop writers, bring up Postgres, run the migration, restart).
