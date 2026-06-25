# Observer Ingestion Filters (Allow / Deny List)

**Branch:** `feat/observer-ingestion-filters`
**Date:** 2026-06-25

## Problem

Anyone can contribute as a remote **Observer** to a MeshCore Hub by publishing
decoded packets to the Hub's MQTT broker using JWT auth. There is currently no
way for a Hub operator to restrict *which* observers are allowed to have their
events ingested. We want an allow / deny list, configured via environment
variables, keyed on the observer's public key.

## How observers identify themselves (confirmed)

Remote observers publish to **LetsMesh upload topics**:

```
<prefix>/<iata>/<public_key>/(packets|status|internal)
```

A real production topic:

```
meshcore/STN/F4762185BBB684510B2E3D41568300869DB5E75B284448145475F7708C1EF408/packets
   │     │    └─ observer public key (64-char hex, UPPERCASE)                  └─ feed
 prefix  iata
```

The `<public_key>` segment is the observer's identity. It is parsed by
`TopicBuilder.parse_letsmesh_upload_topic()`
(`src/meshcore_hub/common/mqtt.py:130`) which returns `(public_key, feed_type)`.

The collector subscriber consumes these in
`Subscriber._handle_mqtt_message()` (`src/meshcore_hub/collector/subscriber.py:203`),
which calls `_normalize_letsmesh_event()` and obtains `public_key` (the observer
key) before performing **raw packet capture** and **event dispatch**. This is the
single choke point through which every observer-sourced event flows, so it is the
correct place to apply the filter.

In tests the observer key is a full 64-char hex string (e.g. `"a" * 64`); in
production it is **upper-case** 64-char hex (see example above). This is the
direct reason the filter normalises both the list entries and the topic key to
lower-case before comparing — an operator can paste the key in either case, or
use a leading prefix such as `OBSERVER_DENYLIST=F4762185`, and it will still
match.

## Decisions (confirmed with user)

1. **Env var naming:** `OBSERVER_ALLOWLIST` / `OBSERVER_DENYLIST` — **no**
   `COLLECTOR_` prefix. This matches the existing pydantic-settings convention
   where the field name maps directly to the upper-cased env var
   (`RAW_PACKET_CAPTURE_ENABLED`, `DATA_RETENTION_ENABLED`, `SPAM_*`). A
   `COLLECTOR_`-prefixed name would be the only one in the codebase and would
   require an `env_prefix`/alias.
2. **Matching:** **prefix match, case-insensitive.** An observer key matches a
   list entry if the (lower-cased) observer key *starts with* the (lower-cased,
   trimmed) entry. This lets operators use short prefixes (e.g. `a1b2c3`) as well
   as full keys.
3. **Precedence:** If `OBSERVER_ALLOWLIST` is non-empty it takes effect and
   `OBSERVER_DENYLIST` is **ignored**. If the allowlist is empty, the denylist
   applies. If both are empty, all observers are ingested (current behaviour).

## Semantics

Given a normalised observer key `k`:

| Allowlist | Denylist | Result |
| --- | --- | --- |
| empty | empty | **allow** (default, unchanged behaviour) |
| non-empty | (ignored) | allow **iff** `k` prefix-matches any allowlist entry |
| empty | non-empty | allow **unless** `k` prefix-matches any denylist entry |

A blocked event is dropped *before* raw-packet capture and before handler
dispatch, and is logged at `DEBUG` (to avoid log spam from a noisy blocked
observer). It is not persisted anywhere.

### Drop guarantee

The filter check is the **first** statement in `_handle_mqtt_message`, so a
blocked observer's packet skips every stage below it:

| Stage | Runs for blocked packet? |
| --- | --- |
| LetsMesh RF decode/decrypt (`_letsmesh_decoder.decode_payload`) | No |
| `raw_packets` insert (`_maybe_capture_raw_packet`) | No |
| Event handlers → `messages` / `advertisements` / `telemetry` / `event_observers` | No |
| Node upsert / `is_observer` flag | No |
| Webhook dispatch | No |

The **only** processing a blocked packet incurs is the unavoidable
transport-level `json.loads()` of the MQTT envelope in
`MQTTClient._on_message` (`common/mqtt.py:230`) — which happens for every
message before any handler runs and is shared by all subscribers — plus the
cheap topic-string split the filter does to read the observer key. Neither
performs RF packet decoding nor writes to the database. A blocked packet is
therefore dropped entirely: not decoded, not persisted, not forwarded.

Empty / whitespace-only entries are discarded when parsing the comma-delimited
lists, so `OBSERVER_DENYLIST=` or trailing commas are harmless.

## Implementation

### 1. New module: `src/meshcore_hub/collector/observer_filter.py`

A small, dependency-free, unit-testable helper.

```python
"""Allow/deny filtering of observer-sourced events by observer public key."""

from __future__ import annotations

from dataclasses import dataclass


def _normalise(entries: list[str] | None) -> tuple[str, ...]:
    """Lower-case, strip, and drop empty entries."""
    if not entries:
        return ()
    return tuple(e.strip().lower() for e in entries if e and e.strip())


@dataclass(frozen=True)
class ObserverFilter:
    """Decides whether an observer's events should be ingested.

    Allowlist takes precedence over denylist. Matching is case-insensitive
    prefix matching against the observer public key.
    """

    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()

    @classmethod
    def from_lists(
        cls,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
    ) -> "ObserverFilter":
        return cls(allowlist=_normalise(allowlist), denylist=_normalise(denylist))

    @property
    def active(self) -> bool:
        return bool(self.allowlist or self.denylist)

    def is_allowed(self, public_key: str | None) -> bool:
        if not self.allowlist and not self.denylist:
            return True
        key = (public_key or "").strip().lower()
        if self.allowlist:
            return any(key.startswith(entry) for entry in self.allowlist)
        return not any(key.startswith(entry) for entry in self.denylist)
```

> Note on empty-string prefix: `_normalise` drops empty entries, so an
> all-empty list yields `()` and `startswith` is never called with `""`. This
> prevents an accidental "match everything" from a stray comma.

### 2. Config: `src/meshcore_hub/common/config.py` (`CollectorSettings`)

Add two raw string fields plus parsed-list properties. Strings (not `list[str]`)
because pydantic-settings parses complex types from env as JSON, which breaks
comma-separated input.

```python
# Observer ingestion filtering (allow/deny by observer public key).
# Allowlist takes precedence over denylist. Empty = no restriction.
observer_allowlist: str = Field(
    default="",
    description=(
        "Comma-separated observer public keys (or prefixes) allowed to ingest. "
        "If set, overrides OBSERVER_DENYLIST."
    ),
)
observer_denylist: str = Field(
    default="",
    description=(
        "Comma-separated observer public keys (or prefixes) blocked from ingesting. "
        "Ignored when OBSERVER_ALLOWLIST is set."
    ),
)

@property
def observer_allowlist_keys(self) -> list[str]:
    return [k.strip() for k in self.observer_allowlist.split(",") if k.strip()]

@property
def observer_denylist_keys(self) -> list[str]:
    return [k.strip() for k in self.observer_denylist.split(",") if k.strip()]
```

### 3. Subscriber: `src/meshcore_hub/collector/subscriber.py`

- Add `observer_filter: ObserverFilter | None = None` parameter to
  `Subscriber.__init__`; store as `self._observer_filter = observer_filter or ObserverFilter()`.
  Log at startup when active (mirroring the existing raw-capture log line), e.g.
  `"Observer filter active: %d allow, %d deny"`.
- In `_handle_mqtt_message()`, **before** `_normalize_letsmesh_event()` (to avoid
  decode work for blocked observers), cheaply extract the observer key from the
  topic and short-circuit:

```python
def _handle_mqtt_message(self, topic, pattern, payload):
    if self._observer_filter.active:
        parsed_topic = self.mqtt.topic_builder.parse_letsmesh_upload_topic(topic)
        if parsed_topic:
            observer_key, _feed = parsed_topic
            if not self._observer_filter.is_allowed(observer_key):
                logger.debug(
                    "Dropping event from blocked observer %s...", observer_key[:12]
                )
                return
    # ... existing normalize + capture + dispatch ...
```

  Rationale for placing the check here rather than inside
  `_normalize_letsmesh_event`: it covers raw-packet capture too (which also keys
  off `public_key`), and skips the decode entirely for blocked observers. When
  the filter is inactive (`active == False`) there is **zero** added work on the
  hot path.

- Thread the parameter through the two factory functions in the same file:
  - `create_subscriber(...)` — add `observer_filter` param, pass to `Subscriber(...)`.
  - `run_collector(...)` — add `observer_filter` param, pass to `create_subscriber(...)`.

### 4. CLI wiring: `src/meshcore_hub/collector/cli.py`

In `_run_collector_service()` build the filter from settings and pass it into
`run_collector(...)`:

```python
from meshcore_hub.collector.observer_filter import ObserverFilter
...
run_collector(
    ...,
    raw_packet_capture_enabled=settings.raw_packet_capture_enabled,
    raw_packet_retention_days=settings.effective_raw_packet_retention_days,
    observer_filter=ObserverFilter.from_lists(
        allowlist=settings.observer_allowlist_keys,
        denylist=settings.observer_denylist_keys,
    ),
)
```

## Tests

### New: `tests/test_collector/test_observer_filter.py` (unit, pure logic)

- empty allow + empty deny → allows any key
- allowlist set → allows listed key; blocks unlisted; denylist ignored even if it
  would block the same key (precedence)
- denylist set (no allowlist) → blocks listed key; allows others
- case-insensitivity (upper-case env entry vs lower-case key and vice versa)
- prefix matching: short prefix matches longer key; non-matching prefix does not
- whitespace / empty-entry hygiene (`"", "  ", "a,"` etc.) — no spurious matches
- `active` property true/false
- `from_lists(None, None)` behaves as empty

### Extend: `tests/test_collector/test_subscriber.py`

Following the existing `_handle_mqtt_message` test style (mock
`_normalize_letsmesh_event`, real topic):

- observer on denylist → handler **not** called, no raw-packet row written
- observer on allowlist → handler called normally
- observer not on allowlist (allowlist active) → handler not called
- filter inactive (default) → existing behaviour unchanged (regression guard)
- blocked observer with `raw_packet_capture_enabled=True` → no raw row written
  (confirms the check precedes capture)

### Extend: `tests/test_common/` config test (if present)

- `OBSERVER_ALLOWLIST="aaa, bbb ,"` → `observer_allowlist_keys == ["aaa", "bbb"]`
- defaults → empty lists, `active` false

## Documentation

### `docs/configuration.md`

Add a new subsection under **Collector** (after the Collector table, before
Webhooks) titled **Observer Ingestion Filters**:

| Variable | Default | Description |
| --- | --- | --- |
| `OBSERVER_ALLOWLIST` | _(none)_ | Comma-separated observer public keys (or key prefixes) permitted to ingest. If set, only matching observers are accepted and `OBSERVER_DENYLIST` is ignored. |
| `OBSERVER_DENYLIST` | _(none)_ | Comma-separated observer public keys (or key prefixes) blocked from ingesting. Applies only when `OBSERVER_ALLOWLIST` is unset/empty. |

Prose: explain observer = LetsMesh upload topic publisher identified by its
public key; precedence (allow overrides deny); case-insensitive prefix matching;
blocked events are dropped before capture/persistence; default (both empty) =
accept all. Cross-link to [observer.md](../observer.md).

### `docs/observer.md`

Add a short "Restricting which observers are accepted" note linking back to the
configuration table, so operators running observers know contributions can be
gated.

### `docs/upgrading.md`

Add a **new `## v0.16.0` section at the top** of the file (above the current
`## v0.15.0`), since this ships in the next release. Under it add an **Observer
Ingestion Filters** subsection: new optional `OBSERVER_ALLOWLIST` /
`OBSERVER_DENYLIST` vars; **non-breaking**, defaults preserve existing
accept-all behaviour; note allow-over-deny precedence, case-insensitive prefix
matching, and that blocked observer packets are dropped before any decode or
persistence. Cross-link to [configuration.md](configuration.md) and
[observer.md](observer.md).

### `.env.example`

Under the `# COLLECTOR SETTINGS` block (near `DATA_RETENTION_*` /
`RAW_PACKET_*`), add commented examples:

```ini
# Observer ingestion filter (allow/deny remote observers by public key or prefix).
# Allowlist takes precedence over denylist. Matching is case-insensitive prefix
# matching. Leave both empty to accept all observers (default).
# OBSERVER_ALLOWLIST=
# OBSERVER_DENYLIST=
```

### Docker Compose files

Only the **base** `docker-compose.yml` defines the collector's `environment:`
block, so it is the only compose file that needs the new vars. Wire both into
the **collector** service `environment:` block (near `RAW_PACKET_*`) so Compose
users can set them from their `.env`:

```yaml
      # Observer ingestion filter (allow/deny remote observers by public key/prefix)
      - OBSERVER_ALLOWLIST=${OBSERVER_ALLOWLIST:-}
      - OBSERVER_DENYLIST=${OBSERVER_DENYLIST:-}
```

The other compose files are intentionally **not** modified:

| File | Why no change |
| --- | --- |
| `docker-compose.dev.yml` | Overlay; only overrides `pull_policy` / `depends_on` / `ports`. Compose merges `environment` additively, so it inherits the base collector env block. |
| `docker-compose.prod.yml` | Overlay; only overrides `networks`. Inherits base env block. |
| `docker-compose.traefik.yml` | Overlay; only adds Traefik labels. Inherits base env block. |
| `contrib/packetcapture/docker-compose.yml` | This is the **observer-side** packet-capture publisher, not the Hub collector. The allow/deny lists are consumed by the ingesting Hub collector, so this file gets nothing. |

## Files touched

| File | Change |
| --- | --- |
| `src/meshcore_hub/collector/observer_filter.py` | **new** — `ObserverFilter` |
| `src/meshcore_hub/common/config.py` | add fields + parsed-list properties |
| `src/meshcore_hub/collector/subscriber.py` | filter param on `Subscriber`, `create_subscriber`, `run_collector`; early-drop in `_handle_mqtt_message` |
| `src/meshcore_hub/collector/cli.py` | build `ObserverFilter`, pass to `run_collector` |
| `tests/test_collector/test_observer_filter.py` | **new** unit tests |
| `tests/test_collector/test_subscriber.py` | integration tests for drop/allow |
| `tests/test_common/...` (config test) | env-var parsing tests |
| `docs/configuration.md` | new Observer Ingestion Filters table + prose |
| `docs/observer.md` | short cross-reference note |
| `docs/upgrading.md` | release note |
| `.env.example` | commented example vars |
| `docker-compose.yml` | collector env wiring |

## Out of scope / non-goals

- No UI surface for managing the lists (env-driven only, like other collector knobs).
- No database-backed dynamic list; restart picks up env changes (consistent with
  existing collector settings).
- Native `event` topics (`<prefix>/<public_key>/event/#`) are not currently
  subscribed by this collector path — the filter targets LetsMesh observer
  uploads, which is where untrusted JWT contributors publish. If native event
  ingestion is added later, the same `is_allowed` check can be applied there.

## Validation

- `make test` (or `pytest tests/test_collector/test_observer_filter.py
  tests/test_collector/test_subscriber.py`) green.
- `ruff` / `mypy` clean (the new module is fully typed; frozen dataclass).
- Manual sanity: set `OBSERVER_DENYLIST=<known observer key prefix>`, confirm its
  events stop appearing while others continue; clear it and set
  `OBSERVER_ALLOWLIST` to a different key, confirm only that observer ingests.
