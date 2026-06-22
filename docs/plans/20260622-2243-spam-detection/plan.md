# Spam Detection / Message Scoring at Ingest

**Date**: 2026-06-22
**Status**: Design settled, ready for implementation
**Branch**: `feat/spam-detection`

## Problem Statement

A user is flooding the mesh network with near-identical messages. The sender name
varies slightly each time (incrementing suffixes, e.g. `bob1`, `bob2`), so naive
name-blocking does not work. The message content is currently trivial (`"test"`)
but is trivially changeable, so content-blocking is also unreliable.

The goal is to **flag likely-spam messages with a score at ingest time, store that
score on the message row, and let the display layer filter on it** (hide by
default, with a "show potential spam" toggle). We never drop or block at ingest —
the design stays reversible, so the threshold can be retuned later without
reprocessing anything.

## Research Findings

The original design assumed messages carried a sender *name* and a *path prefix*
(first few route hops). Exploration of the codebase shows the real data model
differs in ways that shape the implementation:

### Sender identity

- Messages do **not** store a human sender name. They store `pubkey_prefix`
  (12-char public-key prefix) — `models/message.py:42`.
- A human `sender_name` *is* resolved during normalization
  (`letsmesh_normalizer.py:172`, via `_extract_letsmesh_decoder_sender` +
  `_normalize_sender_name`) but is currently only used to prefix the message text,
  not persisted.
- **On public channels (where the spam lives) there is no cryptographic sender
  identity.** Channel messages are encrypted with a shared channel key, so
  `pubkey_prefix` is typically null and the sender name is *self-declared* — it is
  literally part of the decrypted body, formatted `"<Sender Name>: <Body>"`
  (confirmed: name then a colon-space `": "` delimiter). That is exactly why the
  spammer can trivially rotate `bob1`/`bob2`. The normalizer already extracts that
  name into the payload's `sender_name`, so `sender_normalized =
  normalize_sender(payload["sender_name"])`; if ever absent it can be recovered by
  splitting the stored `text` on the first `": "`. A future content-fingerprint
  signal must strip everything up to and including that `": "` before comparing.

### Route / path

- Messages store only `path_len` — a hop **count** integer (`models/message.py:54`),
  **not** the route itself.
- However, the ordered route **is available at ingest** in the decoded packet as a
  top-level `decoded.path` list of hop hashes. It is simply discarded for message
  packets. The trace handler already keeps it as `path_hashes`
  (`letsmesh_normalizer.py:287`), and `api/routes/packet_groups.py:36`
  `_extract_path_hashes()` documents the exact location (`decoded.get("path")`,
  with `decoded.payload.decoded.pathHashes` as the trace-style fallback).
- The path is the **strongest signal**: it reflects the real relay topology and is
  far harder for a spammer to fake than a name or message body.
- **Two ordering/determinism caveats** that affect how the prefix is taken:
  1. *Direction.* We must take the **origin-side** hops. A spammer at a fixed
     location reaches the same repeaters that can physically hear it, so the first
     hop(s) are effectively a **location fingerprint** the spammer can't change by
     editing the name or body — this is why path is the strongest signal.
     Origin-side selection is also what makes the stored prefix **deterministic
     across observers**: the receiver-side hops diverge per observer (and dedup
     keeps only the first-arriving observer's row), but the origin-side hops are
     shared by all observers, so the key is stable regardless of which observer
     wins. The hop list is append-order as the packet is relayed (each repeater
     appends its hash), so index 0 is closest to the origin and `path_hashes[:N]`
     is the origin-side prefix. **Confirmed origin-first** — the Packets page
     renders these paths from origin toward observer using the same `decoded.path`
     ordering.
  2. *Cross-observer dedup.* One logical message received by several observers is
     deduped to a **single** `messages` row written by whichever observer inserted
     first, and each observer received the message via a *different* route. So the
     stored `path_prefix` is nondeterministic at the receiver end. Taking only the
     first 2–3 *origin-side* hops keeps it as stable as possible, but the prefix is
     inherently a little noisy — which is why `sender_normalized` is kept as an
     independent secondary signal rather than folding everything into the path.

### Infrastructure

- The **collector has no Redis**. Redis exists only in the API service for
  response caching (`common/redis.py`, used via `@cached` in the API routes).
- The `messages` table is already indexed on `received_at`
  (`ix_messages_received_at`). Adding a composite `(path_prefix, received_at)`
  index makes a windowed `COUNT(*)` trivially cheap at mesh volumes.
- Migrations use **Alembic** with autogenerate; an example add-column migration is
  `alembic/versions/20260515_1920_add_route_type_advert_timestamp.py`. CLI:
  `meshcore-hub db revision --autogenerate -m "…"` then `meshcore-hub db upgrade`.
- The display path is: API `api/routes/messages.py::list_messages` (cached) →
  schema `common/schemas/messages.py::MessageRead` → SPA
  `web/static/js/spa/pages/messages.js` (lit-html), which renders filters via
  `renderFilterCard()` in `components.js`.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sliding-window counter store | **Postgres-direct windowed `COUNT(*)`** | Collector has no Redis; mesh volume is low; the `(path_prefix, received_at)` index makes counts cheap. One source of truth, no rebuild-on-restart logic. |
| Primary signal | **Joint `(path_prefix, sender_normalized)`** frequency in window | The real spam signature is "same route **and** same normalized sender, repeatedly." A joint count means a busy *legitimate* path carrying many *different* senders does not score — only concentrated repetition does. |
| Secondary signal | **`sender_normalized`** alone (name with trailing digits stripped) frequency | Robust fallback that catches `bob1`/`bob2` rotation even when the stored `path_prefix` is noisy/null (see cross-observer path note). Weighted lower. |
| Content signal | **Out of scope (v1)** | Content is trivial/spoofable now; shingling/fingerprinting deferred to a future iteration. |
| Block vs. score | **Score, never block** | Reversible; threshold retunable without reprocessing. Filtering happens at display time. |
| Threshold location | **Env var `SPAM_SCORE_THRESHOLD`** (default 0.6) | Retune without code change/redeploy. |
| Short-path handling | **Minimum-path-length gate `SPAM_MIN_PATH_HOPS`** (default 5) | Short paths (`<5` hops) in local meshes legitimately share the same prefix; below the gate the path signal is disabled and `path_prefix` is stored null so these rows don't pollute path counts. |
| Historical backfill | **None (v1)** | Backfill would require re-decoding `raw_packets`. Window is minutes, so counts self-heal as new messages arrive. |
| Database support | **Both SQLite and Postgres** | Project still ships SQLite as the default. All work stays DB-agnostic: SQLAlchemy Core/ORM for queries, Alembic batch mode for the migration (no Postgres-only DDL), and a **Python-computed cutoff datetime** for the window — never SQL `NOW() - INTERVAL` (which differs between engines). |
| Master on/off switch | **`FEATURE_SPAM_DETECTION` (UI) bridged to `SPAM_DETECTION_ENABLED` (backend), both default `false`** | Mirrors the existing **raw-packets** pattern exactly. `FEATURE_SPAM_DETECTION` (config `feature_spam_detection`) feeds the `features` dict the frontend reads (like `FEATURE_PACKETS`) and gates the UI toggle. `SPAM_DETECTION_ENABLED` (config `spam_detection_enabled`) is the operational switch the **collector + API** read; when off the collector does no scoring (null `spam_score`), the sweep doesn't run, and the API applies no hide-filter. Compose bridges them — `SPAM_DETECTION_ENABLED=${FEATURE_SPAM_DETECTION:-false}` (cf. `RAW_PACKET_CAPTURE_ENABLED=${FEATURE_PACKETS}`) — so operators set **one** var. Keeping two avoids making backend services depend on a UI "feature" flag. |

## Combined Design

### 1. Database model (`models/message.py`)

Add three nullable columns (backward compatible with existing rows) and two
composite indexes:

- `path_prefix: Mapped[str | None]` — `String(48)`, first N hop hashes joined
  (e.g. `"16,69,23"`); null below the path-length gate.
- `sender_normalized: Mapped[str | None]` — `String(255)`, lower-cased name with
  trailing digits stripped.
- `spam_score: Mapped[float | None]` — `Float`, 0.0–1.0.
- `Index("ix_messages_path_prefix_received_at", "path_prefix", "received_at")`
- `Index("ix_messages_sender_normalized_received_at", "sender_normalized", "received_at")`

The Alembic migration must use **batch mode** for the `add_column` operations so it
works on SQLite (which lacks full `ALTER TABLE`) as well as Postgres — the project's
`alembic/env.py` already drives batch mode for SQLite. Follow the existing
add-column migration `alembic/versions/20260515_1920_add_route_type_advert_timestamp.py`.

### 2. Capture the route on message packets (`letsmesh_normalizer.py`)

In `_build_letsmesh_message_payload` (near line 148 where `path_len` is set), also
extract the ordered hop list and add `normalized_payload["path_hashes"]`. Reuse
the same source as `api/routes/packet_groups.py::_extract_path_hashes`
(`decoded.get("path")`), normalized through the existing `_normalize_hash_list`
helper (line 820). `sender_name` is already populated (line 172) — no change there.

### 3. Scoring module (new — `collector/spam.py`)

Pure, unit-testable helpers plus one DB-querying scorer and a config object:

- `normalize_sender(name: str | None) -> str | None` — lower-case, strip trailing
  digits/whitespace (`bob17` → `bob`); None if empty.
- `compute_path_prefix(path_hashes, hops) -> str | None` — join first `hops` hop
  hashes; None if no path.
- `score_message(session, *, path_prefix, sender_normalized, path_len, received_at, cfg) -> float`
  — two windowed `COUNT(*)` queries over `messages` (using the new indexes). The
    cutoff is computed in Python (`cutoff = received_at - timedelta(seconds=cfg.window_seconds)`)
    and passed as a bound parameter — `where(Message.received_at >= cutoff)` — so
    identical code runs on SQLite and Postgres (no SQL `NOW()`/`INTERVAL`):
  - `path_count` = **joint** count: rows with the same `path_prefix` **and** the
    same `sender_normalized` where `received_at >= cutoff` (uses the
    `(path_prefix, received_at)` index, then filters on `sender_normalized`). Only
    runs when both `path_prefix` and `sender_normalized` are present.
  - `name_count` = rows with the same `sender_normalized` in the same window
  - combine: a weighted average over the signals **actually available**,
    normalised by the active weight. With both signals present (weights summing
    to 1.0): `min(1.0, w_path*min(path_count/path_thr,1) + w_name*min(name_count/name_thr,1))`.
  - counts exclude the current row (scored before insert), so a first-ever message
    scores 0.
  - **Minimum-path-length gate:** if `path_len < cfg.min_path_hops` (or there is no
    path at all — e.g. an observer **zero hops** from the sender), the path signal
    is disabled and `path_prefix` is stored null. In that case the **name signal
    stands alone at full weight** (`score = min(1.0, name_count/name_thr)`), *not*
    capped at `w_name`. Without this, name-only spam (`bob1`/`bob2` rotation) on a
    short/zero-hop path could never exceed `w_name` (0.3) and would be permanently
    undetectable below a 0.6 threshold.
- `SpamConfig` dataclass, read once from env (mirrors the `envvar=` pattern in
  `collector/cli.py`). The operational switch lives on the shared `Settings`
  (`common/config.py`) as `spam_detection_enabled` (env `SPAM_DETECTION_ENABLED`) so
  the API reads it too; the UI-facing `feature_spam_detection` (`FEATURE_SPAM_DETECTION`)
  is bridged to it in Compose (see §7):

  | Env var | Default | Meaning |
  |---------|---------|---------|
  | `SPAM_DETECTION_ENABLED` | **false** | Operational switch read by collector + API (bridged from `FEATURE_SPAM_DETECTION`) |
  | `SPAM_WINDOW_SECONDS` | 300 | Sliding window for counts |
  | `SPAM_PATH_HOPS` | 3 | Leading hops that form the prefix |
  | `SPAM_MIN_PATH_HOPS` | 5 | Minimum `path_len` before the path signal applies |
  | `SPAM_PATH_THRESHOLD` | 5 | path_count that saturates the path signal |
  | `SPAM_NAME_THRESHOLD` | 5 | name_count that saturates the name signal |
  | `SPAM_WEIGHT_PATH` | 0.7 | Weight of the path signal |
  | `SPAM_WEIGHT_NAME` | 0.3 | Weight of the name signal |
  | `SPAM_RESCORE_INTERVAL_SECONDS` | 120 | Background re-scoring sweep cadence (`0` disables) |

### 4. Wire scoring into the handler (`collector/handlers/message.py`)

**Guarded by the master switch:** when `spam_detection_enabled` is false, skip all
of the below — `Message` is created with `spam_score`/`path_prefix`/`sender_normalized`
left null, exactly as today (one early `if not cfg.enabled: ...` bypass).

In `_handle_message`, on the **new-insert branch only** (~line 143; not the
duplicate/observer-merge path), before constructing `Message(...)`:

- `path_prefix = compute_path_prefix(payload.get("path_hashes"), cfg.path_hops)`
  (left null when `path_len < cfg.min_path_hops`)
- `sender_normalized = normalize_sender(payload.get("sender_name"))`
- `spam_score = score_message(session, path_prefix=…, sender_normalized=…, path_len=path_len, received_at=now, cfg=cfg)`

Set all three on the `Message` record. This is the **online** score: it counts
only rows that already exist (priors), so the leading edge of a burst scores low
(see the re-scoring sweep below and the limitation note).

**Log the score at ingest.** Extend the existing "Stored … message" log lines
(`handlers/message.py:195-204`) to include `spam_score` and the signals that drove
it, so the score is visible in the collector log without querying the DB, e.g.:

```
Stored channel 0 message [spam=0.84 path=aaa1,aab2 path_n=6 sender=bob]: test...
```

Log at `INFO` when `spam_score >= SPAM_SCORE_THRESHOLD` (so likely-spam stands out)
and keep the normal line otherwise; include the score either way. `score_message`
should return the component counts (path_count/name_count) alongside the score so
they can be logged, and the §4b sweep should log at `DEBUG` when it changes a row's
score (old → new).

### 4b. Background re-scoring sweep (`collector/spam.py` + `subscriber.py`)

A periodic task that recomputes `spam_score` for recent rows **with hindsight** —
counting matching peers across the *whole* window (including messages that arrived
*after* a given row), not just priors. This flags the leading edge of bursts that
the online score necessarily misses, and closes the bursty-evasion hole.

This is a **small** addition because the collector already runs periodic async
tasks in the same pattern: the cleanup scheduler (`subscriber.py:363`) and the
channel-refresh loop (`subscriber.py:483`). Add a third task following that
template:

- `rescore_recent(db, cfg)` in `collector/spam.py` — select rows where
  `received_at >= now - lookback` (a couple of windows), recompute each score via
  the same combine logic but with **symmetric** window counts
  (`abs(other.received_at - row.received_at) <= window`, both directions), and
  `UPDATE` only rows whose score changed. Idempotent.
- Schedule it from `Subscriber` like the existing loops, gated by
  `SPAM_RESCORE_INTERVAL_SECONDS` (default e.g. 120; `0` disables) **and** the
  master switch — the task is not scheduled at all when `spam_detection_enabled`
  is false.

Config-gated so it can ship disabled and be enabled once tuned.

### 5. Display layer — API (`api/routes/messages.py`, `schemas/messages.py`)

`list_messages`:
- Add `include_spam: bool = Query(False)`.
- **Master switch:** when `spam_detection_enabled` is false, apply **no** hide-filter
  at all — every message is returned regardless of stored score (so toggling the
  feature off instantly un-hides everything, including rows scored while it was on).
- When enabled and `include_spam` is False, filter both the count query and the
  results query:
  `where(or_(Message.spam_score < threshold, Message.spam_score.is_(None)))`,
  `threshold = SPAM_SCORE_THRESHOLD` (env, default 0.6).
- Add `spam_score` to the `msg_dict` built ~line 183.
- Update the `@cached` key builder (`_messages_key_builder`) to include
  `include_spam` so cached responses don't leak across toggle states.

`MessageRead`: add `spam_score: Optional[float] = Field(default=None, …)`.

### 6. Display layer — frontend (`web/static/js/spa/pages/messages.js`)

- **Only render the toggle/badge when the feature is enabled.** Add
  `feature_spam_detection` (`FEATURE_SPAM_DETECTION`, default `False`) to
  `common/config.py` and a `"spam"` entry to the `features` property — exactly like
  `feature_packets`/`"packets"`. It flows to the SPA via the existing
  `app.state.features` mechanism; gate the toggle on `features.spam`. Because Compose
  bridges `SPAM_DETECTION_ENABLED=${FEATURE_SPAM_DETECTION}`, the UI flag and the
  API's hide behaviour move together, so the toggle is never shown while the API is
  returning everything (or vice-versa).
- Add a "Show potential spam" checkbox to the existing filter card
  (`renderFilterCard` in `components.js`), bound to URL param `?include_spam=true`,
  default off, following the existing select-filter pattern.
- Optionally tag rows with `spam_score >= threshold` with a small badge when shown.
- Add the i18n label(s) to `web/static/locales/en.json`.

### 7. Config & docs

Config plumbing (vars are passed explicitly per service, not via `env_file`):

- `common/config.py` — add `feature_spam_detection` (default `False`) next to the
  other `feature_*` fields and map `"spam": self.feature_spam_detection` into the
  `features` property; add `spam_detection_enabled` (default `False`) next to the
  other `*_enabled` ops flags, plus the scoring fields.
- **`.env.example`** — add a new commented `# Spam Detection` block led by
  `FEATURE_SPAM_DETECTION=false` (the one switch operators set), with the bridged
  `SPAM_DETECTION_ENABLED` documented as Compose-derived, followed by the `SPAM_*`
  scoring vars and `SPAM_SCORE_THRESHOLD`. Mirror the Data-Retention / raw-packet
  blocks (which document `FEATURE_PACKETS` driving `RAW_PACKET_CAPTURE_ENABLED`).
- **`docker-compose.yml`** — bridge and thread vars the same way as raw-packets
  (`- VAR=${VAR:-default}`): collector service gets
  `SPAM_DETECTION_ENABLED=${FEATURE_SPAM_DETECTION:-false}` + all scoring/sweep vars;
  the **api** service gets the same bridged `SPAM_DETECTION_ENABLED` +
  `SPAM_SCORE_THRESHOLD`. Apply to `docker-compose.prod.yml` if it enumerates these.

Docs:

- **`docs/configuration.md`** — add a new `## Spam Detection` section (var table in
  the same format as `## Data Retention`) listing every `SPAM_*` var, its default,
  and which service reads it (collector vs API), and documenting the
  `SPAM_DETECTION_ENABLED=${FEATURE_SPAM_DETECTION}` bridge; add a `FEATURE_SPAM_DETECTION`
  row to the `## Feature Flags` table (noting, like `FEATURE_PACKETS`, that it also
  drives the backend switch in Compose).
- Note in user-facing docs that the feature is **off by default** and describe the
  scoring behaviour + "show potential spam" toggle.
- Update `SCHEMAS.md` with the new `messages` columns.

### 8. Tests — run against **both** SQLite and Postgres

The scoring queries (windowed `COUNT(*)`, the joint `path_prefix`+`sender_normalized`
filter, the `or_(... is_(None))` display filter) can pass on SQLite and break on
Postgres (or vice-versa), so the DB-touching tests must exercise **both** backends.

The project **already** has a backend switch — no new mechanism is needed, just
correct fixture reuse. The whole suite runs against Postgres with:

```
TEST_DATABASE_BACKEND=postgres \
TEST_POSTGRES_URL="postgresql+psycopg2://postgres:postgres@localhost:55432/test" \
make test
```

Default (no env) runs SQLite. `TEST_DATABASE_BACKEND` defaults to `sqlite`; setting
`postgres` requires `TEST_POSTGRES_URL` (else the fixture **skips**). The
`tests/test_api/conftest.py` fixtures (`db_backend`/`db_url`/`api_db_engine`,
schema via `create_all`, per-xdist-worker Postgres DBs) already honor this.

Implications for the new tests:

- **API spam tests** go in `tests/test_api/test_messages.py` using the existing
  `api_db_session`/test-client fixtures → they run on **both** backends for free
  under the command above. No fixture work.
- **Collector spam tests** are the gap: `tests/test_collector/conftest.py` hardcodes
  `sqlite:///:memory:` (`db_manager`, `async_db_session`). Make these backend-aware
  so `score_message`/`rescore_recent`/handler tests also run on Postgres — extract
  the `db_backend`/`db_url` helper from `tests/test_api/conftest.py` into the shared
  `tests/conftest.py` and have the collector fixtures consume it (falling back to
  in-memory SQLite when `TEST_DATABASE_BACKEND` is unset).
- **Pure-function tests** (`normalize_sender`, `compute_path_prefix`) need no DB.
- **Migration on Postgres:** the suite builds schema via `create_all`, so it does
  **not** exercise the Alembic batch migration. Verifying the migration on Postgres
  stays a manual step (see Verification) unless we add a dedicated migration test.

Coverage:
- Seed N identical-path/identical-sender rows → assert online `score_message` rises
  past threshold; assert a diverse busy path (many senders) does **not**.
- Handler test: feed duplicate messages → assert `spam_score`, `path_prefix`,
  `sender_normalized` populated; assert short-path (`< SPAM_MIN_PATH_HOPS`) rows get
  null `path_prefix` and rely on the name signal.
- `rescore_recent`: insert a burst out of order → assert the leading-edge rows get
  re-scored above threshold with hindsight.
- API (`tests/test_api/test_messages.py`): spammy rows hidden by default, visible
  with `include_spam=true`; cache key differs per toggle state.
- **Master switch (both collector and API):** with `spam_detection_enabled=false`
  (the backend flag the services read), the handler stores null `spam_score` (no
  scoring) and the API returns **all** rows including ones with a high stored score;
  with it true, scoring + hiding apply. (Tests set the backend flag directly; the
  `FEATURE_SPAM_DETECTION` bridge is a Compose concern, verified in step 1.)

## Affected Files

| File | Change |
|------|--------|
| `src/meshcore_hub/common/config.py` | Add `feature_spam_detection` (+ `"spam"` in `features`) and `spam_detection_enabled` ops switch (both default `False`) + scoring fields |
| `src/meshcore_hub/common/models/message.py` | Add `path_prefix`, `sender_normalized`, `spam_score` columns + 2 composite indexes |
| `src/meshcore_hub/collector/letsmesh_normalizer.py` | Add `path_hashes` to the normalized message payload |
| `src/meshcore_hub/collector/spam.py` | **New** — `normalize_sender`, `compute_path_prefix`, `score_message`, `rescore_recent`, `SpamConfig` |
| `src/meshcore_hub/collector/handlers/message.py` | Compute + store `path_prefix`/`sender_normalized`/`spam_score` on insert |
| `src/meshcore_hub/collector/subscriber.py` | Add periodic re-scoring task alongside the existing cleanup/channel-refresh loops |
| `src/meshcore_hub/collector/cli.py` | Wire `SPAM_*` env/config options (incl. `SPAM_RESCORE_INTERVAL_SECONDS`) |
| `src/meshcore_hub/api/routes/messages.py` | `include_spam` param, default-hide filter, `spam_score` in response, cache key |
| `src/meshcore_hub/common/schemas/messages.py` | Add `spam_score` to `MessageRead` |
| `src/meshcore_hub/web/static/js/spa/pages/messages.js` | "Show potential spam" toggle + optional badge |
| `src/meshcore_hub/web/static/locales/en.json` | Toggle/badge labels |
| `alembic/versions/` | Migration for the 3 new columns + 2 indexes |
| `.env.example` | New `# Spam Detection` block led by `FEATURE_SPAM_DETECTION` |
| `docker-compose.yml` (+ `docker-compose.prod.yml` if it lists these) | Bridge `SPAM_DETECTION_ENABLED=${FEATURE_SPAM_DETECTION:-false}` into collector (+ scoring vars) and api (+ `SPAM_SCORE_THRESHOLD`) env blocks |
| `docs/configuration.md` | New `## Spam Detection` var table + `FEATURE_SPAM_DETECTION` row in `## Feature Flags` |
| `docs/` (user-facing) | Document scoring, toggle, off-by-default behaviour |
| `SCHEMAS.md` | Update `messages` schema |
| `tests/conftest.py` + `tests/test_collector/conftest.py` | Make collector DB fixtures backend-aware: lift the `db_backend`/`db_url` helper out of `tests/test_api/conftest.py` into the shared conftest so `db_manager`/`async_db_session` honor `TEST_DATABASE_BACKEND`/`TEST_POSTGRES_URL` (default SQLite) |
| `tests/test_collector/` | Unit tests for `normalize_sender`, `compute_path_prefix`; DB tests for `score_message`, `rescore_recent`, and the handler (run on both backends via the env switch) |
| `tests/test_api/test_messages.py` | Default-hide vs `include_spam=true` behavior (uses existing `api_db_*` fixtures → both backends) |

## Verification

1. `meshcore-hub db upgrade` succeeds; `messages` shows the 3 columns + 2 indexes.
   With `FEATURE_SPAM_DETECTION` unset (default → bridged `SPAM_DETECTION_ENABLED=false`),
   confirm ingest writes null `spam_score`, the API hides nothing, and the UI shows
   no spam toggle — i.e. the feature is fully dark out of the box. Then set
   `FEATURE_SPAM_DETECTION=true` (or `SPAM_DETECTION_ENABLED=true` when running
   services directly without Compose) for the remaining steps.
2. Run the collector against seed/sample MQTT data (`seed/`,
   `docker-compose.dev.yml`); confirm new rows get `path_prefix`,
   `sender_normalized`, and a `spam_score`.
3. Replay a burst of near-identical messages sharing a path prefix with
   `path_len >= SPAM_MIN_PATH_HOPS`; later rows score above
   `SPAM_SCORE_THRESHOLD`. Confirm a short-path burst (`path_len <` gate) is **not**
   flagged on the path signal alone.
4. `GET /api/v1/messages` hides flagged rows by default; `?include_spam=true`
   returns them with `spam_score` populated; the UI toggle reflects this.
5. `pytest` (unit + handler + API) green; `ruff`/`mypy` clean per
   `.pre-commit-config.yaml`.
6. Run the full suite on **both** backends and confirm green:
   - SQLite (default): `make test`
   - Postgres: `TEST_DATABASE_BACKEND=postgres TEST_POSTGRES_URL="postgresql+psycopg2://postgres:postgres@localhost:55432/test" make test`
   This confirms the windowed/joint counts and the display filter behave identically
   on both. Separately, apply the **Alembic migration** to a Postgres DB
   (`meshcore-hub db upgrade` against the test cluster) to prove the batch
   `add_column` + composite indexes apply there — the suite builds schema via
   `create_all`, so the migration itself is not covered by tests.
7. **Cross-observer stability:** confirm the same logical message seen by multiple
   observers stores the same origin-side `path_prefix` (`decoded.path` is
   origin-first — already relied on by the Packets page, so `path_hashes[:N]` is
   correct).
8. **Channel sender check:** confirm `sender_name` is populated from the
   `"<Sender Name>: "` body prefix for public-channel messages, and that
   `normalize_sender` strips the rotating suffix (`bob1`/`bob2` → `bob`).

## Notes / Non-goals

- **Backfill:** existing rows have null `path_prefix`/`sender_normalized`, so they
  don't contribute to counts until re-seen. Because the window is minutes, counts
  self-heal; no historical backfill (which would require re-decoding `raw_packets`)
  in v1.
- **Content fingerprinting** (text shingling, after stripping the `"<Name>: "`
  prefix) is a future tertiary signal, not in scope now.
- **Frozen score / leading edge of bursts.** The *online* score (set at insert)
  counts only priors, so the first `~path_thr` messages of a burst score low and,
  without re-scoring, stay shown forever — and **bursty** spam (a few messages, a
  pause longer than the window, repeat) could evade entirely because the online
  count restarts at zero each burst. This is exactly what the §4b background
  re-scoring sweep addresses by counting peers symmetrically (with hindsight).
  `SPAM_PATH_THRESHOLD` is the precision/recall knob: higher = fewer false
  positives but more of each burst's head leaks until the sweep catches it.
