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

## Channel Keys

- For channel packets, if a channel key is available, a channel label is attached (for example `Public` or `#test`) for UI display.
- In the messages feed and dashboard channel sections, known channel indexes are preferred for labels (`17 -> Public`, `217 -> #test`) to avoid stale channel-name mismatches.
- Additional channel names are loaded from `COLLECTOR_CHANNEL_KEYS` when entries are provided as `label=hex` (for example `bot=<key>`).
- The collector keeps built-in keys for `Public` and `#test`, and merges any additional keys from `COLLECTOR_CHANNEL_KEYS`.

## Location and Messages

- Decoder-advertisement packets with location metadata update node GPS (`lat/lon`) for map display.
- This keeps advertisement listings focused on node advert traffic only, not observer status telemetry.
- Packets without decryptable message text are kept as informational `letsmesh_packet` events and are not shown in the messages feed; when decode succeeds the decoded JSON is attached to those packet log events.
- When decoder output includes a human sender (`payload.decoded.decrypted.sender`), message text is normalized to `Name: Message` before storage; receiver/observer names are never used as sender fallback.

## Decoder Runtime

- Docker runtime uses the native Python `meshcoredecoder` library (no external Node.js dependency).
