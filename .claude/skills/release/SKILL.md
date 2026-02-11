---
name: release
description: Full release workflow — quality gate, semantic version tag, push, and GitHub release. Use when ready to cut a new release from main.
---

# Release

Run the full release workflow: quality checks, version tagging, push, and GitHub release creation.

## Arguments

The user may optionally provide a version number (e.g., `/release 1.2.0`). If not provided, one will be suggested based on commit history.

## Process

### Phase 1: Pre-flight Checks

1. **Verify on `main` branch:**

```bash
git branch --show-current
```

   - Must be on `main`. If not, tell the user to switch to `main` first.

2. **Verify working tree is clean:**

```bash
git status --porcelain
```

   - If there are uncommitted changes, tell the user to commit or stash them first.

3. **Pull latest:**

```bash
git pull origin main
```

### Phase 2: Quality Gate

1. **Run full test suite:**

```bash
pytest
```

2. **Run pre-commit checks:**

```bash
pre-commit run --all-files
```

3. If either fails, report the issues and stop. Do NOT proceed with a release that has failing checks.

### Phase 3: Determine Version

1. **Get the latest tag:**

```bash
git describe --tags --abbrev=0 2>/dev/null || echo "none"
```

2. **List commits since last tag:**

```bash
git log {last_tag}..HEAD --oneline
```

   If no previous tag exists, list the last 20 commits:

```bash
git log --oneline -20
```

3. **Determine next version:**
   - If the user provided a version, use it.
   - Otherwise, suggest a version based on commit prefixes:
     - Any commit starting with `feat` or `Add` → **minor** bump
     - Only `fix` or `Fix` commits → **patch** bump
     - If no previous tag, suggest `0.1.0`
   - Present the suggestion and ask the user to confirm or provide a different version.

### Phase 4: Tag and Release

1. **Create annotated tag:**

```bash
git tag -a v{version} -m "Release v{version}"
```

2. **Push tag to origin:**

```bash
git push origin v{version}
```

3. **Create GitHub release:**

```bash
gh release create v{version} --title "v{version}" --generate-notes
```

4. **Report** the release URL to the user.

## Rules

- MUST be on `main` branch with a clean working tree.
- MUST pass all quality checks before tagging.
- Tags MUST follow the `v{major}.{minor}.{patch}` format (e.g., `v1.2.0`).
- Always create an annotated tag, not a lightweight tag.
- Always confirm the version with the user before tagging.
- Do NOT skip quality checks under any circumstances.
- Do NOT force-push tags.
