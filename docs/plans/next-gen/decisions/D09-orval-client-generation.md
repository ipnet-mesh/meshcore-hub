# D09: orval for Generated TypeScript Client

- **Status:** Locked
- **Iteration:** 2 (locked), 6 (spike removed — committed upfront)

## Context

The frontend hand-copies backend types into every page (overview pain F1 — "no generated type layer" from overview.md §4.4; an overview pain-table number, not a review-findings F-number): `NodeTag` defined 3×, `Channel` 5×, `Profile` variants across 5 files. Every schema change forces a manual sync that is easy to miss. The contract (api.md → OpenAPI as the contract) is "OpenAPI generated from the server drives a typed frontend client," but the generator choice was left open.

## Decision

**orval** — committed upfront, no validation spike. Generates typed TanStack Query hooks (`useMessagesQuery`, `useNodeTagsMutation`) plus tag-based invalidation via the `x-invalidates` OpenAPI extension. The mutator config (custom `apiClient` injecting `credentials: 'include'`) controls the fetch client; orval generates the hook signatures and invalidation calls.

**Why no spike (iteration 6):** orval's core value (generated hooks + invalidation tags) maps cleanly to the declarative `ENTITY_INVALIDATION` graph (api.md → Unified cache contract). The main risk (ugly generated code) is mitigated by the mutator override — we control the client, orval just generates signatures. If the output is truly bad, switching to `openapi-fetch` + hand-written hooks is a day's work (the types are identical either way). The spike bought insurance we don't need.

CI gate: the generated client must be up to date with the schema (`make gen-client` + a drift check).

## Consequences

**Positive:** Full type fidelity from server `response_model` → TypeScript; generated hooks eliminate pain-F1's hand-copy drift; invalidation tags mirror the server-side graph automatically. Per-page boilerplate collapses to importing the generated hook.

**Negative:** A codegen step in the build; generated code is a build artifact (not hand-edited). orval's generated hooks can be verbose; the mutator config is a real integration cost.

## Alternatives considered

| Option | Verdict |
|---|---|
| **orval** (chosen) | Types + typed client + generated hooks + tag invalidation; one tool covers the full frontend data layer. |
| openapi-typescript + openapi-fetch | Rejected — types + typed client only; hooks hand-written. More boilerplate. Available as fallback if orval output proves unmaintainable. |
| hey-api | Rejected — strong types but weaker TanStack Query hook generation at decision time. |
| Hand-written types (today's model) | Rejected — overview pain F1 drift is the exact pain point being solved. |
