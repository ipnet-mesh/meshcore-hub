# D11: Three-Tier Config Model (Env / DB-Settings / Entities)

- **Status:** Locked
- **Iteration:** 4

## Context

Today ~200 env vars configure everything from branding to tuning to feature flags, and changing any of them — even an announcement banner — requires a container restart. The pain is acute for community-operated deployments where the operator isn't always the deployer: an incident-comms banner shouldn't be a git commit + redeploy. The §8.8 question: move config into a DB-backed UI-editable store, and if so, where do env vars still win? The user suggestion in iteration 4 was to move config into the API/UI.

## Decision

**Three-tier config model.** A setting is in exactly one tier, determined by *when it can change*:

- **Tier 1 — Bootstrap (env vars, immutable at runtime, ~15–20 vars).** Needed to start the process or reach the DB/IdP: `DATABASE_URL`, `NATS_URL`, `MQTT_HOST/...`, `REDIS_HOST/...`, `OIDC_CLIENT_ID/SECRET/DISCOVERY`, `JWT_SESSION_SECRET`, `API_HOST/PORT`, `LOG_LEVEL`, `INSTANCE_NAME`. Rule of thumb: if changing it requires reconnecting to an external system or re-authenticating, it is Tier 1. Secrets stay here (or in a secret manager) — never in a DB backup. In multi-tenant mode (D21) the OIDC/`AUTH_MODE` vars are **platform defaults only** — each tenant overrides them via `tenant_oidc_configs` (a DB entity, multi-tenancy.md §6); `JWT_SESSION_SECRET` stays platform-wide because it signs for all tenants.
- **Tier 2 — Runtime settings (DB-backed `settings` table, UI-editable, cached + NATS-invalidated).** Branding/content, feature flags, tuning (retention, spam thresholds, evaluator intervals, cache TTLs), webhooks, radio display. Exposed via `GET/PUT /api/v1/settings/{category}`; per-category Zod validation on write; defaults ship as a seed migration; cross-service invalidation via NATS `settings.updated.<inst>.{category}`. Env vars override the seed at first boot only, then the DB is authoritative.
- **Tier 3 — First-class entities (already DB-backed, unchanged).** Channels, routes, tags, profiles. Custom pages move to DB in D20 (previously file-based).

## Consequences

**Positive:** Operators tune spam thresholds, toggle feature flags, change branding, all at runtime without a restart — fits the community-operated model. The `__APP_CONFIG__` per-request rebuild (F5) collapses into `GET /api/v1/config` reading the cached snapshot. Config changes are auditable (`updated_by`, `updated_at`) and revertible, unlike env-var git commits. Aligns naturally with the static-shell design (§9.4).

**Negative:** Split-brain risk between env and DB (mitigated by the explicit three-tier rule + small Tier-1 allowlist). Cross-service propagation lag must be documented per category (branding = next request; feature flags = next packet for the collector; tuning = next worker tick). Bad values need an escape hatch (the `settings reset --category=...` CLI — see D18).

## Alternatives considered

| Option | Verdict |
|---|---|
| **Three-tier** (chosen) | Explicit line-drawing by when-can-it-change; restart-free for runtime config. |
| Keep all env vars (today's model) | Rejected — restart-for-an-announcement is the current acute pain; ~200 vars is unmanageable. |
| Full DB-backed (no tiers) | Rejected — bootstrap settings (DB URL, IdP config) can't be read from the DB; secrets shouldn't sit in a DB backup. |
| File-based config (YAML/TOML) | Rejected — still requires a restart to change; no UI path for operators. |
