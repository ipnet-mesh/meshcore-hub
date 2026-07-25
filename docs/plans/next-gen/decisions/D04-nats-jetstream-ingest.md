# D04: NATS JetStream for Ingest Queue + Realtime Fan-Out

- **Status:** Locked
- **Iteration:** 2

## Context

Today's ingest is a single-threaded MQTT callback with no backpressure (W1): one slow DB write on the paho thread stalls all topics, and there is no internal queue to absorb bursts. The `Subscriber(LetsMeshNormalizer)` god-class (P1) mixes decode, dispatch, persistence, and webhook fan-out on one thread. The §7 redesign splits receipt from write (`MqttIngester` → durable queue → `IngestWorker` pool), which requires picking the queue. The §13-D4 question also covered realtime fan-out for the SSE endpoint (D7): one tool for both roles, or two?

## Decision

**NATS 2.10+ JetStream** owns both roles:

1. **Durable ingest stream** (`INGEST-<inst>`, JetStream, `WorkQueuePolicy`, subject `meshcore.ingest.<inst>.*`). `MqttIngester` produces decoded envelopes; the `IngestWorker` consumer group (`durable="workers"`, `ack_explicit`) reads them. Server-side dedup via the `Nats-Msg-Id` header set to the packet's `wire_hash` within a `duplicate_window = 5m`. `max_age = 7d` (replay window for worker restarts), `storage = file`, `retention = limits`.
2. **Realtime fan-out bus** (`events.new.<inst>.{table}`, core non-durable pub/sub). Workers publish a small "event persisted" notification after commit; the API's SSE endpoint subscribes and pushes to clients.

Redis narrows to optional API response cache only — it is no longer on the ingest or fan-out paths and may be omitted entirely.

## Consequences

**Positive:** One tool covers durable ingest + fan-out (vs Redis Streams + a separate bus). Bursts are absorbed by JetStream; a DB stall no longer stalls MQTT (W1). `Nats-Msg-Id` dedup suppresses MQTT redelivery with zero double-inserts. Worker pool scales horizontally via consumer groups. Redis becomes optional, dropping a hard runtime dependency for small deployments.

**Negative:** NATS is now first-class infrastructure — the default Compose stack gains a `nats` service with a JetStream persistence volume that operators must back up. One more moving part vs the in-process queue model.

## Alternatives considered

| Option | Verdict |
|---|---|
| **NATS JetStream** (chosen) | Single binary; built-in persistence, dedup, consumer groups, core pub/sub for fan-out. One tool, two roles. |
| Redis Streams | Rejected — forces Redis onto the critical ingest path; doesn't double as the fan-out bus as cleanly. |
| Kafka | Rejected — operationally heavy for this scale; NATS covers the same guarantees at a fraction of the ops cost. |
| Postgres-based queue (`SELECT FOR UPDATE SKIP LOCKED`) | Rejected — puts more load on the DB the redesign is trying to protect. |
