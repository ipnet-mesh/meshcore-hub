# Webhooks

The collector can forward certain events to external HTTP endpoints. This is useful for integrating MeshCore Hub with external systems, notification services, or custom processing pipelines.

## Configuration

Webhook behaviour is configured via `WEBHOOK_*` environment variables. For the full variable reference (URLs, secrets, timeout, retries, backoff), see [configuration.md → Webhooks](configuration.md#webhooks). The sections below describe how the configured values behave.

### URL Routing

- `WEBHOOK_MESSAGE_URL` receives **both** channel and direct message events unless overridden.
- `WEBHOOK_CHANNEL_MESSAGE_URL` overrides the URL for channel messages only.
- `WEBHOOK_DIRECT_MESSAGE_URL` overrides the URL for direct messages only.

### Secrets

Each webhook URL can optionally have a corresponding secret. When configured, the secret is sent as the `X-Webhook-Secret` HTTP header, allowing the receiving endpoint to verify the request origin.

### Retries

Failed webhook deliveries are retried with exponential backoff controlled by `WEBHOOK_MAX_RETRIES` (default `3`) and `WEBHOOK_RETRY_BACKOFF` (default `2.0`). With the defaults, retries occur at approximately 2s, 4s, and 8s.

## Payload Format

All webhooks send a JSON POST request with the following structure:

```json
{
  "event_type": "advertisement",
  "public_key": "abc123...",
  "payload": { ... }
}
```

### Event Types

| Event Type        | Trigger                          | Payload Content              |
| ----------------- | -------------------------------- | ---------------------------- |
| `advertisement`   | Node advertisement received      | Advertisement event data     |
| `channel_message` | Channel message received         | Channel message event data   |
| `direct_message`  | Direct message received          | Direct message event data    |

### Example: Advertisement Webhook

```bash
# .env
WEBHOOK_ADVERTISEMENT_URL=https://example.com/webhook
WEBHOOK_ADVERTISEMENT_SECRET=my-secret-key
```

### Example: Separate Channel and Direct Message Webhooks

```bash
# .env
WEBHOOK_CHANNEL_MESSAGE_URL=https://example.com/channel-webhook
WEBHOOK_CHANNEL_MESSAGE_SECRET=channel-secret
WEBHOOK_DIRECT_MESSAGE_URL=https://example.com/direct-webhook
WEBHOOK_DIRECT_MESSAGE_SECRET=direct-secret
```
