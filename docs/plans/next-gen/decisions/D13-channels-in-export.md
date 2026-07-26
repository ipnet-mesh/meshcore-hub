# D13: Include Channels in the Config Export Bundle

- **Status:** Locked
- **Iteration:** 4

## Context

The preserved-config export/import (migration.md) carries data that cannot be repopulated from RF traffic: `user_profiles` + roles, `routes` + nodes + observers, `node_tags`, adoptions, and node identity stubs. The open question (Q-C in iteration 4): are channels in this set? Channels are *borderline* — the `name` and `visibility` tier could plausibly be re-entered by hand, but the `key_hex` is an operator secret **never transmitted over RF**. Without it, the ingester's `ChannelKeyCache` cannot decrypt incoming channel messages, and the parallel-stack validation window (D14) would lose every channel message.

## Decision

**Include channels in `db export-config`.** The export bundle carries `channels` alongside `user_profiles`, `routes`, `node_tags`, `adoptions`, and `node_stubs`. On import, channels are inserted with `key_hex` cast and `key_hash` recomputed (first byte of `sha256(key)`). The export is JSON, human-readable and diffable; channel keys are operator secrets, so the bundle must be treated as a secret (operators already handle the export this way for OIDC config).

## Consequences

**Positive:** Channel decryption works from minute one of the parallel-stack window — no manual key re-entry, no lost channel messages during validation. Operators iterating on route config during the validation window can re-export cleanly.

**Negative:** The export bundle now contains a secret (`key_hex`), so it must be handled/stored with the same care as `OIDC_CLIENT_SECRET` or `ADMIN_PASSWORD` — documented in the export command's `--help` and the migration runbook.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Include channels in export** (chosen) | Keys are operator secrets never on RF; without them the ingester can't decrypt. |
| Exclude channels — operator re-enters keys manually | Rejected — error-prone, breaks parallel-stack validation (channel messages lost), poor UX. |
| Separate `db export-channels` command | Rejected — artificial split; channels belong with the other preserved config in one bundle. |
| Re-derive keys from RF on first sighting | Rejected — keys are never transmitted over RF by design; this is impossible. |
