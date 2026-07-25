# D12: Multi-Source Auth — Local Passwords + Optional OIDC

- **Status:** Locked
- **Iteration:** 4

## Context

Today interactive login is OIDC-only (with an API-key plane for m2m). That requires every deployment — including the smallest community operator with no identity provider — to stand up an OIDC IdP before the UI is usable. The §8.3 question (raised in iteration 4 by the user): offer a built-in local password source so deployments without an IdP still work, while keeping OIDC optional for orgs that want SSO. The D6 JWT boundary is what makes this clean: every source converges on one JWT issuance, so the API stays credential-source-agnostic.

## Decision

**Three credential sources, all producing the same JWT (D6):**

| Source | When | Always available? |
|---|---|---|
| **Local password store** (argon2id, `local_users` table) | Small/community deployments with no IdP — the "just works" path | Yes — default |
| **OIDC/OAuth2** | Org/multi-user deployments wanting SSO | Optional — configure if you have an IdP |
| **API keys** (direct Bearer) | CLI, scripts, m2m | Yes — for automation |

`AUTH_MODE` (Tier-1 env var, because it affects which bootstrap credentials are required) selects which interactive sources the login page offers:

- `local` — username/password form only. Zero external dependencies.
- `oidc` — "Sign in with SSO" button only. For orgs that mandate the IdP.
- **`hybrid` (default)** — both: the login page shows the OIDC button *and* the username/password form. Operators pick per user.

A `local_users` row links to a `user_profiles` row (adoptions, tags, route ownership work unchanged — keyed on `user_profile.id`). The profile's `user_id` is namespaced `local:<username>` to avoid colliding with OIDC `sub` claims. Password hashing: argon2id (`argon2` npm package, native bindings), parameterised at install time. Rate limiting: `failed_attempts` + `locked_until` give exponential lockout (5 → 15s, 10 → 5m, 20 → 1h) without Redis. Bootstrap admin via `ADMIN_USERNAME`/`ADMIN_PASSWORD` env, `admin create-user` CLI, or the first-run setup wizard (§20.8). Local + OIDC users share one Users management page.

## Consequences

**Positive:** Zero-dependency default deployment — the smallest operator runs the stack and logs in without an IdP. The D6 JWT boundary means adding/removing credential sources later doesn't touch the API. Argon2id + exponential lockout is the modern password-store baseline. One Users admin page manages both sources.

**Negative:** Two code paths to maintain (local verify + OIDC callback) — though both converge on JWT issuance. Local password storage is a security responsibility (hashing, lockout, rotation) that OIDC-only avoided. The `AUTH_MODE` setting is Tier-1 (env var) because it gates bootstrap, so changing it requires a restart.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Multi-source, `hybrid` default** (chosen) | OIDC optional; zero-dependency default; one JWT boundary. |
| OIDC-only (today's model) | Rejected — forces every deployment to run an IdP; blocks the community-operator use case. |
| Local-only (drop OIDC) | Rejected — loses SSO for org/multi-user deployments; regresses an existing capability. |
| Per-instance auth mode in DB (not env) | Rejected — auth mode gates which bootstrap credentials are required, so it must be available before the DB is reachable. |
