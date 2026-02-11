---
name: git-branch
description: Create a new branch from latest main with the project's naming convention (feat/fix/chore). Use when starting new work on a feature, bug fix, or chore.
---

# Git Branch

Create a new branch from the latest `main` branch using the project's naming convention.

## Arguments

The user may provide arguments in the format: `<type>/<description>`

- `type` — one of `feat`, `fix`, or `chore`
- `description` — short kebab-case description (e.g., `add-map-clustering`)

If not provided, ask the user for the branch type and description.

## Process

1. **Fetch latest main:**

```bash
git fetch origin main
```

2. **Determine branch name:**

   - If the user provided arguments (e.g., `/git-branch feat/add-map-clustering`), use them directly.
   - Otherwise, ask the user for:
     - **Branch type**: `feat`, `fix`, or `chore`
     - **Short description**: a brief kebab-case slug describing the work
   - Construct the branch name as `{type}/{slug}` (e.g., `feat/add-map-clustering`).

3. **Create and switch to the new branch:**

```bash
git checkout -b {branch_name} origin/main
```

4. **Confirm** by reporting the new branch name to the user.

## Rules

- Branch names MUST follow the `{type}/{slug}` convention.
- Valid types are `feat`, `fix`, and `chore` only.
- The slug MUST be kebab-case (lowercase, hyphens, no spaces or underscores).
- Always branch from `origin/main`, never from the current branch.
- Do NOT push the branch — just create it locally.
