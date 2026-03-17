# Product Requirements Document

> Source: `.plans/2026/03/17/01-multibyte-support/prompt.md`

## Project Overview

MeshCore Hub must be updated to support multibyte path hashes introduced in MeshCore firmware v1.14 and the meshcore_py v2.3.0 Python bindings. Path hashes — node identifiers embedded in trace and route data — were previously fixed at 1 byte (2 hex characters) per hop but can now be multiple bytes, allowing longer repeater IDs at the cost of reduced maximum hops. The update must maintain backwards compatibility with nodes running older single-byte firmware.

## Goals

- Support variable-length (multibyte) path hashes throughout the data pipeline: interface → MQTT → collector → database → API → web dashboard.
- Maintain backwards compatibility so single-byte path hashes from older firmware nodes continue to work without modification.
- Update documentation and schemas to accurately describe the new variable-length path hash format.

## Functional Requirements

### REQ-001: Accept Variable-Length Path Hashes in Collector

**Description:** The collector's event handlers and normalizer must accept path hash strings of any even length (not just 2-character strings). Path hashes arriving from both the meshcore_py interface and LetsMesh-compatible ingest must be processed correctly regardless of byte length.

**Acceptance Criteria:**

- [ ] Path hashes with 2-character values (legacy single-byte) are accepted and stored correctly
- [ ] Path hashes with 4+ character values (multibyte) are accepted and stored correctly
- [ ] Mixed-length path hash arrays (e.g. `["4a", "b3fa", "02"]`) are accepted when the mesh contains nodes with different firmware versions
- [ ] The LetsMesh normalizer handles multibyte `pathHashes` values from decoded payloads

### REQ-002: Update Pydantic Schema Validation for Path Hashes

**Description:** The `path_hashes` field in event and message Pydantic schemas currently describes values as "2-character node hash identifiers". The schema description and any validation constraints must be updated to permit variable-length hex strings.

**Acceptance Criteria:**

- [ ] `TraceDataEvent.path_hashes` field description reflects variable-length hex strings
- [ ] `MessageEventBase.path_hashes` field description reflects variable-length hex strings (if applicable)
- [ ] No schema validation rejects path hash strings longer than 2 characters

### REQ-003: Verify Database Storage Compatibility

**Description:** The `path_hashes` column on the `trace_paths` table uses a JSON column type. Confirm that variable-length path hash strings are stored and retrieved correctly without requiring a schema migration.

**Acceptance Criteria:**

- [ ] Multibyte path hash arrays are round-tripped correctly through SQLAlchemy JSON column (store and retrieve)
- [ ] No Alembic migration is required (JSON column already supports arbitrary string lengths)

### REQ-004: Update API Responses for Variable-Length Path Hashes

**Description:** The trace paths API must return multibyte path hashes faithfully. API response schemas and any serialization logic must not truncate or assume a fixed length.

**Acceptance Criteria:**

- [ ] `GET /trace-paths` returns multibyte path hash arrays as-is from the database
- [ ] `GET /trace-paths/{id}` returns multibyte path hash arrays as-is from the database
- [ ] API response examples in documentation reflect variable-length path hashes

### REQ-005: Update Web Dashboard Trace/Path Display

**Description:** If the web dashboard displays path hashes (e.g. in trace path views), the rendering must handle variable-length strings without layout breakage or truncation.

**Acceptance Criteria:**

- [ ] Trace path views display multibyte path hashes correctly
- [ ] No fixed-width formatting assumes 2-character hash strings

### REQ-006: Verify meshcore_py Library Compatibility

**Description:** Confirm that the meshcore_py v2.3.0+ library handles backwards compatibility with single-byte firmware nodes transparently, so that MeshCore Hub does not need to implement compatibility logic itself.

**Acceptance Criteria:**

- [ ] meshcore_py v2.3.0+ is confirmed to handle mixed single-byte and multibyte path hashes at the protocol level
- [ ] The interface receiver and sender components work with the updated library without code changes beyond the dependency version bump (or with minimal changes if the library API changed)

## Non-Functional Requirements

### REQ-007: Backwards Compatibility

**Category:** Reliability

**Description:** The system must continue to operate correctly when receiving events from nodes running older (single-byte) firmware. No data loss or processing errors may occur for legacy path hash formats.

**Acceptance Criteria:**

- [ ] Existing test cases with 2-character path hashes continue to pass without modification
- [ ] New test cases with multibyte path hashes pass alongside legacy test cases
- [ ] No database migration is required that would break rollback to the previous version

### REQ-008: Documentation Accuracy

**Category:** Maintainability

**Description:** All documentation referencing path hash format must be updated to reflect the variable-length nature of multibyte path hashes.

**Acceptance Criteria:**

- [ ] `SCHEMAS.md` path hash descriptions updated from "2-character" to "variable-length hex string"
- [ ] Code docstrings and field descriptions in models/schemas updated
- [ ] Example payloads in documentation include at least one multibyte path hash example

## Technical Constraints and Assumptions

### Constraints

- Python 3.13+ (specified by project)
- meshcore_py >= 2.3.0 (already set in `pyproject.toml`)
- SQLite with JSON column for path hash storage (existing schema)
- No breaking changes to the REST API response format

### Assumptions

- The meshcore_py library handles protocol-level backwards compatibility for multibyte path hashes, so MeshCore Hub only needs to ensure its data pipeline accepts variable-length strings
- Path hashes are always valid hex strings (even number of characters)
- The JSON column type in SQLite/SQLAlchemy does not impose length restrictions on individual array element strings
- The `pyproject.toml` dependency has already been bumped to `meshcore>=2.3.0`

## Scope

### In Scope

- Updating Pydantic schema descriptions and validation for variable-length path hashes
- Updating collector handlers and normalizer for multibyte path hashes
- Verifying database storage compatibility (no migration expected)
- Verifying API response compatibility
- Updating web dashboard path hash display if applicable
- Updating `SCHEMAS.md` and code documentation
- Adding/updating tests for multibyte path hashes
- Confirming meshcore_py library handles backwards compatibility

### Out of Scope

- MeshCore firmware changes or device-side configuration
- Adding UI controls for selecting single-byte vs. multibyte mode
- Performance optimization of path hash processing
- Changes to MQTT topic structure or message format
- LetsMesh ingest protocol changes (beyond accepting multibyte values that LetsMesh already provides)

## Suggested Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| MeshCore bindings | meshcore_py >= 2.3.0 | Specified by prompt; provides multibyte path hash support |
| Validation | Pydantic v2 | Existing stack — schema descriptions updated |
| Database | SQLAlchemy 2.0 + SQLite JSON | Existing stack — no migration needed |
| API | FastAPI | Existing stack — no changes to framework |
| Testing | pytest + pytest-asyncio | Existing stack — new test cases for multibyte |
