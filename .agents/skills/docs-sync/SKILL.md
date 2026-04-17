---
name: docs-sync
description: "Audits and fixes discrepancies between project source code (Python config, Docker Compose files) and primary documentation files (README.md, AGENTS.md, UPGRADING.md, .env.example, SCHEMAS.md). Extracts environment variables from Pydantic Settings, Click CLI options, and os.getenv calls; parses Docker Compose services, profiles, volumes, and env passthroughs; verifies feature flags, CLI commands, and file paths referenced in documentation. Produces a structured audit report and applies fixes to keep documentation accurate and up-to-date. Invoke after any config change, env var addition/removal, Docker service modification, feature flag change, or when documentation drift is suspected."
license: MIT
compatibility: opencode
metadata:
  author: https://github.com/agessaman
  version: "0.1.0"
  domain: quality
  triggers: documentation sync, docs audit, env vars, config drift, .env.example, README, AGENTS.md, UPGRADING.md, SCHEMAS.md, docker compose docs, feature flags, documentation update, keep docs in sync, documentation accuracy
  role: specialist
  scope: review
  output-format: report
  related-skills: code-review, docs-writer
---

# Docs Sync

Documentation accuracy specialist that keeps project docs in sync with source code and Docker configuration.

## When to Use This Skill

- After adding, removing, or renaming environment variables in Python config
- After modifying Docker Compose services, profiles, volumes, or port mappings
- After adding or removing feature flags
- After adding or removing CLI commands or subcommands
- After changing Pydantic Settings defaults or types
- When documentation drift is suspected
- Before releases to ensure docs are accurate
- When AGENTS.md or README.md references stale files or commands

## Primary Documentation Files

The following files are the documentation targets. All must be kept in sync:

| File | Role |
|------|------|
| `README.md` | User-facing reference: env var tables, Docker instructions, feature list |
| `AGENTS.md` | AI agent instructions: env var list, project structure, conventions |
| `UPGRADING.md` | Upgrade guide: deprecated vars, new vars, migration steps |
| `.env.example` | Example environment file with comments and defaults |
| `SCHEMAS.md` | Event JSON schemas and database column mappings |

## Core Workflow

1. **Extract config from Python source** — Parse all environment variables from three sources: Pydantic Settings classes in `common/config.py`, Click `envvar=` parameters in CLI modules, and direct `os.getenv()`/`os.environ` calls. Build a complete inventory with field names, defaults, types, and descriptions. See `references/config-source-guide.md`.

2. **Extract Docker configuration** — Parse all `docker-compose*.yml` files for services, compose profiles, volumes, port mappings, environment variable references (with defaults), and device mappings. Distinguish hub-consumed vars from passthrough vars (e.g., `PACKETCAPTURE_*`). See `references/docker-source-guide.md`.

3. **Extract features and commands** — Verify feature flags have corresponding UI routes and config fields. Verify CLI commands documented in README.md and AGENTS.md still exist. Verify file paths and directory structures referenced in docs actually exist.

4. **Cross-reference against documentation** — For each of the 5 primary doc files, check every env var, Docker service, feature, command, and path reference against the source-of-truth inventories from steps 1-3. See `references/documentation-checklist.md`.

5. **Verify inline comments** — Check that all comments in `.env.example` and `docker-compose*.yml` accurately describe the values they annotate. Verify default values in comments match actual defaults from source code.

6. **Produce report and apply fixes** — Generate a structured discrepancy report. For each discrepancy, apply the fix to the relevant documentation file. Summarize all changes made.

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Config Source Extraction | `references/config-source-guide.md` | Extracting env vars from Python source |
| Docker Source Extraction | `references/docker-source-guide.md` | Parsing Docker Compose files |
| Documentation Checklist | `references/documentation-checklist.md` | Cross-referencing against each doc file |

## Discrepancy Categories

| Category | Severity | Description |
|----------|----------|-------------|
| Missing env var in docs | High | Variable exists in source but not in a doc file that should list it |
| Stale env var in docs | High | Variable documented but no longer exists in source |
| Wrong default value | High | Documented default doesn't match actual default |
| Wrong type or description | Medium | Documented type or description doesn't match source |
| Missing Docker service/profile | High | Service or profile exists in compose but not documented |
| Stale Docker service/profile | High | Documented service or profile no longer exists |
| Stale file path reference | Medium | Referenced file or directory doesn't exist |
| Stale CLI command | High | Documented command no longer exists |
| Stale feature reference | Medium | Documented feature flag doesn't exist in config |
| Inaccurate inline comment | Low | Comment doesn't accurately describe the value |
| Missing comment | Low | Value lacks a descriptive comment |
| Stale doc cross-reference | Medium | Reference to removed file (e.g., PLAN.md, TASKS.md) |

## Report Template

```
# Docs Sync Audit Report

## Summary
- Total discrepancies found: N
- High: N | Medium: N | Low: N
- Files modified: N

## Environment Variables
### Missing from documentation
| Variable | Default | Missing from |
|----------|---------|-------------|
| ... | ... | README.md, .env.example |

### Stale (removed from source)
| Variable | Still in |
|----------|---------|
| ... | AGENTS.md, README.md |

### Wrong defaults
| Variable | Documented | Actual |
|----------|-----------|--------|
| ... | ... | ... |

## Docker Configuration
### Services/Profiles
[Discrepancies between compose files and docs]

### Environment Passthroughs
[Missing or stale env vars in .env.example for Docker]

## Features & Commands
### Stale features
[Documented features that don't exist]

### Missing features
[Features in source but not documented]

### Stale commands
[Documented CLI commands that don't exist]

### Stale file references
[Paths referenced in docs that don't exist]

## Inline Comments
### Inaccurate comments
| File | Line | Current | Correct |
|------|------|---------|---------|
| ... | ... | ... | ... |

## Changes Applied
[List of edits made to each file]
```

## Constraints

### MUST DO

- Treat Python source code (`common/config.py`, CLI modules, `os.getenv` calls) as the single source of truth for environment variables
- Treat `docker-compose*.yml` files as the source of truth for Docker configuration
- Check ALL five documentation files on every audit
- Include `.env.example` comment verification
- Include `docker-compose*.yml` inline comment verification
- Verify default values match exactly (type-aware: `true` vs `"true"`, port numbers as strings vs ints)
- Flag references to removed files (PLAN.md, TASKS.md) in AGENTS.md and README.md
- Apply fixes to documentation files after reporting
- Preserve existing formatting and section structure in doc files
- For AGENTS.md env var sections, maintain the existing table format and grouping

### MUST NOT DO

- Modify Python source code or Docker Compose files (only documentation files)
- Add documentation for variables that don't exist in source
- Remove content from documentation without confirming it's stale in source
- Change the formatting style of existing documentation (match surrounding content)
- Modify UPGRADING.md historical content (deprecated var lists, old instructions)
- Skip any of the 5 documentation files
- Guess at defaults — always verify against actual source code
- Treat test compose files (`tests/e2e/`) as documentation targets (they are test fixtures)

## Knowledge Reference

Pydantic Settings (BaseSettings, env_file, field defaults), Click (envvar parameter), Docker Compose (profiles, volumes, environment, depends_on), YAML parsing, environment variable naming conventions (UPPER_SNAKE_CASE), MeshCore Hub architecture (collector, API, web, MQTT broker, packet capture observer)
