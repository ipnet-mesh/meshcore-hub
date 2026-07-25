# D07: SSE for Realtime Fan-Out (Polling as Fallback)

- **Status:** Locked
- **Iteration:** 2

## Context

Today's "realtime" is polling-only (F3): every live page runs a redundant client (TanStack) + server (Redis/ETag) cache, and every poll round-trips even on 304. There is no `/ws` or SSE anywhere. The §8.6 question: add WebSocket, SSE, or stay polling? Live pages (Messages, Packets, Dashboard activity) need instant updates; the 30s poll is the source of the "feels stale" complaint.

## Decision

**Server-Sent Events** at `GET /api/v1/events/stream`, fed from NATS core pub/sub (`events.new.<inst>.{table}` — see D4). One HTTP connection per tab. The API subscribes to the instance's `events.new` subjects; per-event channel-visibility is enforced against the resolved `Principal.channel_indices`. A 15s heartbeat keeps proxies from killing idle connections. Event types include `message.new`, `advertisement.new`, `raw_reception.new`, `route.updated`, `settings.updated`.

**Backpressure:** the NATS subscription uses a bounded pending-messages limit (~256); if a client can't keep up, messages are dropped and TanStack Query's `refetchOnReconnect` plus the existing 30s poll recover. **Polling remains as the safety-net fallback** — SSE is primary, polling is secondary, not the reverse.

## Consequences

**Positive:** SSE is plain HTTP — no upgrade handshake, plays nice with reverse proxies, one connection per tab. The `useEventStream` hook patches the TanStack Query cache optimistically for instant updates; the 30s poll catches anything missed on disconnect. A `settings.updated` event invalidates the config query across all open tabs within seconds (replaces "reload to see the announcement").

**Negative:** One long-lived connection per tab consumes a server file descriptor + a NATS subscription; horizontal API scaling requires either sticky sessions or a shared NATS subscription model. SSE is unidirectional (server → client) — fine here, but a future bidirectional need would require WebSocket.

## Alternatives considered

| Option | Verdict |
|---|---|
| **SSE** (chosen) | Plain HTTP, proxy-friendly, unidirectional matches the use case; one connection per tab. |
| WebSocket | Rejected — upgrade handshake adds proxy complexity; bidirectionality is unused. |
| Polling only (today's model) | Rejected — 30s staleness on live pages; round-trips even on 304. |
| Long polling | Rejected — more complex than SSE for the same unidirectional fan-out. |
