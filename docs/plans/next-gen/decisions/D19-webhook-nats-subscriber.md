# D19: Webhook Delivery via NATS Core Subscriber

- **Status:** Locked
- **Iteration:** 7 (gap review)

## Context

Today's webhook delivery is a dedicated daemon thread polling an in-memory list every 10ms, dispatching via `httpx.AsyncClient` with exponential backoff (3 retries, 2s/4s/8s). Events are lost on process crash (no persistent queue). Three URL+secret pairs are configured via env vars (`WEBHOOK_ADVERTISEMENT_URL/SECRET`, etc.). A JSONPath-like filter DSL exists in code but is **inert in production** (only reachable from a test-only factory). Dead code: a second synchronous dispatch mechanism (`webhook.py:398-451`) used only in tests.

The ingest redesign (D4, ingest.md) moves the fan-out to NATS: the IngestWorker publishes `events.new.<inst>.{table}` after commit. The SSE endpoint already subscribes to this subject. The §derived-state.md statement that the webhook thread is "folded into the IngestWorker post-commit path" left the actual delivery mechanism undesigned.

## Decision

**A `WebhookWorker` subscribes to `events.new.<inst>.*` (NATS core, non-durable) and dispatches webhooks.** The IngestWorker's post-commit path stays lean: commit → publish `events.new.*` → ack. Webhook delivery is a separate consumer on the same fan-out subject the SSE endpoint uses.

- **Delivery:** `WebhookWorker` subscribes to `events.new.<inst>.>`, checks the Tier-2 webhook settings (URLs, secrets, event-type filters), and dispatches via `undici`/`fetch` with the same retry/backoff semantics as today (3 retries, exponential backoff). Only events that are `is_new` (first sighting) trigger webhooks — the IngestWorker's `events.new.*` notification already carries this flag.
- **Config:** webhook URLs, secrets, event-type filters, and retry tuning are **Tier-2 settings** (D11) — runtime-editable via the Admin UI, propagated via `settings.updated.<inst>.webhooks`. The `WebhookWorker` holds a `SettingsCache` snapshot and reloads on NATS notification.
- **Filter DSL:** the existing JSONPath-like expression is wired into production (today it's test-only). Each webhook config entry carries an optional `filter_expression` evaluated against the event payload before dispatch.
- **Durability:** best-effort, matching today's semantics (in-memory queue, lost on crash). NATS core is non-durable — if the `WebhookWorker` is down, events are missed. This is acceptable: webhooks are an integration convenience, not a source of truth. If durability becomes a requirement later, upgrade to a JetStream durable consumer with a staleness guard (skip events older than a configurable window).
- **Dead code:** the module-level `set_dispatch_callback` / `dispatch_event` / `get_queued_events` mechanism and the test-only `create_webhook_dispatcher_from_config` factory are not carried forward.

## Consequences

**Positive:** The IngestWorker stays lean (no httpx calls on the hot path). Webhook slowness or endpoint downtime doesn't block the ingest ack. Config is runtime-editable (Tier-2 settings) instead of env-var-only. The filter DSL becomes functional. One more small consumer process, but it shares the NATS subscription pattern the SSE endpoint already uses.

**Negative:** Webhook events are lost if the `WebhookWorker` is down (non-durable NATS core). This matches today's behaviour (in-memory queue lost on crash) but is worth documenting. The `WebhookWorker` is another process to deploy and monitor.

## Alternatives considered

| Option | Verdict |
|---|---|
| **NATS core subscriber** (chosen) | Decoupled from ingest; webhook slowness doesn't block ack. Best-effort matches today. |
| IngestWorker post-commit dispatch | Rejected — slow endpoints block the ack; retry/backoff adds complexity to the hot path. |
| JetStream durable consumer | Deferred — at-least-once delivery survives restarts, but needs a staleness guard (7d max_age). Upgrade path if durability becomes a requirement. |
