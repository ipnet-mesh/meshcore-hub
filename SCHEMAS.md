# MeshCore Event Schemas

This document defines the complete JSON payload schemas for all MeshCore events supported by the API.

## Event Categories

Events are categorized by how they're handled:

- **Persisted Events**: Stored in database tables and available via REST API
- **Webhook Events**: Trigger HTTP POST notifications when configured
- **Informational Events**: Logged but not persisted to separate tables

## Table of Contents

- [Persisted & Webhook Events](#persisted--webhook-events)
  - [ADVERTISEMENT / NEW_ADVERT](#advertisement--new_advert)
  - [CONTACT_MSG_RECV](#contact_msg_recv)
  - [CHANNEL_MSG_RECV](#channel_msg_recv)
- [Persisted Events (Non-Webhook)](#persisted-events-non-webhook)
  - [TRACE_DATA](#trace_data)
  - [TELEMETRY_RESPONSE](#telemetry_response)
  - [CONTACTS](#contacts)
- [Informational Events](#informational-events)
  - [SEND_CONFIRMED](#send_confirmed)
  - [STATUS_RESPONSE](#status_response)
  - [BATTERY](#battery)
  - [PATH_UPDATED](#path_updated)
- [Webhook Payload Format](#webhook-payload-format)

---

## Persisted & Webhook Events

These events are both stored in the database and trigger webhooks when configured.

### ADVERTISEMENT / NEW_ADVERT

Node advertisements announcing presence and metadata.

**Database Table**: `advertisements`

**Payload Schema**:
```json
{
  "public_key": "string (64 hex chars)",
  "name": "string (optional)",
  "adv_type": "string (optional)",
  "flags": "integer (optional)"
}
```

**Field Descriptions**:
- `public_key`: Node's full 64-character hexadecimal public key (required)
- `name`: Node name/alias (e.g., "Gateway-01", "Alice")
- `adv_type`: Node type - one of: `"chat"`, `"repeater"`, `"room"`, `"none"`
- `flags`: Node capability/status flags (bitmask)

**Example**:
```json
{
  "public_key": "4767c2897c256df8d85a5fa090574284bfd15b92d47359741b0abd5098ed30c4",
  "name": "Gateway-01",
  "adv_type": "repeater",
  "flags": 218
}
```

**Webhook Trigger**: Yes
**REST API**: `GET /api/v1/advertisements`

---

### CONTACT_MSG_RECV

Direct/private messages between two nodes.

**Database Table**: `messages`

**Payload Schema**:
```json
{
  "pubkey_prefix": "string (12 chars)",
  "path_len": "integer (optional)",
  "txt_type": "integer (optional)",
  "signature": "string (optional)",
  "text": "string",
  "SNR": "number (optional)",
  "sender_timestamp": "integer (optional)"
}
```

**Field Descriptions**:
- `pubkey_prefix`: First 12 characters of sender's public key
- `path_len`: Number of hops message traveled
- `txt_type`: Message type indicator (0=plain, 2=signed, etc.)
- `signature`: Message signature (8 hex chars) when `txt_type=2`
- `text`: Message content (required)
- `SNR`: Signal-to-Noise Ratio in dB
- `sender_timestamp`: Unix timestamp when message was sent

**Example**:
```json
{
  "pubkey_prefix": "01ab2186c4d5",
  "path_len": 3,
  "txt_type": 0,
  "signature": null,
  "text": "Hello Bob!",
  "SNR": 15.5,
  "sender_timestamp": 1732820498
}
```

**Webhook Trigger**: Yes
**REST API**: `GET /api/v1/messages`
**Webhook JSONPath Examples**:
- Send only text: `$.data.text`
- Send text + SNR: `$.data.[text,SNR]`

---

### CHANNEL_MSG_RECV

Group/broadcast messages on specific channels.

**Database Table**: `messages`

**Payload Schema**:
```json
{
  "channel_idx": "integer",
  "path_len": "integer (optional)",
  "txt_type": "integer (optional)",
  "signature": "string (optional)",
  "text": "string",
  "SNR": "number (optional)",
  "sender_timestamp": "integer (optional)"
}
```

**Field Descriptions**:
- `channel_idx`: Channel number (0-255)
- `path_len`: Number of hops message traveled
- `txt_type`: Message type indicator (0=plain, 2=signed, etc.)
- `signature`: Message signature (8 hex chars) when `txt_type=2`
- `text`: Message content (required)
- `SNR`: Signal-to-Noise Ratio in dB
- `sender_timestamp`: Unix timestamp when message was sent

**Example**:
```json
{
  "channel_idx": 4,
  "path_len": 10,
  "txt_type": 0,
  "signature": null,
  "text": "Hello from the mesh!",
  "SNR": 8.5,
  "sender_timestamp": 1732820498
}
```

**Webhook Trigger**: Yes
**REST API**: `GET /api/v1/messages`
**Webhook JSONPath Examples**:
- Send only text: `$.data.text`
- Send channel + text: `$.data.[channel_idx,text]`

---

## Persisted Events (Non-Webhook)

These events are stored in the database but do not trigger webhooks.

### TRACE_DATA

Network trace path results showing route and signal strength.

**Database Table**: `trace_paths`

**Payload Schema**:
```json
{
  "initiator_tag": "integer",
  "path_len": "integer (optional)",
  "flags": "integer (optional)",
  "auth": "integer (optional)",
  "path_hashes": "array of strings",
  "snr_values": "array of numbers",
  "hop_count": "integer (optional)"
}
```

**Field Descriptions**:
- `initiator_tag`: Unique trace identifier (0-4294967295)
- `path_len`: Length of the path
- `flags`: Trace flags/options
- `auth`: Authentication/validation data
- `path_hashes`: Array of 2-character node hash identifiers (ordered by hops)
- `snr_values`: Array of SNR values corresponding to each hop
- `hop_count`: Total number of hops

**Example**:
```json
{
  "initiator_tag": 123456789,
  "path_len": 3,
  "flags": 0,
  "auth": 1,
  "path_hashes": ["4a", "b3", "fa"],
  "snr_values": [25.3, 18.7, 12.4],
  "hop_count": 3
}
```

**Webhook Trigger**: No
**REST API**: `GET /api/v1/trace-paths`

---

### TELEMETRY_RESPONSE

Sensor data from network nodes (temperature, humidity, battery, etc.).

**Database Table**: `telemetry`

**Payload Schema**:
```json
{
  "node_public_key": "string (64 hex chars)",
  "lpp_data": "bytes (optional)",
  "parsed_data": "object (optional)"
}
```

**Field Descriptions**:
- `node_public_key`: Full public key of the reporting node
- `lpp_data`: Raw LPP-encoded sensor data (CayenneLPP format)
- `parsed_data`: Decoded sensor readings as key-value pairs

**Example**:
```json
{
  "node_public_key": "4767c2897c256df8d85a5fa090574284bfd15b92d47359741b0abd5098ed30c4",
  "lpp_data": null,
  "parsed_data": {
    "temperature": 22.5,
    "humidity": 65,
    "battery": 3.8,
    "pressure": 1013.25
  }
}
```

**Webhook Trigger**: No
**REST API**: `GET /api/v1/telemetry`

---

### CONTACTS

Contact sync event containing all known nodes.

**Database Table**: Updates `nodes` table

**Payload Schema**:
```json
{
  "contacts": [
    {
      "public_key": "string (64 hex chars)",
      "name": "string (optional)",
      "node_type": "string (optional)"
    }
  ]
}
```

**Field Descriptions**:
- `contacts`: Array of contact objects
- `public_key`: Node's full public key
- `name`: Node name/alias
- `node_type`: One of: `"chat"`, `"repeater"`, `"room"`, `"none"`

**Example**:
```json
{
  "contacts": [
    {
      "public_key": "01ab2186c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1",
      "name": "Alice",
      "node_type": "chat"
    },
    {
      "public_key": "b3f4e5d6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4",
      "name": "Bob",
      "node_type": "chat"
    }
  ]
}
```

**Webhook Trigger**: No
**REST API**: `GET /api/v1/nodes`

---

## Informational Events

These events are logged to `events_log` table but not persisted to separate tables.

### SEND_CONFIRMED

Confirmation that a sent message was delivered.

**Payload Schema**:
```json
{
  "destination_public_key": "string (64 hex chars)",
  "round_trip_ms": "integer"
}
```

**Field Descriptions**:
- `destination_public_key`: Recipient's full public key
- `round_trip_ms`: Round-trip time in milliseconds

**Example**:
```json
{
  "destination_public_key": "4767c2897c256df8d85a5fa090574284bfd15b92d47359741b0abd5098ed30c4",
  "round_trip_ms": 2500
}
```

---

### STATUS_RESPONSE

Device status information.

**Payload Schema**:
```json
{
  "node_public_key": "string (64 hex chars)",
  "status": "string (optional)",
  "uptime": "integer (optional)",
  "message_count": "integer (optional)"
}
```

**Field Descriptions**:
- `node_public_key`: Node's full public key
- `status`: Status description
- `uptime`: Uptime in seconds
- `message_count`: Total messages processed

**Example**:
```json
{
  "node_public_key": "4767c2897c256df8d85a5fa090574284bfd15b92d47359741b0abd5098ed30c4",
  "status": "operational",
  "uptime": 86400,
  "message_count": 1523
}
```

---

### BATTERY

Battery status information.

**Payload Schema**:
```json
{
  "battery_voltage": "number",
  "battery_percentage": "integer"
}
```

**Field Descriptions**:
- `battery_voltage`: Battery voltage (e.g., 3.7V)
- `battery_percentage`: Battery level 0-100%

**Example**:
```json
{
  "battery_voltage": 3.8,
  "battery_percentage": 75
}
```

---

### PATH_UPDATED

Notification that routing path to a node has changed.

**Payload Schema**:
```json
{
  "node_public_key": "string (64 hex chars)",
  "hop_count": "integer"
}
```

**Field Descriptions**:
- `node_public_key`: Target node's full public key
- `hop_count`: Number of hops in new path

**Example**:
```json
{
  "node_public_key": "4767c2897c256df8d85a5fa090574284bfd15b92d47359741b0abd5098ed30c4",
  "hop_count": 3
}
```

---

### Other Informational Events

The following events are logged but have varying or device-specific payloads:

- **STATISTICS**: Network statistics (varies by implementation)
- **DEVICE_INFO**: Device hardware/firmware information
- **BINARY_RESPONSE**: Binary data responses
- **CONTROL_DATA**: Control/command responses
- **RAW_DATA**: Raw protocol data
- **NEXT_CONTACT**: Contact enumeration progress
- **ERROR**: Error messages with description
- **MESSAGES_WAITING**: Notification of queued messages
- **NO_MORE_MSGS**: End of message queue
- **RX_LOG_DATA**: Receive log data

---

## Webhook Payload Format

All webhook events are wrapped in a standard envelope before being sent:

```json
{
  "event_type": "string",
  "timestamp": "string (ISO 8601)",
  "data": {
    // Event-specific payload (see schemas above)
  }
}
```

**Example (Channel Message)**:
```json
{
  "event_type": "CHANNEL_MSG_RECV",
  "timestamp": "2025-11-28T19:41:38.748379Z",
  "data": {
    "channel_idx": 4,
    "path_len": 10,
    "txt_type": 0,
    "text": "Hello from the mesh!",
    "SNR": 8.5,
    "sender_timestamp": 1732820498
  }
}
```

### JSONPath Filtering

You can filter webhook payloads using JSONPath expressions:

| JSONPath | Result |
|----------|--------|
| `$` | Full payload (default) |
| `$.data` | Event data only |
| `$.data.text` | Message text only |
| `$.data.[text,SNR]` | Multiple fields as array |
| `$.event_type` | Event type string |
| `$.timestamp` | Timestamp string |

See [AGENTS.md](AGENTS.md) for webhook configuration details.

---

## Event Flow

1. **Hardware/Mock MeshCore** → Generates raw events
2. **Event Handler** → Processes and persists to database
3. **Webhook Handler** → Sends HTTP POST to configured URLs (if enabled)
4. **REST API** → Query historical data from database

Most events are logged to the `events_log` table with full payloads for debugging and audit purposes. Some high-frequency informational events (e.g., `NEXT_CONTACT`) are intentionally excluded from logging to reduce database size.
