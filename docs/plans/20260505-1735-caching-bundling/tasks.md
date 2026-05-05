# Tasks: esbuild Bundling + Cache Busting

Reference: [plan.md](./plan.md)

## Phase 1: Build pipeline

### Task 1.1 — Add esbuild dependency

**File:** `package.json`

- Add `"esbuild": "^0.25"` to `devDependencies`

```json
"devDependencies": {
  "esbuild": "^0.25"
}
```

### Task 1.2 — Update build.js with esbuild step

**File:** `build.js`

1. Add imports: `readFileSync`, `writeFileSync`, `readdirSync` from `node:fs`; `createHash` from `node:crypto`
2. Define `DIST` constant: `join(STATIC, "dist")`
3. After Tailwind build (line 25), add esbuild step:
   - `mkdirSync(DIST, { recursive: true })`
   - Run esbuild via `execSync`:
     ```
     npx esbuild src/meshcore_hub/web/static/js/spa/app.js
       --bundle --format=esm --splitting --minify
       --outdir=src/meshcore_hub/web/static/dist
       --entry-names=[name].[hash].js
       --chunk-names=chunks/[name].[hash].js
       --metafile=src/meshcore_hub/web/static/dist/meta.json
     ```
4. Post-process `meta.json` → `assets.json`:
   - Parse `meta.json`, extract `outputs` → simplify to `{ "app.js": "app.abc123.js", ... }`
5. Compute vendor hashes:
   - For each vendor file (`leaflet.css`, `leaflet.js`, `chart.umd.min.js`, `qrcode.min.js`):
     `createHash("sha256").update(readFileSync(path)).digest("hex").slice(0, 8)`
   - Add to `assets.json` under `"vendor"` key
6. Compute `locale_version`:
   - Read all `*.json` files from `join(STATIC, "locales")`, sorted by filename
   - Concatenate contents, hash with SHA256, take first 8 hex chars
   - Add to `assets.json` as `"locale_version"`
7. Write `assets.json` to `join(DIST, "assets.json")`
8. **Remove** lit-html vendor copy block (lines 29-46)

### Task 1.3 — Update .gitignore

**File:** `.gitignore`

Add after line 226 (`src/meshcore_hub/web/static/vendor/`):
```
src/meshcore_hub/web/static/dist/
```

---

## Phase 2: Python changes

### Task 2.1 — Add manifest loader to app.py

**File:** `src/meshcore_hub/web/app.py`

1. Add `_load_asset_manifest()` helper:
   ```python
   def _load_asset_manifest() -> dict[str, Any]:
       manifest_path = STATIC_DIR / "dist" / "assets.json"
       if not manifest_path.exists():
           return {}
       try:
           return json.loads(manifest_path.read_text())
       except (OSError, json.JSONDecodeError):
           return {}
   ```
2. In `create_app()`, call manifest and store on `app.state`:
   ```python
   manifest = _load_asset_manifest()
   app.state.asset_manifest = manifest
   ```
3. Extract convenience values:
   ```python
   app.state.asset_app_js = manifest.get("app.js", "")
   app.state.vendor_hashes = manifest.get("vendor", {})
   app.state.locale_version = manifest.get("locale_version", "")
   ```
4. In `_build_config_json()`, add to the `config` dict (after line 273):
   ```python
   "locale_version": getattr(app.state, "locale_version", ""),
   ```

### Task 2.2 — Pass asset paths to spa.html template

**File:** `src/meshcore_hub/web/app.py`

In the `spa_catchall` handler (line 1036), add to the template context dict:
```python
"asset_app_js": request.app.state.asset_app_js,
"vendor_hashes": request.app.state.vendor_hashes,
```

### Task 2.3 — Add /static/dist/ immutable cache rule

**File:** `src/meshcore_hub/web/middleware.py`

Insert a new `elif` block between the existing `/static/` + `v=` rule (line 50-51) and the generic `/static/` rule (line 53-55):

```python
# Static dist/ files use content-hashed filenames — immutable
elif path.startswith("/static/dist/"):
    response.headers["cache-control"] = "public, max-age=31536000, immutable"
```

Final rule order:
1. `/health` → `no-cache` (line 46-47, unchanged)
2. `/static/` + `v=` → `immutable` (line 50-51, unchanged)
3. `/static/dist/` → `immutable` (**new**)
4. `/static/` → `1-hour` (line 53-55, unchanged)

---

## Phase 3: Template and frontend

### Task 3.1 — Update spa.html template

**File:** `src/meshcore_hub/web/templates/spa.html`

1. **Remove** the import map block (lines 49-57):
   ```html
   <script type="importmap">
   {
       "imports": {
           "lit-html": "/static/vendor/lit-html/lit-html.js",
           "lit-html/": "/static/vendor/lit-html/"
       }
   }
   </script>
   ```

2. **Update** vendor tags to add `?v=` cache busting:
   - Line 44: `<link rel="stylesheet" href="/static/vendor/leaflet/leaflet.css?v={{ vendor_hashes['leaflet.css'] }}" />`
   - Line 177: `<script src="/static/vendor/leaflet/leaflet.js?v={{ vendor_hashes['leaflet.js'] }}"></script>`
   - Line 180: `<script src="/static/vendor/chart.js/chart.umd.min.js?v={{ vendor_hashes['chart.umd.min.js'] }}"></script>`
   - Line 183: `<script src="/static/vendor/qrcodejs/qrcode.min.js?v={{ vendor_hashes['qrcode.min.js'] }}"></script>`

3. **Update** SPA entry point (line 210):
   ```html
   {% if asset_app_js %}
   <script type="module" src="/static/dist/{{ asset_app_js }}"></script>
   {% else %}
   <script type="module" src="/static/js/spa/app.js?v={{ version }}"></script>
   {% endif %}
   ```

4. `charts.js` (line 186) stays unchanged — already has `?v={{ version }}`.

### Task 3.2 — Update i18n.js locale fetching

**File:** `src/meshcore_hub/web/static/js/spa/i18n.js`

Update line 23:
```javascript
// Before
const res = await fetch(`/static/locales/${locale}.json`);

// After
const config = window.__APP_CONFIG__ || {};
const v = config.locale_version || '';
const res = await fetch(`/static/locales/${locale}.json${v ? '?v=' + v : ''}`);
```

Note: `window.__APP_CONFIG__` is already set by the inline `<script>` in spa.html that parses `config_json`.

---

## Phase 4: Docker and cleanup

### Task 4.1 — Update Dockerfile

**File:** `Dockerfile`

Add after line 49 (`COPY --from=frontend ... tailwind.css`):
```dockerfile
COPY --from=frontend /app/src/meshcore_hub/web/static/dist ./src/meshcore_hub/web/static/dist
```

This overlays the bundled JS (`app.[hash].js`, `chunks/`, `assets.json`) onto the source tree before `pip install`.

### Task 4.2 — Remove lit-html vendor copy from build

**File:** `build.js`

Already covered in Task 1.2 step 8 — remove lines 29-46 (the `vendor("lit-html", ...)` calls).

No separate action needed.

---

## Phase 5: Verify

### Task 5.1 — Build and verify

1. `npm install` — installs esbuild
2. `npm run build` — should produce:
   - `src/meshcore_hub/web/static/dist/app.[hash].js`
   - `src/meshcore_hub/web/static/dist/chunks/[name].[hash].js` (shared chunks)
   - `src/meshcore_hub/web/static/dist/assets.json`
   - `src/meshcore_hub/web/static/dist/meta.json`
3. Verify `assets.json` contains `app.js`, `vendor`, and `locale_version` keys
4. `meshcore-hub web` — dashboard should load with bundled JS
5. Check browser DevTools Network tab:
   - `/static/dist/app.*.js` → `Cache-Control: public, max-age=31536000, immutable`
   - `/static/vendor/leaflet/leaflet.css?v=*` → `Cache-Control: public, max-age=31536000, immutable`
   - `/static/locales/en.json?v=*` → `Cache-Control: public, max-age=31536000, immutable`

### Task 5.2 — Fallback test

1. Delete `dist/` directory
2. `meshcore-hub web` — dashboard should load using `app.js?v={{ version }}` fallback
3. Verify no errors in browser console

### Task 5.3 — Run tests

```bash
source .venv/bin/activate
pytest tests/test_web/ -v
pre-commit run --all-files
```
