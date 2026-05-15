# Plan: Fix Recent Advertisements Date Always Showing Today

**Date:** 2025-05-15
**Status:** Draft
**Scope:** API only (advertisements endpoint)

## Problem

The "Recent Advertisements" section on the Node detail page always shows today's date, while the time portion is accurate. The root cause is a missing `public_key` query parameter filter on the API endpoint.

## Root Cause Analysis

### Missing `public_key` filter in advertisements API

**Location:** `src/meshcore_hub/api/routes/advertisements.py:44`

The node detail page fetches advertisements with:

```js
// node-detail.js:86
apiGet('/api/v1/advertisements', { public_key: publicKey, limit: 10 })
```

But the `list_advertisements` endpoint does **not accept a `public_key` query parameter**. FastAPI silently ignores unknown query params, so the `public_key` filter is dropped. The API returns the 10 most recent advertisements across **all nodes** (sorted by `received_at DESC`), not filtered to the specific node.

Since results are the most recent network-wide ads, they cluster around the current time — making it appear that all dates show today.

### Sibling endpoints checked (no issues found)

- **Telemetry**: Already has `node_public_key` filter (`telemetry.py:23`) — the frontend passes `node_public_key` which the API correctly applies
- **Messages**: Not called from the node detail page — no impact
- **Nodes**: Uses path parameter (`/api/v1/nodes/{public_key}`) — no issue

## Plan of Changes

### Step 1: Add `public_key` filter to advertisements API route

**File:** `src/meshcore_hub/api/routes/advertisements.py`

- Add a `public_key: Optional[str] = Query(None, ...)` parameter to `list_advertisements`
- Add a filter clause: `if public_key: query = query.where(Advertisement.public_key == public_key)`
- This filters by the **source** node's public key (the node that sent the advertisement)

### Step 2: Update API tests

**File:** `tests/test_api/test_advertisements.py`

- Add a test for the `public_key` query parameter filtering
- Verify ads returned match the requested public key
- Verify ads with different public keys are excluded

### Step 3: Verify frontend formatting

No frontend changes needed. The `public_key` query param is already sent by `node-detail.js:86`. Once the API honors the filter, the node detail page will show only that node's most recent advertisements (which should span multiple dates, not just today).

## Files Changed

| File | Change |
|------|--------|
| `src/meshcore_hub/api/routes/advertisements.py` | Add `public_key` query parameter filter |
| `tests/test_api/test_advertisements.py` | Test `public_key` filter |

## Testing

```bash
source .venv/bin/activate
pytest tests/test_api/test_advertisements.py -v
pre-commit run --all-files
```

## Verification

After deploying the fix:
1. Navigate to a node detail page with historical advertisement data
2. Verify the "Recent Advertisements" table shows ads spanning multiple dates (not all today)
3. Verify the ad count is limited to 10 and only belongs to the viewed node

## Risk Assessment

- **Low risk:** Adding an optional query parameter is backward-compatible
- **No migration needed:** No schema changes to database tables
- **No frontend changes needed:** The frontend already sends the parameter
