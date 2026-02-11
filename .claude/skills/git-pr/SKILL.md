---
name: git-pr
description: Create a pull request to main from the current branch. Runs quality checks, commits changes, pushes, and opens a PR via gh CLI. Use when ready to submit work for review.
---

# Git PR

Create a pull request to `main` from the current feature branch.

## Process

### Phase 1: Pre-flight Checks

1. **Verify branch:**

```bash
git branch --show-current
```

   - The current branch must NOT be `main`. If on `main`, tell the user to create a feature branch first (e.g., `/git-branch`).

2. **Check for uncommitted changes:**

```bash
git status
```

   - If there are uncommitted changes, ask the user for a commit message and commit them using the `/git-commit` skill conventions (no Claude authoring details).

### Phase 2: Quality Checks

1. **Determine changed components** by comparing against `main`:

```bash
git diff --name-only main...HEAD
```

2. **Run targeted tests** based on changed files:
   - `tests/test_web/` for web-only changes (templates, static JS, web routes)
   - `tests/test_api/` for API changes
   - `tests/test_collector/` for collector changes
   - `tests/test_interface/` for interface/sender/receiver changes
   - `tests/test_common/` for common models/schemas/config changes
   - Run the full `pytest` if changes span multiple components

3. **Run pre-commit checks:**

```bash
pre-commit run --all-files
```

   - If checks fail and auto-fix files, commit the fixes and re-run until clean.

4. If tests or checks fail and cannot be auto-fixed, report the issues to the user and stop.

### Phase 3: Push and Create PR

1. **Push the branch to origin:**

```bash
git push -u origin HEAD
```

2. **Generate PR content:**
   - **Title**: Derive from the branch name. Convert `feat/add-map-clustering` to `Add map clustering`, `fix/login-error` to `Fix login error`, etc. Keep under 70 characters.
   - **Body**: Generate a summary from the commit history:

```bash
git log main..HEAD --oneline
```

3. **Create the PR:**

```bash
gh pr create --title "{title}" --body "$(cat <<'EOF'
## Summary
{bullet points summarizing the changes}

## Test plan
{checklist of testing steps}
EOF
)"
```

4. **Return the PR URL** to the user.

## Rules

- Do NOT create a PR from `main`.
- Do NOT skip quality checks — tests and pre-commit must pass.
- Do NOT force-push.
- Always target `main` as the base branch.
- Keep the PR title concise (under 70 characters).
- If quality checks fail, fix issues or report to the user — do NOT create the PR with failing checks.
