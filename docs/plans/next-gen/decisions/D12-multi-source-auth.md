# D12: Multi-Source Auth — Local Passwords + Optional OIDC

- **Status:** Locked
- **Iteration:** 4

## Context

Today interactive login is OIDC-only (with an API-key plane for m2m). That requires every deployment — including the smallest community operator with no identity provider — to stand up an OIDC IdP before the UI is usable. The question (auth.md; raised in iteration 4 by the user): offer a built-in local password source so deployments without an IdP still work, while keeping OIDC optional for orgs that want SSO. The D6 JWT boundary is what makes this clean: every source converges on one JWT issuance, so the API stays credential-source-agnostic.

## Decision

**Three credential sources, all producing the same JWT (D6):**

| Source | When | Always available? |
|---|---|---|
| **Local password store** (argon2id, `local_users` table) | Small/community deployments with no IdP — the "just works" path | Yes — default |
| **OIDC/OAuth2** | Org/multi-user deployments wanting SSO | Optional — configure if you have an IdP |
| **API keys** (direct Bearer) | CLI, scripts, m2m | Yes — for automation |

`AUTH_MODE` selects which interactive sources the login page offers. It is a Tier-1 env var in single-tenant mode (because it affects which bootstrap credentials are required at first boot); in multi-tenant mode (D21, Phase 7) it becomes a **per-tenant** setting (`tenant_oidc_configs.auth_mode`) with the env var as the platform default:

- `local` — username/password form only. Zero external dependencies.
- `oidc` — "Sign in with SSO" button only. For orgs that mandate the IdP.
- **`hybrid` (default)** — both: the login page shows the OIDC button *and* the username/password form. Operators pick per user.

**Multi-tenant evolution (D21).** A single global `AUTH_MODE`/IdP would force every self-provisioned tenant into the platform operator's auth choice — contradicting self-service. So in Phase 7 the IdP config *and* `auth_mode` move to the per-tenant `tenant_oidc_configs` table (multi-tenancy.md §6): a community tenant runs local passwords, an enterprise tenant points at their own Okta, both on one platform. The Tier-1 `OIDC_CLIENT_*`/`AUTH_MODE` vars survive only as **platform-level defaults** (the fallback when a tenant hasn't configured their own). The one thing that stays irreducibly platform-wide is the JWT/session signing key (`JWT_SESSION_SECRET`, renamed from `OIDC_SESSION_SECRET` — it was never OIDC config): one key signs for all tenants, and the API trusts the `instance_id` claim because the platform signed it.

A `local_users` row links to a `user_profiles` row (adoptions, tags, route ownership work unchanged — keyed on `user_profile.id`). The profile's `user_id` is namespaced `local:<username>` to avoid colliding with OIDC `sub` claims. Password hashing: argon2id (`argon2` npm package, native bindings), parameterised at install time. Rate limiting: `failed_attempts` + `locked_until` give exponential lockout (5 → 15s, 10 → 5m, 20 → 1h) without Redis. Bootstrap admin via `ADMIN_USERNAME`/`ADMIN_PASSWORD` env, `admin create-user` CLI, or the first-run setup wizard (auth.md → First-run setup wizard). Local + OIDC users share one Users management page.

## Consequences

**Positive:** Zero-dependency default deployment — the smallest operator runs the stack and logs in without an IdP. The D6 JWT boundary means adding/removing credential sources later doesn't touch the API. Argon2id + exponential lockout is the modern password-store baseline. One Users admin page manages both sources.

**Negative:** Two code paths to maintain (local verify + OIDC callback) — though both converge on JWT issuance. Local password storage is a security responsibility (hashing, lockout, rotation) that OIDC-only avoided. The `AUTH_MODE` env var is Tier-1 in single-tenant mode because it gates bootstrap, so changing the platform default requires a restart; the per-tenant `auth_mode` (Phase 7) is a runtime DB setting and needs no restart.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Multi-source, `hybrid` default** (chosen) | OIDC optional; zero-dependency default; one JWT boundary. |
| OIDC-only (today's model) | Rejected — forces every deployment to run an IdP; blocks the community-operator use case. |
| Local-only (drop OIDC) | Rejected — loses SSO for org/multi-user deployments; regresses an existing capability. |
| Per-instance auth mode in DB (not env) | Rejected as the *single-tenant bootstrap* mechanism (auth mode gates which bootstrap credentials are required, so it must predate DB reachability) — but **adopted for multi-tenant runtime** in Phase 7 (D21): `tenant_oidc_configs.auth_mode`, with the env var as platform default. |
