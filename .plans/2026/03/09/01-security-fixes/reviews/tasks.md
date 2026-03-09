# Task Review

> Phase: `.plans/2026/03/09/01-security-fixes`
> Tasks: `.plans/2026/03/09/01-security-fixes/tasks.yaml`
> PRD: `.plans/2026/03/09/01-security-fixes/prd.md`

## Verdict: PASS

The task list is structurally sound, correctly ordered, and fully covers all 7 PRD requirements. The dependency graph is a valid DAG with no cycles or invalid references. No ordering issues, coverage gaps, vague tasks, or invalid fields were found. Two non-blocking warnings are noted: TASK-006 and TASK-007 (frontend XSS fixes) lack corresponding test tasks, and two pairs of independent tasks share output files but modify independent sections.

## Dependency Validation

### Reference Validity

All dependency references are valid. Every task ID referenced in a `dependencies` list corresponds to an existing task in the inventory.

### DAG Validation

The dependency graph is a valid directed acyclic graph. No cycles detected.

Topological layers:
- **Layer 0 (roots):** TASK-001, TASK-002, TASK-003, TASK-005, TASK-006, TASK-007
- **Layer 1:** TASK-004 (depends on TASK-003), TASK-008 (depends on TASK-001), TASK-009 (depends on TASK-002), TASK-011 (depends on TASK-005)
- **Layer 2:** TASK-010 (depends on TASK-003, TASK-004), TASK-012 (depends on TASK-003, TASK-004)

### Orphan Tasks

No orphan tasks detected. All non-root tasks with dependencies are either terminal test/docs tasks (TASK-008, TASK-009, TASK-010, TASK-011, TASK-012) or integration tasks (TASK-004). Root tasks without dependents (TASK-006, TASK-007) are excluded from orphan detection per the review protocol.

## Ordering Check

No blocking ordering issues detected.

**Observation (non-blocking):** Two pairs of independent tasks share output files:

1. **TASK-004 and TASK-005** both modify `src/meshcore_hub/web/app.py` without a dependency between them. TASK-004 modifies `ProxyHeadersMiddleware` (line ~239) and adds a startup warning, while TASK-005 modifies `_build_config_json` (line ~183). These are independent functions in the same file; no actual conflict exists.

2. **TASK-010 and TASK-011** both modify `tests/test_web/test_app.py` without a dependency between them. Both add new test functions to the same test file. No actual conflict exists.

These are not blocking because neither task creates the shared file — both modify existing files in independent sections. Adding artificial dependencies would unnecessarily serialize parallelizable work.

## Coverage Check

### Uncovered Requirements

All PRD requirements are covered.

### Phantom References

No phantom references detected.

**Coverage summary:** 7 of 7 PRD requirements covered by tasks.

| Requirement | Tasks |
|---|---|
| REQ-001 | TASK-001, TASK-008 |
| REQ-002 | TASK-002, TASK-009 |
| REQ-003 | TASK-003, TASK-004, TASK-010, TASK-012 |
| REQ-004 | TASK-005, TASK-011 |
| REQ-005 | TASK-006, TASK-007 |
| REQ-006 | TASK-001, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-010, TASK-011, TASK-012 |
| REQ-007 | TASK-002, TASK-004, TASK-009 |

## Scope Check

### Tasks Too Large

No tasks flagged as too large. No task has `estimated_complexity: large`.

### Tasks Too Vague

No tasks flagged as too vague. All tasks have detailed descriptions (>50 chars), multiple testable acceptance criteria, and specific file paths in `files_affected`.

### Missing Test Tasks

Two implementation tasks lack corresponding test tasks:

- **TASK-006** (Fix stored XSS in admin node-tags page) — modifies `admin/node-tags.js` but no test task verifies the XSS fix in this JavaScript file. The acceptance criteria include XSS payload testing, but no automated test is specified. This is a frontend JavaScript change where manual verification or browser-based testing may be appropriate.

- **TASK-007** (Fix stored XSS in admin members page) — modifies `admin/members.js` but no test task verifies the XSS fix in this JavaScript file. Same reasoning as TASK-006.

**Note:** These are warnings, not blocking issues. The project's test infrastructure (`tests/test_web/`) focuses on server-side rendering and API responses. Client-side JavaScript XSS fixes are typically verified through acceptance criteria rather than automated unit tests.

### Field Validation

All tasks have valid fields:

- **Roles:** All `suggested_role` values are valid (`python`, `frontend`, `docs`).
- **Complexity:** All `estimated_complexity` values are valid (`small`, `medium`).
- **Completeness:** All 12 tasks have all required fields (`id`, `title`, `description`, `requirements`, `dependencies`, `suggested_role`, `acceptance_criteria`, `estimated_complexity`, `files_affected`). All list fields have at least one entry.
