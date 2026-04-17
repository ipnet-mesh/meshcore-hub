# Documentation Checklist

Per-file verification checklists for each of the 5 primary documentation files.

## 1. README.md

### Environment Variable Tables

README.md contains env var tables grouped by component. For each table:

- [ ] **Common Settings table** — every var from `CommonSettings` is listed with correct default
- [ ] **Collector Settings table** — every collector-specific var from `CollectorSettings` is listed
- [ ] **Webhook table** — all 11 webhook vars listed (6 URL/secret pairs + timeout + retries + backoff)
- [ ] **Data Retention table** — all retention and node cleanup vars listed
- [ ] **API Settings table** — all API-specific vars from `APISettings` listed
- [ ] **Web Dashboard Settings table** — all web-specific vars from `WebSettings` listed
- [ ] **Feature Flags table** — all 7 feature flags listed
- [ ] **Network Info vars** — all `NETWORK_*` vars listed
- [ ] **Contact Info vars** — all `NETWORK_CONTACT_*` vars listed

For each variable in each table:
- [ ] Default value matches Pydantic Settings field default exactly
- [ ] Description is accurate and matches field purpose
- [ ] No stale/removed variables remain
- [ ] No variables are duplicated across tables

### Docker Section

- [ ] Compose files listed: base, dev, prod, traefik (4 files)
- [ ] Service profiles table matches `docker-compose.yml` exactly
- [ ] All 7 services documented: mqtt, observer, collector, api, web, migrate, seed
- [ ] Port mappings match `docker-compose.dev.yml`
- [ ] Volume names documented with `COMPOSE_PROJECT_NAME` prefix convention
- [ ] Bind mounts documented (SEED_HOME, CONTENT_HOME)
- [ ] Traefik integration instructions reference `TRAEFIK_DOMAIN`
- [ ] Reverse Proxy section links to `docs/hosting/nginx-proxy-manager.md`
- [ ] Production network setup (`proxy-net`) documented
- [ ] Quick start examples use correct current commands

### Features Section

- [ ] Each listed feature corresponds to actual code
- [ ] Feature flag dependency rules documented correctly (Dashboard auto-disables when Nodes/Ads/Messages all off; Map auto-disables when Nodes off)

### CLI Commands

- [ ] `meshcore-hub collector` — verify still exists
- [ ] `meshcore-hub api` — verify still exists
- [ ] `meshcore-hub web` — verify still exists
- [ ] `meshcore-hub db upgrade` — verify still exists
- [ ] `meshcore-hub collector seed` — verify still exists
- [ ] `meshcore-hub collector cleanup` — verify still exists
- [ ] All example Docker Compose commands use valid profile names

### File Paths

- [ ] `src/meshcore_hub/` structure matches actual layout
- [ ] Seed data directory structure (`node_tags.yaml`, `members.yaml`) documented in `docs/seeding.md`
- [ ] Custom content directory structure (`pages/`, `media/`) documented
- [ ] Translation files location (`src/meshcore_hub/web/static/locales/`) documented
- [ ] No references to removed files (PLAN.md, TASKS.md)

## 2. AGENTS.md

### Environment Variables Section

AGENTS.md has a "Key variables" subsection under "Environment Variables". Verify:

- [ ] All hub-consumed env vars listed (from Pydantic Settings + Click + os.getenv)
- [ ] Passthrough vars (`PACKETCAPTURE_*`, `COMPOSE_PROJECT_NAME`, etc.) NOT listed as Hub vars
- [ ] Defaults match Pydantic Settings defaults
- [ ] Descriptions match field purpose
- [ ] Grouping matches the Settings class hierarchy (Common, Collector, API, Web)

### Project Structure

- [ ] Directory tree matches actual layout
- [ ] All listed files exist
- [ ] No removed files listed (e.g., PLAN.md, TASKS.md)
- [ ] All new directories/files included

### Features Documented

- [ ] Feature flags listed in "Environment Variables" match `WebSettings` fields
- [ ] Dependency rules documented (Dashboard/Map auto-disable logic)
- [ ] Admin auth mechanism documented accurately

### Code Examples

- [ ] Import paths use current module structure
- [ ] Class names match current models
- [ ] CLI commands match current Click definitions
- [ ] Async patterns match current codebase conventions

### Cross-References

- [ ] References to `PLAN.md` — should be removed (file deleted)
- [ ] References to `TASKS.md` — should be removed (file deleted)
- [ ] References to `SCHEMAS.md` — should remain (file exists)
- [ ] References to `docs/upgrading.md` — should remain (file exists)
- [ ] References to `docs/letsmesh.md` — should remain (file exists)

## 3. docs/upgrading.md

### Deprecated Variables

docs/upgrading.md lists variables to remove during upgrade. Verify:

- [ ] Each deprecated var truly no longer exists in `config.py` or any CLI module
- [ ] Removal instructions are clear
- [ ] No currently-active vars are listed as deprecated

### New Variables

- [ ] Each new var listed actually exists in current `config.py`
- [ ] Defaults for new vars match Pydantic Settings defaults
- [ ] Migration instructions for adding new vars are correct

### Renamed Variables

- [ ] Old name no longer exists anywhere in codebase
- [ ] New name matches current `config.py` field name

### Docker Migration

- [ ] Volume rename instructions accurate
- [ ] Old service names truly removed from compose files
- [ ] New compose file structure documented correctly
- [ ] Migration commands still valid for current Docker versions

### Database Migration

- [ ] Column renames documented accurately (e.g., `receiver_node_id` → `observer_node_id`)
- [ ] Table renames documented accurately (e.g., `event_receivers` → `event_observers`)

## 3b. docs/letsmesh.md

### Packet Decoding Documentation

docs/letsmesh.md documents the LetsMesh packet normalization and decoding behavior. Verify:

- [ ] MQTT subscription topics match `subscriber.py` topic patterns
- [ ] Payload type mappings match `letsmesh_decoder.py` and `letsmesh_normalizer.py` logic
- [ ] Channel key handling documented matches `COLLECTOR_CHANNEL_KEYS` config behavior
- [ ] Known channel indexes (`17 -> Public`, `217 -> #test`) match built-in defaults in decoder
- [ ] Message normalization rules match collector handler implementations
- [ ] GPS/location update behavior documented matches advertisement handler logic
- [ ] No stale decoder behavior documented (e.g., references to Node.js decoder)

## 3c. docs/hosting/nginx-proxy-manager.md

### NPM Admin Setup Guide

docs/hosting/nginx-proxy-manager.md documents the Nginx Proxy Manager reverse proxy setup for admin authentication. Verify:

- [ ] Dual-hostname setup (public + admin) documented
- [ ] Proxy host settings (scheme, port, websockets) match `docker-compose.dev.yml` port mappings
- [ ] `WEB_ADMIN_ENABLED` requirement documented
- [ ] Nginx `Advanced` config block headers match those checked by `web/auth.py`
- [ ] Verification curl command uses correct endpoint (`/config.js`)
- [ ] Troubleshooting steps reference correct config variables

## 3d. docs/seeding.md

### Seed Data Documentation

docs/seeding.md documents the seed data format and import process for node tags and network members. Verify:

- [ ] Running the Seed Process section references correct Docker Compose command (`--profile seed`)
- [ ] Seed files listed match `tag_import.py` and `member_import.py` expected filenames
- [ ] Directory structure shows `SEED_HOME` and `DATA_HOME` correctly
- [ ] Node Tags YAML format matches `tag_import.py` parsing logic
- [ ] Tag value types documented match supported types in `tag_import.py`
- [ ] Members YAML format matches `member_import.py` parsing logic
- [ ] Member field table fields match `MemberCreate` Pydantic schema
- [ ] Example seed files referenced in `example/seed/` exist

## 4. .env.example

### Section Structure

Verify sections exist and are correctly ordered:

1. [ ] Quick Start header with observer node example
2. [ ] Common Settings (`COMPOSE_PROJECT_NAME`, `TRAEFIK_DOMAIN`, `IMAGE_VERSION`, `LOG_LEVEL`, `DATA_HOME`, `SEED_HOME`)
3. [ ] MQTT Settings (`MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_PREFIX`, `MQTT_TLS`, `MQTT_TRANSPORT`, `MQTT_WS_PATH`, `MQTT_TOKEN_AUDIENCE`)
4. [ ] Packet Capture Settings (all `PACKETCAPTURE_*` vars + `SERIAL_PORT`)
5. [ ] Collector Settings (`COLLECTOR_CHANNEL_KEYS`, `COLLECTOR_INCLUDE_TEST_CHANNEL`, webhooks, retention, cleanup)
6. [ ] API Settings (`API_PORT`, `API_READ_KEY`, `API_ADMIN_KEY`, metrics)
7. [ ] Web Dashboard Settings (`WEB_PORT`, `API_BASE_URL`, `API_KEY`, theme, locale, auto-refresh, admin, TZ, content home, network info, feature flags, contact info)

### Per-Variable Checks

For every variable in `.env.example`:

- [ ] Variable name matches the env var name exactly (UPPER_SNAKE_CASE)
- [ ] Default value matches Pydantic Settings default OR compose file default (for passthrough vars)
- [ ] Comment above the variable accurately describes its purpose
- [ ] Comment includes valid range/options where applicable (e.g., "DEBUG, INFO, WARNING, ERROR, CRITICAL")
- [ ] Optional vars are commented out (`# VAR=`) with a note about the default
- [ ] Required vars have an uncommented assignment with the default value
- [ ] No duplicate variable entries
- [ ] No removed/stale variables

### Comment Accuracy

- [ ] `COMPOSE_PROJECT_NAME` comment mentions container/volume prefix
- [ ] `MQTT_TRANSPORT` comment states WebSocket is required by MeshCore broker
- [ ] `MQTT_WS_PATH` comment notes default `/` vs production `/mqtt`
- [ ] `MQTT_TOKEN_AUDIENCE` comment explains it must match broker config
- [ ] `PACKETCAPTURE_*` comments reference the external packet capture image
- [ ] `COLLECTOR_CHANNEL_KEYS` comment explains label=hex format
- [ ] `WEB_*` comments reference web dashboard behavior
- [ ] `FEATURE_*` comments explain what each flag controls
- [ ] `NETWORK_*` comments explain where values appear in UI
- [ ] `PROMETHEUS_PORT` / `ALERTMANAGER_PORT` comments reference the monitoring profile

### Missing Variables Check

- [ ] Every hub-consumed var from `config.py` appears (or is commented out) in `.env.example`
- [ ] Every passthrough var from compose files appears in `.env.example`
- [ ] No extra variables that don't exist in any compose file or Python source

## 5. SCHEMAS.md

### Event Schema Verification

SCHEMAS.md documents the JSON schemas for events stored in the database. Verify:

- [ ] Each event type documented has a corresponding handler in `src/meshcore_hub/collector/handlers/`
- [ ] Each documented field exists in the corresponding Pydantic schema or SQLAlchemy model
- [ ] Field types match current code (e.g., `str`, `int`, `Optional[str]`)
- [ ] Required vs optional fields match current schema definitions
- [ ] Database column names match current SQLAlchemy model definitions

### Database Table Verification

For each table documented in SCHEMAS.md:

- [ ] Table name matches `__tablename__` in the corresponding SQLAlchemy model
- [ ] Column names match `mapped_column()` field names
- [ ] Column types match (String length, DateTime, Text, Integer, etc.)
- [ ] Foreign key relationships documented correctly
- [ ] Indexes and unique constraints documented correctly
- [ ] New columns from recent migrations are included
- [ ] Removed columns are not documented

### MQTT Topic Schema

- [ ] Topic structure documented matches what the collector subscribes to
- [ ] Upload topic format (`<prefix>/<IATA>/<public_key>/<feed_type>`) is correct
- [ ] Subscriber subscriptions listed match `subscriber.py` topic patterns

## Cross-File Consistency Checks

These checks ensure all primary documentation files are consistent with each other:

### Env Var Coverage Matrix

Every hub-consumed env var should appear in:

| File | Required | Format |
|------|----------|--------|
| `config.py` | Yes (source of truth) | Pydantic field |
| `README.md` | Yes | Table row with default + description |
| `AGENTS.md` | Yes | Mentioned in env vars section |
| `.env.example` | Yes | Entry with default + comment |
| `docs/upgrading.md` | Only if new/renamed/deprecated | Migration instruction |

Every passthrough env var should appear in:

| File | Required |
|------|----------|
| `docker-compose.yml` | Yes (source of truth) |
| `README.md` | Yes |
| `.env.example` | Yes |
| `AGENTS.md` | No |

### Default Value Consistency

- [ ] Same default in README.md tables, .env.example values, and config.py
- [ ] No contradictions between files
- [ ] Type representations consistent (e.g., don't mix `true`/`True`/`1` for booleans)

### Stale Reference Sweep

Check all primary documentation files for references to removed items:

- [ ] `PLAN.md` — removed, references should be deleted from AGENTS.md
- [ ] `TASKS.md` — removed, references should be deleted from AGENTS.md
- [ ] Old compose profiles (`receiver`, `sender`, `mock`) — should only exist in docs/upgrading.md as deprecated
- [ ] Old service names (`interface-receiver`, `interface-sender`) — should only exist in docs/upgrading.md as deprecated
- [ ] Old env var names (`COLLECTOR_LETSMESH_DECODER_*`, `SERIAL_BAUD`, etc.) — should only exist in docs/upgrading.md as deprecated

## Applying Fixes

When discrepancies are found:

1. **Identify the source of truth** — config.py for env vars, docker-compose.yml for Docker config
2. **Determine scope** — which files need updating
3. **Make minimal edits** — only change what's wrong, preserve surrounding formatting
4. **Match existing style** — tables use same column order, comments use same format, sections use same headers
5. **Preserve historical content** — docs/upgrading.md deprecated var lists are historical, do not remove them
6. **Verify after editing** — re-read the changed section to confirm accuracy
