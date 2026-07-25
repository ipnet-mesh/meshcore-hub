# D06: JWT Auth Boundary — Web-Tier-Issued Token, API-Verified

- **Status:** Locked
- **Iteration:** 2

## Context

Today's auth is two overlapping planes with an implicit trust boundary (S1): direct Bearer tokens for m2m, and OIDC-proxy-injected `X-User-*` headers for browser flows. The trust rests on "only the proxy holds the API key" — it is not cryptographically enforced. Some handlers read `X-User-*` directly off `request.headers`, bypassing the central auth deps (S2). Role-name resolution is duplicated between API and web tier (A8). The §13-D6 question: keep the dual-plane model, harden the header-injection path, or move to a single cryptographically-enforced credential?

## Decision

**Short-lived JWT issued by the web tier, verified at a single API middleware.**

- **Web tier** mints an access JWT (default HS256 signed with `JWT_SESSION_SECRET`; optional RS256 via `JWT_SIGNING_ALG=rs256` + `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` PEM paths) carrying `sub`, `roles`, `role_tier` (pre-resolved), `instance_id`, `type=access`, `iat`, `exp` (+5 minutes), `jti`. Stored in the existing signed `meshcore-session` cookie (7-day sliding renewal via `jose` JWS — same mechanism, updated library). Every login path (local password, OIDC callback — see D12) converges here.
- **API** verifies the JWT at a single `AuthMiddleware`; handlers receive a frozen `Principal` (`user_id`, `roles`, `role_tier`, `instance_id`, `channel_indices` pre-resolved) via `Depends`. **No more `X-User-*` header injection** — the JWT *is* the credential.
- **Direct Bearer (API keys)** remain for CLI/automation; they map to a `Principal` with a fixed role at the same middleware.

## Consequences

**Positive:** One cryptographically-enforced credential model; the API is credential-source-agnostic (it verifies a JWT, never knows *how* the web tier authenticated the user). Fixes S1, S2, A8. The 5-minute access lifetime keeps the stolen-token window tiny; the 7-day cookie makes UX transparent. RS256 option lets multi-service deployments verify with a public key.

**Negative:** The web tier becomes a mandatory component for browser flows (no more direct-browser-to-API with injected headers). Short access tokens force per-request re-mint on the web tier (cheap with HS256, but a real cost). Revocation requires a `jti` denylist or short-expiry patience.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Web-tier-issued JWT** (chosen) | One enforced boundary; multiple login sources (D12) converge cleanly. |
| Header injection (today's model) | Rejected — implicit trust in the proxy; handlers bypass central deps (S2). |
| API-side OIDC (API calls IdP per request) | Rejected — couples the API to the IdP's availability; adds per-request latency; breaks m2m cleanly. |
| Session-only (server-side session store shared between web + API) | Rejected — requires a shared session store between web and API processes; JWT keeps them stateless relative to each other. |
