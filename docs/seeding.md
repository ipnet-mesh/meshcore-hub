# Seed Data

The database can be seeded with node tags and network members from YAML files in the `SEED_HOME` directory (default: `./seed`).

## Running the Seed Process

Seeding is a separate process and must be run explicitly:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile seed up
```

This imports data from the following files (if they exist):

- `{SEED_HOME}/node_tags.yaml` - Node tag definitions
- `{SEED_HOME}/members.yaml` - Network member definitions

## Directory Structure

```
seed/                          # SEED_HOME (seed data files)
├── node_tags.yaml            # Node tags for import
└── members.yaml              # Network members for import

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
  member_id: alice

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

## Network Members

Network members represent the people operating nodes in your network. Members can optionally be linked to nodes via their public key.

### Members YAML Format

```yaml
- member_id: walshie86
  name: Walshie
  callsign: Walshie86
  role: member
  description: IPNet Member
- member_id: craig
  name: Craig
  callsign: M7XCN
  role: member
  description: IPNet Member
```

| Field         | Required | Description                              |
| ------------- | -------- | ---------------------------------------- |
| `member_id`   | Yes      | Unique identifier for the member         |
| `name`        | Yes      | Member's display name                    |
| `callsign`    | No       | Amateur radio callsign                   |
| `role`        | No       | Member's role in the network             |
| `description` | No       | Additional description                   |
| `contact`     | No       | Contact information                      |
| `public_key`  | No       | Associated node public key (64-char hex) |
