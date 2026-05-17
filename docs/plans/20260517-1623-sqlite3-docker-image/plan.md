# Add sqlite3 CLI to Docker Image

## Summary

Add the `sqlite3` command-line tool to the MeshCore Hub Docker runtime
image so operators can inspect, query, and maintain the SQLite database
directly inside running containers. This is a small, low-risk change
that significantly improves operational debuggability without requiring
external tools or volume mounts.

## Background & Motivation

MeshCore Hub uses SQLite as its default database, stored at
`/data/collector/meshcore.db` inside the container (see `DATA_HOME`
env var, defaulting to `/data`). When running in Docker, the database
lives inside a Docker volume (`data` volume in `docker-compose.yml`).

Currently, the runtime image is based on `python:3.14-slim` (line 63 of
`Dockerfile`), which does not include the `sqlite3` CLI tool. This means
operators who need to:

- Inspect table schemas or row counts
- Run ad-hoc queries for debugging
- Perform manual data cleanup or integrity checks
- Dump/export the database for backup analysis

...must either install `sqlite3` ad-hoc (`apt-get update && apt-get
install sqlite3`) inside the running container (lost on restart) or
copy the database file out to a host with `sqlite3` installed. Both
approaches are cumbersome during incident response.

The project has active data retention and cleanup features (see
`DATA_RETENTION_ENABLED`, `NODE_CLEANUP_ENABLED` env vars) and recent
fixes around foreign key enforcement (commit `78d54b7`), making
in-container database inspection increasingly valuable.

## Goals

- Enable `sqlite3` CLI access inside all MeshCore Hub Docker containers
  (collector, api, web, migrate, seed)
- Keep the image size increase minimal
- Maintain the existing security posture (non-root user, slim base)

## Non-Goals

- Adding other database debugging tools (e.g., `sqlitebrowser`, DB
  Browser for SQLite GUI)
- Changing the database engine from SQLite to PostgreSQL or another RDBMS
- Adding a dedicated database maintenance CLI command to `meshcore-hub`
- Modifying the application code or database schema

## Requirements

### Functional Requirements

- The `sqlite3` command must be available in the runtime Docker image
- Operators must be able to exec into any hub container and run
  `sqlite3 /data/collector/meshcore.db` to inspect the database
- The tool must work with the non-root `meshcore` user

### Technical Requirements

- Install `sqlite3` via `apt-get` in the runtime stage of the Dockerfile
- Use `--no-install-recommends` to minimize image size
- Clean up apt lists in the same `RUN` layer to avoid layer bloat
- The `sqlite3` package on Debian/`python:3.14-slim` is approximately
  1-2 MB installed

## Implementation Plan

### Phase 1: Update Dockerfile runtime stage

- Add `sqlite3` to the existing `apt-get install` command in the
  runtime stage (lines 86-90 of `Dockerfile`)
- The current install block already includes `udev` for serial port
  access; add `sqlite3` alongside it

The change modifies a single `RUN` instruction:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For serial port access
    udev \
    # For database debugging and maintenance
    sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data
```

### Phase 2: Verify and document

- Rebuild the Docker image and verify `sqlite3` is available:
  ```
  docker compose --profile core build && \
  docker compose --profile core run --rm api sqlite3 --version
  ```
- No documentation changes needed in AGENTS.md or README.md since this
  is a standard operational tool, not a user-facing feature
- No changes to `.dockerignore`, `docker-compose.yml`, or application
  code

## Open Questions

- None. The change is straightforward and well-scoped.

## References

- `Dockerfile` lines 63-90 (runtime stage)
- `docker-compose.yml` (volume mounts for `/data`)
- `src/meshcore_hub/common/database.py` (SQLite configuration)
- Recent FK enforcement fix: commit `78d54b7`

## Review

**Status**: Approved with Changes

**Reviewed**: 2026-05-17

### Resolutions

- Verification command missing profile flag: Fixed. The `api` service
  is defined in the `core` and `all` profiles in `docker-compose.yml`,
  so `--profile core` is required. Updated the verification command
  from `docker compose build && docker compose run --rm api ...` to
  `docker compose --profile core build && docker compose --profile
  core run --rm api sqlite3 --version`.

### Remaining Action Items

- None. The change is single-file (Dockerfile), one-line addition,
  well-scoped, and ready to implement.
