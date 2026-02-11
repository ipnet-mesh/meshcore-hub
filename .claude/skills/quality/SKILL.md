---
name: quality
description: Run the full test suite, pre-commit checks, and re-run tests to ensure code quality. Fixes any issues found. Use after code changes, before commits, or when the user asks to check quality.
---

# Quality Check

Run the full quality pipeline: tests, pre-commit checks, and a verification test run. Fix any issues discovered at each stage.

## Prerequisites

Before running checks, ensure the environment is ready:

1. Check for `.venv` directory — create with `python -m venv .venv` if missing.
2. Activate the virtual environment: `source .venv/bin/activate`
3. Install dependencies: `pip install -e ".[dev]"`

## Process

### Phase 1: Initial Test Run

Run the full test suite to establish a baseline:

```bash
pytest
```

- If tests **pass**, proceed to Phase 2.
- If tests **fail**, investigate and fix the failures before continuing. Re-run the failing tests to confirm fixes. Then proceed to Phase 2.

### Phase 2: Pre-commit Checks

Run all pre-commit hooks against the entire codebase:

```bash
pre-commit run --all-files
```

- If all checks **pass**, proceed to Phase 3.
- If checks **fail**:
  - Many hooks (black, trailing whitespace, end-of-file) auto-fix issues. Re-run `pre-commit run --all-files` to confirm auto-fixes resolved the issues.
  - For remaining failures (flake8, mypy, etc.), investigate and fix manually.
  - Re-run `pre-commit run --all-files` until all checks pass.
  - Then proceed to Phase 3.

### Phase 3: Verification Test Run

Run the full test suite again to ensure pre-commit fixes (formatting, import sorting, etc.) haven't broken any functionality:

```bash
pytest
```

- If tests **pass**, the quality check is complete.
- If tests **fail**, the pre-commit fixes introduced a regression. Investigate and fix, then re-run both `pre-commit run --all-files` and `pytest` until both pass cleanly.

## Rules

- Always run the FULL test suite (`pytest`), not targeted tests.
- Always run pre-commit against ALL files (`--all-files`).
- Do NOT skip or ignore failing tests — investigate and fix them.
- Do NOT skip or ignore pre-commit failures — investigate and fix them.
- Do NOT modify test assertions to make tests pass unless the test is genuinely wrong.
- Do NOT disable pre-commit hooks or add noqa/type:ignore unless truly justified.
- Fix root causes, not symptoms.
- If a fix requires changes outside the scope of a simple quality fix (e.g., a design change), report it to the user rather than making the change silently.
