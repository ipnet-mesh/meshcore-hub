# Seed Data

The database can be seeded with node tags from YAML files in the `SEED_HOME` directory (default: `./seed`).

## Running the Seed Process

Seeding is a separate process and must be run explicitly:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile seed up
```

This imports data from the following files (if they exist):

- `{SEED_HOME}/node_tags.yaml` - Node tag definitions
- `{SEED_HOME}/channels.yaml` - Channel decryption keys
- `{SEED_HOME}/routes.yaml` - Route health monitoring definitions

## Directory Structure

```
seed/                          # SEED_HOME (seed data files)
├── node_tags.yaml            # Node tags for import
├── channels.yaml             # Channel keys for import
└── routes.yaml               # Route health definitions for import

data/                          # DATA_HOME (runtime data)
└── collector/
    └── meshcore.db           # SQLite database
```

Example seed files are provided in `example/seed/`.

## Node Tags

Node tags allow you to attach custom metadata to nodes (e.g., location, role, owner). Tags are stored in the database and returned with node data via the API.

### Node Tags YAML Format

Tags are keyed by public key in YAML format:

```yaml
# Each key is a 64-character hex public key
0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:
  name: Gateway Node
  description: Main network gateway
  lat: 37.7749
  lon: -122.4194

fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210:
  name: Oakland Repeater
  elevation: 150
```

Tag values can be:

- **YAML primitives** (auto-detected type): strings, numbers, booleans
- **Explicit type** (when you need to force a specific type):
  ```yaml
  altitude:
    value: "150"
    type: number
  ```

Supported types: `string`, `number`, `boolean`

## Channels

Channel keys are used to decrypt encrypted mesh messages. They are stored in the database and loaded by the collector at startup, with periodic refresh.

### Channels YAML Format

Channels support two formats:

**Shorthand** (name → hex key string):

```yaml
MyChannel: AABBCCDD11223344AABBCCDD11223344
```

**Expanded** (name → dict with options):

```yaml
MyChannel:
  key: AABBCCDD11223344AABBCCDD11223344
  enabled: true
```

Key rules:
- Keys must be uppercase hex, 32 characters (AES-128) or 64 characters (AES-256)
- Seeded channels always have `visibility: community` — to set member/operator/admin visibility, use the CLI or API
- The `Public` and `test` built-in keys are always loaded into the decoder regardless of database contents
- Test channel messages are only stored when a `test` channel row exists in the database with `enabled: true`

### Managing Channels via CLI

```bash
# List all channels
meshcore-hub collector channel list

# Add a channel
meshcore-hub collector channel add --name MyChannel --key AABBCCDD11223344AABBCCDD11223344

# Enable/disable a channel
meshcore-hub collector channel enable --name MyChannel
meshcore-hub collector channel disable --name MyChannel

# Remove a channel
meshcore-hub collector channel remove --name MyChannel
```

## Routes

> See [routes.md](routes.md) for the route health monitoring feature overview and evaluation semantics.

Routes define multi-hop mesh paths to monitor for health. Each route is keyed by its `from`/`to` endpoint labels and is upserted (created or updated) by that label pair.

### Routes YAML Format

A list under the top-level `routes:` key. Each entry requires `from`, `to`, and an ordered `path` of at least 2 distinct node public keys:

```yaml
routes:
  - from: Ipswich
    to: Norwich
    description: A140 corridor route
    visibility: community
    match_width: 1
    window_hours: 48
    packet_count_threshold: 5
    # clear_threshold: 15      # optional; omit/null = 3x threshold
    # max_hop_span: 8           # optional; omit/null = unlimited
    enabled: true
    reversible: true              # match both directions (A->B and B->A)
    path:
      - a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
      - 9a8b7c6d5e4f9a8b7c6d5e4f9a8b7c6d5e4f9a8b7c6d5e4f9a8b7c6d5e4f9a8b
    # observers:                 # optional; omit/empty = all observers
    #   - 0102030405060102030405060102030405060102030405060102030405060102
```

Rules:

- Path nodes must already exist in the database (create them via `node_tags.yaml` or let the collector discover them). A missing path node is a hard error.
- Observer nodes that don't exist yet are skipped with a warning (not an error).
- The `(from, to)` label pair must be unique across all routes.
