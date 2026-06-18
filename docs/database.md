# Database

MeshCore Hub supports two database backends: **SQLite** (the zero-config default) and **PostgreSQL** (optional, for write scaling and multi-host deployments). Postgres is opt-in — leave the `DATABASE_*` variables unset to keep using SQLite.

> [!NOTE]
> As of v0.14, SQLite is **deprecated** in favour of PostgreSQL. SQLite remains the default and continues to work unchanged; support will be removed in a future release (at least 3 months out). New deployments that need to scale across hosts should pick Postgres. Existing SQLite deployments can move to Postgres with a one-command migration — see [Migrating from SQLite to PostgreSQL](#migrating-from-sqlite-to-postgresql) and [upgrading.md](upgrading.md).

## SQLite (default)

SQLite needs no configuration. The database file is created automatically on first run and lives under `DATA_HOME` (see [configuration.md → Common](configuration.md#common)):

```
${DATA_HOME}/collector/meshcore.db
```

In Docker Compose this is the `hub_data` volume (`${COMPOSE_PROJECT_NAME:-hub}_data`). WAL mode is enabled automatically, allowing concurrent readers alongside the collector's single writer.

**Limitations:** writes are serialised to one process, and SQLite's file locking does **not** work over network filesystems — it caps you at a single host. To scale writes or run the stack across multiple hosts, switch to PostgreSQL.

## PostgreSQL

Set `DATABASE_BACKEND=postgres` and fill in the `DATABASE_*` connection variables. Postgres is never selected implicitly — the explicit switch avoids a silent backend change. For the full variable reference, see [configuration.md → Database](configuration.md#database).

### Docker (bundled container)

Postgres is bundled behind the `postgres` compose profile:

```bash
# Start the stack on Postgres (bundled container)
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  --profile postgres --profile core up -d

# Start on SQLite (default — no postgres profile)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile core up -d
```

### Production provisioning (role and database)

The bundled container provisions the role and database for you on first start from the `DATABASE_*` values. For a **managed or external** Postgres, create them once before pointing Hub at it. This mirrors the init script used in the [ipnet-mesh/infrastructure](https://github.com/ipnet-mesh/infrastructure/blob/main/etc/postgres/init/02_meshcorehub_db.sh) cluster:

```sql
-- Run once as a superuser/admin role on the target cluster
CREATE DATABASE meshcorehub;
CREATE ROLE meshcorehub LOGIN PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE meshcorehub TO meshcorehub;
```

The application **schema** and tables are created automatically by `db upgrade` (run by the `migrate` service on startup); the role just needs `CREATE` privilege on the database. Hub only ever connects as `DATABASE_USER` — no admin or bootstrap credentials are needed at runtime.

### Managed or external Postgres

To point Hub at an already-running Postgres (e.g. a managed cloud instance), set `DATABASE_HOST` at it and **do not** activate the `postgres` profile:

```bash
DATABASE_BACKEND=postgres
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

## Schema-per-instance (`search_path`)

Each Hub instance is isolated to its own Postgres **schema** via the connection's `search_path`, rather than its own database. This lets several instances (e.g. `prod`, `stg`) share **one** Postgres cluster without colliding — each gets its own tables and its own `alembic_version`.

Give every instance a distinct `DATABASE_SCHEMA`:

```bash
# Production (.env)
COMPOSE_PROJECT_NAME=hub
DATABASE_BACKEND=postgres
DATABASE_SCHEMA=meshcorehub_prod

# Staging (.env, separate directory)
COMPOSE_PROJECT_NAME=hub-beta
DATABASE_BACKEND=postgres
DATABASE_SCHEMA=meshcorehub_stg
```

The schema is created automatically on `db upgrade` if it does not exist, so no manual `CREATE SCHEMA` is required. Connect both instances to the same `DATABASE_HOST` / `DATABASE_NAME` / `DATABASE_USER`; only `DATABASE_SCHEMA` (and `COMPOSE_PROJECT_NAME`) differ.

> **Note:** This is the database-level isolation for instances sharing a Postgres cluster. For running multiple instances on the same Docker host (separate volumes, Traefik routing), see [Multi-Instance Deployments](deployment.md#multi-instance-deployments).

## Migrating from SQLite to PostgreSQL

Existing SQLite deployments can be moved to Postgres with a single built-in command (`meshcore-hub db migrate-to-postgres`), which copies every table in foreign-key order through the ORM and prints a per-table row-count reconciliation. Downtime is required while writers are stopped; the source SQLite file is never modified.

See the **v0.14 upgrade guide** in [upgrading.md](upgrading.md#migrating-an-existing-sqlite-database-to-postgres) for the full step-by-step runbook (backup, stop writers, bring up Postgres, run the migration, restart on Postgres).
