# LetsMesh Packet Decoding

The collector subscribes to packets published by [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture):

- `<prefix>/+/+/packets`
- `<prefix>/+/+/status`
- `<prefix>/+/+/internal`

## Normalization Behavior

- `status` packets are stored as informational `letsmesh_status` events and are not mapped to `advertisement` rows.
- Decoder payload type `4` is mapped to `advertisement` when node identity metadata is present.
- Decoder payload type `11` (control discover response) is mapped to `contact`.
- Decoder payload type `9` is mapped to `trace_data`.
- Decoder payload type `8` is mapped to informational `path_updated` events.
- Decoder payload type `1` can map to native response events (`telemetry_response`, `battery`, `path_updated`, `status_response`) when decrypted structured content is available.
- `packet_type=5` packets are mapped to `channel_msg_recv`.
- `packet_type=1`, `2`, and `7` packets are mapped to `contact_msg_recv` when decryptable text is available.
- Packets that no structured handler claims are no longer all labelled `letsmesh_packet`. They are classified by their MeshCore payload type so the `event_type` is specific:

  | Payload type | `event_type` |
  |---|---|
  | `0x00 REQ` | `req` |
  | `0x01 RESPONSE` | `response` |
  | `0x02 TXT_MSG` (undecryptable) | `encrypted_direct` |
  | `0x03 ACK` | `ack` |
  | `0x04 ADVERT` (no identity) | `advert` |
  | `0x05 GRP_TXT` (unknown key) | `encrypted_channel` |
  | `0x06 GRP_DATA` | `grp_data` |
  | `0x07 ANON_REQ` | `anon_req` |
  | `0x08 PATH` | `path` |
  | `0x09 TRACE` | `trace` |
  | `0x0A MULTIPART` | `multipart` |
  | `0x0B CONTROL` | `control` |
  | `0x0F RAW_CUSTOM` | `raw_custom` |

  `letsmesh_packet` is retained only as a safety net for packets whose payload type cannot be resolved. Reaching these fallbacks for `TXT_MSG`/`GRP_TXT` means the payload did not decrypt, hence the `encrypted_*` labels (decryptable ones become `contact_msg_recv` / `channel_msg_recv`).

## Raw Packet Capture

- When `RAW_PACKET_CAPTURE_ENABLED` is set (Compose derives it from `FEATURE_PACKETS`), every packet on the `packets` feed is also stored verbatim in the `raw_packets` table — one row per observer reception, independent of structured classification. The `status` and `internal` feeds carry no on-air `raw` hex and are **not** captured as raw packets.
- Capture reuses the single decode the normalizer already performs (the decoder caches per raw hex), so it adds only an insert plus an observer upsert to the ingest path.
- The `/packets` API and Packets page apply channel-visibility rules: channel-message packets on a channel above the viewer's role are returned **metadata-only with the payload redacted** (`redacted=true`, `raw_hex`/`decoded` nulled), not hidden. Non-channel and visible-channel packets are returned in full.

## Channel Keys

- For channel packets, if a channel key is available, a channel label is attached (for example `Public` or `#test`) for UI display.
- In the messages feed and dashboard channel sections, known channel indexes are preferred for labels (`17 -> Public`, `217 -> #test`) to avoid stale channel-name mismatches.
- Additional channel names are loaded from the `channels` database table (managed via CLI, API, or seed YAML).
- The collector keeps built-in keys for `Public` and `#test`, and merges any additional keys from enabled database channel rows.

## Location and Messages

- Decoder-advertisement packets with location metadata update node GPS (`lat/lon`) for map display.
- This keeps advertisement listings focused on node advert traffic only, not observer status telemetry.
- Packets without decryptable message text are kept as informational `letsmesh_packet` events and are not shown in the messages feed; when decode succeeds the decoded JSON is attached to those packet log events.
- When decoder output includes a human sender (`payload.decoded.decrypted.sender`), message text is normalized to `Name: Message` before storage; receiver/observer names are never used as sender fallback.

## Decoder Runtime

- Docker runtime uses the native Python `meshcoredecoder` library (no external Node.js dependency).
