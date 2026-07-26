# D23: Test Pyramid & Coverage Policy (vitest + Playwright, CI-gated)

- **Status:** Locked
- **Iteration:** 9

## Context

The plan to this point specified **acceptance gates only** — the phase exit criteria in
[testing.md](../testing.md) ("diff = 0 over a 24h shadow run", "p95 < 200ms", "a cross-instance
query returns 0 rows"). Those are correctness and performance gates observed against a running
system; several are slow (the 5-day parallel-stack window, D14) or one-off (the D5 benchmark).
None of them is a fast, repeatable regression suite that runs on every change, and nothing in the
plan required that a rewritten component ship with automated tests.

D22 already locks **vitest** as the single test runner for backend and frontend, but only as a
dev-loop command ([infrastructure.md → Development workflow](../components/infrastructure.md#development-workflow))
— not as a layered strategy with a coverage obligation.

Two more inputs shape this:

1. **`code-warts.md` TQ1** flags that the current repo's E2E auth is *forged, not logged in* —
   no mock IdP exists, so specs mint a signed session cookie and the real login flow goes
   untested. The test surface diverges from production auth. The rewrite is the chance to fix this.
2. **The rewrite is greenfield + a language switch (D22).** With no historical backfill,
   correctness across the whole feature surface must be proven by tests and the parallel-stack
   window rather than by years of production hardening ([phasing.md → Strategy note](../phasing.md#strategy-note--scope-realism-f13)).
   A regression suite is what keeps that surface from rotting during the build-out.

## Decision

**Every rewritten component and every piece of business logic ships with automated tests at the
appropriate layer, and the suite is required to pass in CI.** No logic merges untested. Coverage
is **qualitative** — there is deliberately **no numeric coverage floor**, to avoid low-value tests
written to satisfy a percentage (see Alternatives).

### The pyramid

| Layer | Runner | Infra | Owns |
|---|---|---|---|
| **Unit** | vitest | none | Pure logic: classifier table, dedup hash, `computeQualityAvg`, spam-score wrapper, cache-key builder, `apply_visibility`, the `meshcore.ingest.v1` envelope Zod schema, webhook filter DSL, `PacketFields`. |
| **Integration** | vitest | dev-compose / throwaway Postgres+NATS+Redis | DB- and bus-touching paths: Drizzle repositories, RLS enforcement (`SET LOCAL app.instance_id`), the `@cached` decorator + declarative invalidation graph, `IngestWorker` batch-commit + ack ordering, `ChannelKeyCache`/`ObserverAllowlistCache` reload, `SettingsCache`, API handlers via Fastify `inject`. |
| **Frontend component** | vitest + Testing Library | jsdom | `useEventStream`, generated-client wrappers, admin pages (Settings/Users/Pages/Observers), chart helpers (`averageRouteTier` threshold sync), login rendering per `auth_mode`. |
| **E2E** | Playwright (headless Chromium) | throwaway stack (own Postgres, isolated volumes) | User-facing flows: registration → login → admin → observer allowlist; SSE-driven live updates; custom pages; settings. |

One runner (vitest) covers the first three layers per D22; Playwright is the only second runner
and only for browser E2E.

### E2E auth — real login, forged only where unavoidable

Closing TQ1: E2E specs **exercise the real local-login flow** (the `local_users` argon2id path,
D12) rather than minting a session out of band. Session minting/forging is permitted **only** for
paths that cannot be automated headlessly — the OIDC callback (D12), where no mock IdP exists.
Where a session is forged, the spec directory documents it, so the divergence from production
auth stays visible instead of silent.

### Relationship to the exit criteria

The pyramid and the [phase exit criteria](../testing.md) are **complementary, not the same axis**:

- **Pyramid** = fast, deterministic, CI-runnable regression tests authored alongside the code.
  They prove a component still behaves correctly on every change.
- **Exit criteria** = acceptance gates, some of which are slow runtime observations (the 5-day
  parallel-stack diff, D14; live-load throughput; first-CAGG-bucket timing) that no unit test can
  reproduce. They prove a *phase* is correct and performant enough to ship.

**A phase is done when its checkboxes are ticked, its automated tests pass in CI, and its exit
criteria pass.** The pyramid does not replace the exit criteria, and the exit criteria do not
replace the pyramid.

## Consequences

**Positive:**

- **Regression safety during a long build-out.** The greenfield + language-switch surface
  (19 tables, ~13 routers, the full SPA) is held in check by tests that run on every change, not
  only at phase boundaries.
- **Auth is tested for real.** E2E drives the actual login flow; the forged-session divergence is
  confined to OIDC and documented, instead of being the default.
- **One CI gate, fast feedback.** vitest unit + component tests run in seconds with no infra;
  integration tests spin up the dev-compose dependencies; Playwright runs against a throwaway
  stack. Each layer fails fast at the level where the bug lives.
- **No vanity metric.** Qualitative coverage avoids the well-known failure mode of tests written
  to hit a percentage that assert nothing meaningful.

**Negative:**

- **CI infrastructure cost.** Integration + E2E need real Postgres/TimescaleDB, NATS, Redis, and a
  browser binary in CI. Mitigated by reusing the existing throwaway-compose + deterministic-seed
  pattern from the current `e2e/` suite, and by keeping the bulk of tests at the infra-free unit
  layer.
- **Test maintenance is now a standing obligation.** Every feature PR carries test changes. That is
  the point, but it is real ongoing cost.
- **No single number to report.** Without a coverage floor, "are we covered?" is answered by
  review (does this logic have a test?) rather than a dashboard. Acceptable given the qualitative
  policy; revisit only if untested logic keeps slipping through review.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Qualitative, CI-required, no % floor** (chosen) | Forces tests where logic lives without incentivising junk tests to hit a number. |
| Numeric coverage floor (e.g. 80% lines) | Rejected — a hard percentage encourages low-value assertion-free tests and becomes the target rather than the measure. Reconsider only if review repeatedly misses untested logic. |
| Exit criteria only (the prior plan) | Rejected — acceptance gates are slow and phase-boundary; they give no per-change regression safety and required no per-component tests. |
| Keep forged E2E auth everywhere (current repo pattern) | Rejected — leaves the real login flow untested (TQ1). Forging is kept only for the un-automatable OIDC path. |
