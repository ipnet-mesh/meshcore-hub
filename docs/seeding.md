# Seed Data

The database can be seeded with node tags from YAML files in the `SEED_HOME` directory (default: `./seed`).

## Running the Seed Process

Seeding is a separate process and must be run explicitly:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile seed up
```

This imports data from the following files (if they exist):

- `{SEED_HOME}/node_tags.yaml` - Node tag definitions

## Directory Structure

```
seed/                          # SEED_HOME (seed data files)
└── node_tags.yaml            # Node tags for import

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
  role: gateway
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
