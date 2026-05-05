# Plan: esbuild Bundling + Cache Busting for Static Assets

**Date:** 2025-05-05
**Status:** Draft

## Problem

Only 4 of ~30+ static assets have cache-busting query parameters. ES module sub-imports (`components.js`, `router.js`, `i18n.js`, etc.) and all vendor libraries are cached at most 1 hour with no invalidation mechanism. The `?v={{ version }}` on `app.js` is the only entry into the ES module graph, but browsers strip query parameters when resolving relative imports -- so the entire module tree loads unversioned.

### Current state

| Asset | Cache busting | Cache-Control |
|-------|--------------|---------------|
| `tailwind.css` | `?v={{ version }}` | `immutable` (1 year) |
| `app.css` | `?v={{ version }}` | `immutable` (1 year) |
| `charts.js` | `?v={{ version }}` | `immutable` (1 year) |
| `app.js` (SPA entry) | `?v={{ version }}` | `immutable` (1 year) |
| All other SPA modules (~14 files) | None | 1 hour |
| All page modules (11 files) | None | 1 hour |
| lit-html (via import map) | None | 1 hour |
| Leaflet CSS/JS | None | 1 hour |
| Chart.js, QRCode.js | None | 1 hour |
| Locale JSON files | None | 1 hour |
| Static images (logo, meshcore) | None | 1 hour |

## Solution

Use **esbuild** to bundle and minify the SPA JavaScript, generating content-hashed filenames for automatic cache invalidation. Add `?v=` cache busting to vendor libs that remain as global `<script>` tags.

### Why esbuild

| Factor | esbuild | Rollup | Terser-only | Native fix |
|--------|---------|--------|-------------|------------|
| Content hashing | Built-in | Plugin needed | Manual | Manual + complex |
| Dynamic import splitting | `--splitting` | Yes | N/A | Breaks |
| Tree-shaking | Yes | Best | No | No |
| Minification | Built-in | Plugin | Yes | No |
| New deps | 1 package (~10 MB) | 3+ (~15 MB) | 1 (~3 MB) | 0 |
| Config | CLI flags (1 line) | Config file | build.js loop | Half a bundler |
| Import map | Eliminated (bundles lit-html) | Same | Keeps | Keeps |

- The project already uses Node.js for builds (Tailwind CLI, vendor copying)
- SPA JS is ~195 KB unminified across 18 files -- esbuild processes it in <50ms
- lit-html (~10 KB) gets bundled in, eliminating the import map
- Dynamic imports preserved via `--splitting` (each page stays a separate chunk)
- Vendor IIFE libs (Leaflet, Chart.js, QRCode.js) stay as-is

### Estimated impact

| Metric | Current | After |
|--------|---------|-------|
| SPA JS (initial load) | ~42 KB unminified (7+ files) | ~18-20 KB minified (1-2 chunks) |
| SPA JS (total) | ~195 KB unminified | ~80-90 KB minified |
| HTTP requests (initial) | 7+ JS files | 1-2 JS files |
| Cache invalidation | Version-based (all-or-nothing) | Content-hash (per-file) |

## Implementation

### Step 1: Add esbuild to build pipeline

**File:** `package.json`

Add `esbuild` as a dev dependency:

```json
"devDependencies": {
    "esbuild": "^0.25"
}
```

> Note: esbuild is only needed at build time. In Docker, it's installed via `npm ci` in the frontend stage and discarded. It could alternatively run via `npx esbuild` without adding to `package.json`, but listing it explicitly ensures version pinning via `package-lock.json`.

**File:** `build.js`

Add an esbuild step after the Tailwind build:

1. Define a `DIST` output directory: `src/meshcore_hub/web/static/dist/`
2. Run esbuild via `execSync`:
   ```
   npx esbuild src/meshcore_hub/web/static/js/spa/app.js
     --bundle --format=esm --splitting --minify
     --outdir=src/meshcore_hub/web/static/dist
     --entry-names=[name].[hash].js
     --chunk-names=chunks/[name].[hash].js
     --metafile=src/meshcore_hub/web/static/dist/meta.json
   ```
   - `--splitting`: preserves dynamic `import()` as separate chunks
   - `--format=esm`: output ES modules
   - `--minify`: minify all output
   - `--entry-names=[name].[hash].js`: content-hashed filenames for entry points
   - `--chunk-names=chunks/[name].[hash].js`: content-hashed filenames for shared chunks
   - `--metafile`: generates a JSON manifest mapping inputs to outputs
3. Post-process `metafile` to generate a simplified `assets.json` manifest:
   ```json
   {
     "app.js": "app.abc123.js",
     "chunks/shared.def456.js": "chunks/shared.def456.js"
   }
   ```
4. Compute SHA256 content hashes (first 8 hex chars) for vendor files (Leaflet, Chart.js, QRCode.js, their CSS) and all locale JSON files combined. Add to `assets.json`:
   ```json
   {
     "app.js": "app.abc123.js",
     "vendor": {
       "leaflet.css": "a1b2c3",
       "leaflet.js": "d4e5f6",
       "chart.umd.min.js": "g7h8i9",
       "qrcode.min.js": "j0k1l2"
     },
     "locale_version": "m3n4o5"
   }
   ```
   **Vendor hashes** are computed per-file using `crypto.createHash("sha256")`,
   reading each file's contents. **`locale_version`** is computed by hashing the
   concatenated contents of ALL locale JSON files in the `locales/` directory
   (sorted by filename for determinism) — any locale change invalidates all
   locale caches. This value is passed to the SPA via `_build_config_json()` so
   `i18n.js` can append `?v=` to its fetch URL.
5. Remove the lit-html vendor copy step (lines 29-46 of `build.js`) since esbuild bundles it from `node_modules`.

**File:** `.gitignore`

Add the `dist/` output directory:
```
src/meshcore_hub/web/static/dist/
```

### Step 2: Python manifest loader

**File:** `src/meshcore_hub/web/app.py`

1. Add a `_load_asset_manifest()` function that reads `assets.json` from `STATIC_DIR / "dist" / "assets.json"` at startup. Returns an empty dict if the file doesn't exist (for bare source installs without a build step).

2. Store the manifest on `app.state.asset_manifest` during `create_app()`.

3. Pass asset paths to the Jinja2 template context:
   - `asset_app_js`: the hashed app entry point (e.g., `"app.abc123.js"`)
   - `vendor_hashes`: dict of vendor file hashes (e.g., `{"leaflet.css": "a1b2c3", ...}`)

4. The `_build_config_json()` function should include `locale_version` from the manifest so the SPA's `i18n.js` can append it to locale fetch URLs.

### Step 3: Update spa.html template

**File:** `src/meshcore_hub/web/templates/spa.html`

1. **Remove** the `<script type="importmap">` block (lines 49-57). lit-html is now bundled by esbuild.

2. **Update** the SPA entry point (line 210):
   ```html
   <!-- Before -->
   <script type="module" src="/static/js/spa/app.js?v={{ version }}"></script>

   <!-- After -->
   <script type="module" src="/static/dist/{{ asset_app_js }}"></script>
   ```

3. **Add** `?v=` cache busting to vendor `<script>` and `<link>` tags:
   ```html
   <!-- Leaflet CSS -->
   <link rel="stylesheet" href="/static/vendor/leaflet/leaflet.css?v={{ vendor_hashes['leaflet.css'] }}" />

   <!-- Leaflet JS -->
   <script src="/static/vendor/leaflet/leaflet.js?v={{ vendor_hashes['leaflet.js'] }}"></script>

   <!-- Chart.js -->
   <script src="/static/vendor/chart.js/chart.umd.min.js?v={{ vendor_hashes['chart.umd.min.js'] }}"></script>

   <!-- QRCode.js -->
   <script src="/static/vendor/qrcodejs/qrcode.min.js?v={{ vendor_hashes['qrcode.min.js'] }}"></script>
   ```

4. `charts.js` remains unchanged (it already has `?v={{ version }}`, which is fine since it changes with releases).

5. **Graceful fallback**: If `asset_app_js` is empty (no `dist/` directory), fall back to the original `app.js?v={{ version }}` path. This ensures source installs without `npm run build` still work.

### Step 4: Update i18n.js locale fetching

**File:** `src/meshcore_hub/web/static/js/spa/i18n.js`

The locale JSON fetch at line 23 needs a cache-busting parameter. Since this file is now bundled by esbuild, the version string must come from the embedded `window.__APP_CONFIG__`:

```javascript
// Before
const res = await fetch(`/static/locales/${locale}.json`);

// After
const config = window.__APP_CONFIG__ || {};
const v = config.locale_version || '';
const res = await fetch(`/static/locales/${locale}.json${v ? '?v=' + v : ''}`);
```

The `locale_version` value is set by `build.js` (content hash of all locale files combined) and passed through the Python config JSON.

### Step 5: Update static image references

**File:** `src/meshcore_hub/web/static/js/spa/pages/home.js`

Two hardcoded image references without cache busting:
- Line ~168: `'/static/img/logo.svg'`
- Line ~221: `"/static/img/meshcore.svg"`

These are embedded in lit-html templates and rarely change. Options:
- **(A)** Include image hashes in the manifest and reference them via `window.__APP_CONFIG__` -- adds complexity for minimal benefit.
- **(B)** Leave as-is with the existing 1-hour cache -- images rarely change and are small.

**Recommendation:** Option B. Images are small SVGs that rarely change. The 1-hour cache is acceptable.

### Step 6: Update Dockerfile

**File:** `Dockerfile`

Add a `COPY --from=frontend` line to overlay the `dist/` directory:

```dockerfile
# Overlay built frontend assets onto source tree
COPY --from=frontend /app/src/meshcore_hub/web/static/vendor ./src/meshcore_hub/web/static/vendor
COPY --from=frontend /app/src/meshcore_hub/web/static/css/tailwind.css ./src/meshcore_hub/web/static/css/tailwind.css
COPY --from=frontend /app/src/meshcore_hub/web/static/dist ./src/meshcore_hub/web/static/dist
```

The `dist/` directory is generated by `npm run build` in the frontend stage and includes:
- `app.[hash].js` (SPA entry point)
- `chunks/` directory (shared chunks, page modules)
- `assets.json` (manifest for Python to read)
- `meta.json` (esbuild metafile, optional -- could be excluded from Docker image)

### Step 7: Remove vendored lit-html

**Files to remove:** `src/meshcore_hub/web/static/vendor/lit-html/` (entire directory)

This directory is already gitignored (line 226 of `.gitignore`). The lit-html vendor copy step in `build.js` (lines 29-46) is removed in Step 1.

## Middleware impact

**File:** `src/meshcore_hub/web/middleware.py`

The `/static/dist/` directory serves content-hashed files (the filename itself is the cache-buster — when content changes, the filename changes). These need `immutable` caching:

```python
# Static dist/ files use content-hashed filenames — immutable
elif path.startswith("/static/dist/"):
    response.headers["cache-control"] = "public, max-age=31536000, immutable"
```

Add this rule **before** the generic `/static/` rule (line 50-51) so it takes priority. Placement:

1. `/health` → `no-cache` *(unchanged)*
2. `/static/` + `v=` → `immutable` *(unchanged)*
3. **`/static/dist/` → `immutable`** *(new)*
4. `/static/` → `1-hour` *(unchanged)*

The `?v=` params on vendor files (e.g., `/static/vendor/leaflet/leaflet.css?v=hash`) already match rule 2 and get `immutable`. No changes needed for the vendor path pattern.

## Development workflow

- `npm run build` is required after any JS change to see it reflected
- Source files in `js/spa/` remain the source of truth
- `dist/` is a build artifact (gitignored)
- For CSS-only changes, only the Tailwind build runs (esbuild step is fast enough that running it is harmless)

## Files changed

| File | Change |
|------|--------|
| `package.json` | Add `esbuild` to devDependencies |
| `build.js` | Add esbuild step, generate manifest, remove lit-html vendor copy |
| `.gitignore` | Add `src/meshcore_hub/web/static/dist/` |
| `Dockerfile` | Add `COPY --from=frontend` for `dist/` directory |
| `src/meshcore_hub/web/app.py` | Add manifest loader, pass asset paths to template |
| `src/meshcore_hub/web/templates/spa.html` | Remove import map, use hashed bundle path, add vendor `?v=` |
| `src/meshcore_hub/web/middleware.py` | Add `/static/dist/` immutable cache rule |
| `src/meshcore_hub/web/static/js/spa/i18n.js` | Add `?v=` to locale fetch URL |

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Source install without `npm run build` breaks | Fallback in `spa.html`: if `asset_app_js` is empty, use original `app.js?v={{ version }}` path |
| esbuild `--splitting` requires HTTP/2 for optimal loading | Already the case with current native ES modules (multiple parallel requests) |
| Dynamic import paths change after bundling | esbuild handles this automatically -- `import('./pages/home.js')` becomes `import('./chunks/home.abc123.js')` in the output |
| lit-html import map removal breaks third-party extensions | Import map was only used internally. No external consumers. |
| Build step required for every JS change during development | Accepted trade-off. esbuild is <50ms. `npm run build` is already required for Tailwind. |

## Future considerations

- The `charts.js` file could be converted to an ES module and imported by the dashboard page module, eliminating the need for a separate `<script>` tag and the global `Chart` dependency.
- Vendor libs (Leaflet, Chart.js, QRCode.js) could be converted to ES module imports in the pages that use them, allowing esbuild to tree-shake unused code. This is a larger refactor.
- The `assets.json` manifest could be extended to include CSS hashes, replacing the `?v={{ version }}` on `tailwind.css` and `app.css` with content hashes.
