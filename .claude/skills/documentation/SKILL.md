---
name: documentation
description: Audit and update project documentation to accurately reflect the current codebase. Use when documentation may be outdated, after significant code changes, or when the user asks to review or update docs.
---

# Documentation Audit

Audit and update all project documentation so it accurately reflects the current state of the codebase. Documentation must only describe features, options, configurations, and functionality that actually exist in the code.

## Files to Review

- **README.md** - Project overview, setup instructions, usage examples
- **AGENTS.md** - AI coding assistant guidelines, project structure, conventions
- **.env.example** - Example environment variables

Also check for substantial comments or inline instructions within the codebase that may be outdated.

## Process

1. **Read all documentation files** listed above in full.

2. **Cross-reference against the codebase.** For every documented item (features, env vars, CLI commands, routes, models, directory paths, conventions), search the code to verify:
   - It actually exists.
   - Its described behavior matches the implementation.
   - File paths and directory structures are accurate.

3. **Identify and fix discrepancies:**
   - **Stale/legacy content** — documented but no longer in the code. Remove it.
   - **Missing content** — exists in the code but not documented. Add it.
   - **Inaccurate descriptions** — documented behavior doesn't match implementation. Correct it.

4. **Apply updates** to each file. Preserve existing style and structure.

5. **Verify consistency** across all documentation files — they must not contradict each other.

## Rules

- Do NOT invent features or options that don't exist in the code.
- Do NOT remove documentation for features that DO exist.
- Do NOT change the fundamental structure or style of the docs.
- Do NOT modify CLAUDE.md.
- Focus on accuracy, not cosmetic changes.
- When in doubt, check the source code.
