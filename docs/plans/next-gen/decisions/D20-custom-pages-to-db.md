# D20: Custom Pages Move to DB

- **Status:** Locked
- **Iteration:** 7 (gap review)

## Context

Today's custom pages are file-based: markdown files with YAML frontmatter in `$CONTENT_HOME/pages/*.md`, read at startup by `PageLoader` into an in-memory dict, served via the web tier (`GET /spa/pages/{slug}` → JSON), rendered client-side with react-markdown. Nav metadata is injected into `window.__APP_CONFIG__.custom_pages`. No DB involvement. D11 incorrectly listed custom pages as "already DB-backed" — they are file-based.

The three-tier config model (D11) puts first-class entities in Tier 3. Custom pages are operator-authored content with nav metadata (title, slug, menu_order, enabled) — they fit the Tier-3 entity pattern (like channels, routes, tags) more than the Tier-1 env-var pattern. File-based storage means no admin UI, no runtime changes without a volume edit + reload, and no API-level CRUD.

## Decision

**Custom pages become a DB-backed Tier-3 entity** with a CRUD API and an admin UI page. The file-based `CONTENT_HOME` loader is not carried forward.

```sql
CREATE TABLE custom_pages (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug         text NOT NULL,
  title        text NOT NULL,
  content      text NOT NULL DEFAULT '',        -- markdown body
  menu_order   int NOT NULL DEFAULT 100,
  enabled      boolean NOT NULL DEFAULT true,
  instance_id  uuid NOT NULL REFERENCES instances(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (instance_id, slug)
);
```

- **API:** `GET /api/v1/pages` (public list, enabled only, sorted by `menu_order`), `GET /api/v1/pages/{slug}` (public detail), `POST/PUT/DELETE /api/v1/pages` (admin CRUD). Response shape: `{slug, title, content, menu_order, enabled}`.
- **Frontend:** `CustomPage.tsx` fetches from the API instead of `/spa/pages/{slug}`. Nav items come from `/api/v1/config` (which includes the enabled pages list) instead of `window.__APP_CONFIG__`. The react-markdown rendering pipeline is unchanged.
- **Config bootstrap:** a one-time `db import-config` step can seed pages from a `CONTENT_HOME` directory for operators migrating from the old stack (the export-config bundle includes a `custom_pages` array read from the old `PageLoader`). After import, the DB is authoritative.
- **Cache invalidation:** mutations invalidate the `pages` + `config` namespaces (nav metadata changes).

## Consequences

**Positive:** Runtime-editable via the Admin UI — operators add/edit/remove pages without touching the filesystem. Fits the D11 Tier-3 entity model. The `/api/v1/config` endpoint serves the nav list, aligning with the static-shell design (no per-request `__APP_CONFIG__` inlining). CRUD API enables future extensions (per-page visibility, i18n content, revision history).

**Negative:** One more table, one more API router, one more admin page. Operators who today edit markdown files in a volume must use the UI (or the API) instead. The `CONTENT_HOME` env var is retired — a workflow change for file-oriented operators.

## Alternatives considered

| Option | Verdict |
|---|---|
| **DB-backed Tier-3 entity** (chosen) | Runtime-editable, admin-UI-managed, fits D11. |
| Stay file-based (`CONTENT_HOME`) | Rejected — no admin UI, no runtime changes, contradicts the D11 "already DB-backed" framing. Fits rarely-changing content, but the UI path is strictly better for community operators. |
| Hybrid (file + DB merged) | Rejected — two sources of truth = "which wins?" ambiguity (the exact problem D18 kills for config). |
