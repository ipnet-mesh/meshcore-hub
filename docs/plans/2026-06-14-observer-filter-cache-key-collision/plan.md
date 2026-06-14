# Fix: Observer filter "disappears" message — cache key collision

## Context

User report: a message received by observer **A** shows when filtering by A, but
**disappears when a second observer B is also enabled** — appearing to behave like
AND instead of OR.

Investigation findings:

- **The filter logic is correct and is OR.** `observed_by_filter_clause`
  (`src/meshcore_hub/api/observer_utils.py:13`) builds
  `event_hash IN (SELECT ... WHERE Node.public_key IN (:keys))`, i.e. a record
  matches if observed by **any** selected observer. Tests assert this
  (`tests/test_api/test_messages.py::test_filter_by_observed_by_multiple`).
- The primary observer is always written to the `event_observers` junction table at
  ingest (`collector/handlers/message.py:162`), so OR filtering sees it.
- The frontend correctly sends repeated params: `?observed_by=A&observed_by=B`
  (`web/static/js/spa/api.js` appends each array item; `pages/messages.js:263`).

**Primary root cause — the web proxy collapses repeated params.** The SPA calls
the backend through the web API proxy (`src/meshcore_hub/web/app.py:696`
`api_proxy`). It forwarded query params with:

```python
params = dict(request.query_params)   # collapses repeated keys to LAST value
```

`dict(QueryParams)` keeps only the last value of a repeated key, so
`?observed_by=A&observed_by=B` was forwarded to the backend as `observed_by=B`
only. The backend then filtered to B's events, dropping the A-only message — the
exact reported symptom, and independent of caching. Fix: forward
`request.query_params.multi_items()` (a list of `(key, value)` tuples; httpx
preserves them as repeated params).

**Secondary root cause — cache key collision.** The cached-response key is built by
`sorted_query_string` (`src/meshcore_hub/api/cache.py:15`):

```python
params = list(request.query_params.items())   # collapses repeated keys to LAST value
```

In Starlette, `QueryParams.items()` keeps only the **last** value of a repeated key
(`multi_items()` is the one that preserves all). So `?observed_by=A&observed_by=B`
produces the cache key fragment `observed_by=B` only. Every distinct observer set
sharing the same *last* `observed_by` value collides on one Redis key, and whichever
response populated it first (e.g. a prior "B only" query, which omits the A-only
message) is served for the TTL window. Hence the message "disappears" when B is
enabled. Only manifests when Redis caching is enabled.

Affected endpoints: anything cached with repeated query params — messages
(`_messages_key_builder`) and advertisements (`@cached("advertisements")` default
key), both of which accept repeated `observed_by`.

## Change

Single-line fix in the shared helper, plus a regression test.

### 1. `src/meshcore_hub/api/cache.py` — `sorted_query_string`

Use `multi_items()` so repeated query params are all included in the cache key.
Sort by the full `(key, value)` tuple so order-independent observer sets
(`A&B` vs `B&A`) still map to the same key (matching OR semantics).

```python
def sorted_query_string(request: Request) -> str:
    """Build a deterministic query string from request params, sorted by key.

    Uses multi_items() so repeated query params (e.g. observed_by) are all
    preserved; items() would collapse them to the last value and cause cache
    key collisions between different filter sets.
    """
    params = request.query_params.multi_items()
    if not params:
        return ""
    params = sorted(params)          # sort by (key, value) -> order-independent
    return urlencode(params)
```

No other call sites change — every key builder
(`messages`, `advertisements`, `channels`, `packets`, `packet_groups`, `dashboard/*`)
routes through this one helper and benefits automatically.

### 2. Regression test (cache helper)

`tests/test_api/test_cache.py` already exists with a `TestSortedQueryString` class.
Add cases there using the same `Request(scope)` pattern (build a scope with a
`query_string` of `b"observed_by=A&observed_by=B"`), asserting:
- the resulting string contains **both** `observed_by=A` and `observed_by=B`;
- `observed_by=A&observed_by=B` and `observed_by=B&observed_by=A` produce the
  **same** string;
- it differs from the string for `observed_by=B` alone (the collision case that
  caused the bug).

## Verification

1. Unit: `uv run pytest tests/test_api/test_cache.py` and the existing
   `tests/test_api/test_messages.py::...test_filter_by_observed_by_multiple` /
   advertisements equivalent still pass.
2. End-to-end with Redis enabled:
   - Seed a message observed only by A.
   - `GET /api/v1/messages?observed_by=<B>` (warms the colliding key) → empty.
   - `GET /api/v1/messages?observed_by=<A>&observed_by=<B>` → **must include the
     message** (previously returned the stale empty "B" response).
   - In the UI: enable A (message visible), then also enable B — message stays
     visible.
3. Sanity: confirm distinct filter combinations now yield distinct response
   behavior (no cross-talk between observer sets).

## Notes / out of scope

- The OR semantics are intended and unchanged. If the user actually wants AND
  ("observed by *all* selected"), that is a separate feature (would require a
  `GROUP BY event_hash HAVING COUNT(DISTINCT observer)=N` style clause) — not
  included here.
