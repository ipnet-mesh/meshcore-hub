# D22: Node/TypeScript Backend (Fastify)

- **Status:** Locked
- **Iteration:** 7

## Context

The rewrite plan (iterations 1–6) assumed Python (FastAPI + SQLAlchemy + Alembic), matching the current codebase. The §overview.md "What This Document Does NOT Decide" section explicitly stated "we keep Python (3.13+) + FastAPI + SQLAlchemy 2.0 + React 19 + Vite."

Two findings from the iteration-7 ecosystem research challenge this:

1. **The MeshCore packet decoder is TypeScript-primary.** `@michaelhart/meshcore-decoder` (npm, 50 stars, powers the official LetsMesh analyzer) is the original implementation. `meshcoredecoder` (PyPI, 8 stars) is explicitly a port that lags the TS original. The current hub carries ~100 LOC of workaround code (`_enrich_payload_decoded`, `_flatten_control_parsed`) patching fields the Python port omits. Every new MeshCore protocol feature lands in the TS decoder first.

2. **The NATS JetStream Node client is first-party.** `@nats-io/nats-core` + `@nats-io/jetstream` (v3.4.0) is maintained by Synadia with typed consumer APIs, `Nats-Msg-Id` as a standard publish option, and active development. `nats-py` (v2.15.0) is community-maintained with sparse docs and slower feature parity. The ingest pipeline (D4) is the architectural centerpiece — the queue client quality matters.

The operator's constraint: Python and Node/TS are the two languages they can confidently debug. No other language is in scope.

## Decision

**Node/TypeScript backend with Fastify 5.** The rewrite is a single-language stack: TypeScript for the backend, the frontend (already React+TS), and the packet decoder (the primary implementation).

### Library mapping

| Concern | Python (was) | Node/TS (now) | Why |
|---|---|---|---|
| HTTP framework | FastAPI | **Fastify 5** | Schema-based serialization, plugin ecosystem, ~3× Express throughput. NestJS adds DI overhead not needed here. |
| ORM / query builder | SQLAlchemy 2.0 | **Drizzle ORM** | Thin typed SQL layer, excellent `sql` template raw escape hatch. TimescaleDB DDL is raw SQL regardless. |
| Migrations | Alembic | **Drizzle Kit** + raw SQL for extension DDL | `drizzle-kit` handles OLTP tables; hypertable/CAGG/compression DDL is hand-written SQL migrations (both languages require this). |
| Schema validation | Pydantic | **Zod** | Runtime validation + static types from one definition. |
| NATS | nats-py | **@nats-io/nats-core + @nats-io/jetstream** | First-party (Synadia), typed JetStream API, active development. |
| MQTT | paho-mqtt + aiomqtt | **mqtt.js 5.x** | Natively async/await, MQTT 5.0. |
| Redis | redis-py async | **ioredis 5.x** | Battle-tested. |
| SSE | sse-starlette | **@fastify/eventsource** or raw `res.raw` headers | Simple. |
| JWT | python-jose / PyJWT | **jose** | JWT + JWS, HS256/RS256. |
| Session signing | itsdangerous | **jose** (JWS) or custom HMAC | Same mechanism, different library. |
| Password hashing | argon2-cffi | **argon2** (node, native bindings) | argon2id, same algorithm. |
| CLI | Click | **commander** | Ops-only commands (D18). |
| Testing | pytest | **vitest** | Already used for frontend tests. One test runner for the whole stack. |
| Packet decoder | meshcoredecoder (port) | **@michaelhart/meshcore-decoder** (primary) | The original implementation. No more porting lag. |
| OpenAPI generation | FastAPI (built-in) | **@fastify/swagger** + `@fastify/swagger-ui` | Schema-based; Fastify's JSON Schema approach maps to Zod via `fastify-type-provider-zod`. |
| Frontend codegen | orval (unchanged) | orval (unchanged) | Generates typed React Query hooks from any OpenAPI spec. |

### What survives unchanged

The architectural decisions (D1–D21) are **language-agnostic**. They describe:

- NATS subject topology (strings)
- Schema DDL (SQL)
- API contract (OpenAPI)
- Cache invalidation graph (a data structure)
- Auth boundary (JWT claims, middleware resolution)
- Ingest envelope shape (JSON schema)
- Config tiers (env / DB / entities)

The component docs' code examples are **illustrative pseudocode** showing the design pattern. The implementation uses the TS stack above. The design — the shapes, the flows, the contracts — does not change.

### What changes

- The implementation checklist references TS libraries instead of Python ones.
- Code examples in component docs are annotated as illustrative (the patterns translate directly).
- The CLI is `commander`-based instead of Click.
- Tests are vitest instead of pytest (one runner for backend + frontend).
- The Docker image is Node-based instead of Python-based.

## Consequences

**Positive:**

- **Primary decoder implementation.** No more porting lag, no more workaround code. Every MeshCore protocol feature is available immediately. The decoder's TypeScript types flow directly into the ingest envelope types.
- **First-party NATS client.** The ingest pipeline's backbone uses the best-supported JetStream client in any dynamic language. Typed consumer APIs, active Synadia maintenance.
- **One language for the whole stack.** Backend, frontend, decoder, tests — all TypeScript. Domain types can be shared (though orval codegen makes this less critical). One `tsconfig`, one linter, one test runner.
- **mqtt.js is natively async.** No callback-to-async wrapper needed (paho + aiomqtt).

**Negative:**

- **FastAPI's OpenAPI generation is best-in-class.** `@fastify/swagger` works but requires more manual schema annotation. Mitigated by `fastify-type-provider-zod` (Zod schemas → JSON Schema → OpenAPI automatically).
- **Drizzle is younger than SQLAlchemy.** Smaller ecosystem, fewer Stack Overflow answers. Mitigated by the thin abstraction — most queries are raw SQL via the `sql` template, and TimescaleDB DDL is raw SQL regardless.
- **`drizzle-kit` breaks on continuous aggregates** (open issue #2962). Mitigated by writing extension DDL as hand-authored SQL migrations (the plan already does this).
- **The MeshCore operational ecosystem is Python** (packet-capture, meshcoretomqtt). Mitigated by the MQTT protocol being the integration boundary, not the language. The new stack talks MQTT — it doesn't import Python libraries.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Node/TypeScript (Fastify)** (chosen) | Primary decoder, first-party NATS, one-language stack. |
| Python (FastAPI) | Rejected — carries the decoder porting-lag cost and community-maintained NATS client. Best OpenAPI ergonomics, but not enough to offset the two core-library gaps. |
| Go / Rust | Rejected — operator cannot confidently debug in these languages. |
