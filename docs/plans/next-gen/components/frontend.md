# Frontend

> **Related decisions:** D7 (realtime transport — SSE drives live pages, with polling as fallback; the `useEventStream` hook patches the TanStack Query cache on SSE events), D9 (frontend client gen — `orval`, committed upfront; `openapi-fetch` as documented fallback), D20 (custom pages move to DB — admin UI page for CRUD).

## Frontend redesign (overview)

Keep React 19 + Vite + TanStack Query + Tailwind/DaisyUI + react-router. The architecture is fine; the *discipline* changes.

### Codegen'd client + typed queries

- **`orval`** generates the typed API client + TanStack Query hooks from the OpenAPI spec (D9 — committed upfront): `useMessagesQuery`, `useNodeTagsMutation`, etc., keyed by operation ID. `openapi-fetch` is the documented fallback only, not the primary path.
- Delete every hand-written `interface NodeItem` / `Channel` / `Profile` copy.

### Route-level code-splitting

- `lazy(() => import(...))` for `MapPage`, `Dashboard`, `CustomPage`, `Routes` (the big ones). Vendor-split chart.js, leaflet, react-markdown into lazy chunks loaded on demand.
- Target: <200 KB initial JS (shell + nav + home), rest on demand.

### One data-fetching pattern

- All reads go through generated query hooks. No raw `useEffect`+`AbortController`. No multi-fetch-in-one-`queryFn`.
- For composite views (Dashboard, Messages-with-observers), use `useQueries` or a dedicated **aggregating API endpoint** so the client isn't orchestrating.

### Static, cacheable shell

- The HTML shell becomes a **build-time artifact** served as a static file (or via CDN). It contains no user-specific data.
- `__APP_CONFIG__` is split: **static** network config baked at build time; **dynamic** user/role data fetched via `GET /api/v1/me` (returns the resolved `Principal`). The SPA renders the public shell immediately and personalizes after the `/me` call.
- Announcements, feature flags, custom pages nav: fetched once from `/api/v1/config` and cached.

### Realtime where it matters

- Live pages (Messages, Packets, Dashboard activity) subscribe to the SSE stream and patch their query caches optimistically.
- TanStack Query's `query.cache.setQueryData` on SSE events gives instant updates; `refetchOnWindowFocus` and the 30s poll become a safety net.

### Consolidate orchestration

- Server-side aggregation endpoint for observer-area filtering (return the area map from the API; client just renders). Removes the 500-node client fetch.
- Replace hand-rolled debounce in Routes modal with `useDeferredValue` / a `useDebounce` hook.
- Extract a `Popover` component for path-hop bubbles.
- Standardize on one error UX: toast notifications via a `ToastProvider`; kill `alert()` and flash-via-querystring.

### Delete dead weight

- Remove `static/vendor/lit-html/`, `static/vendor/qrcodejs/`. Only fonts + tailwind build remain vendored.

## Client generation (D9 — orval, committed)

orval's first real generation runs in Phase 4 (against the new API spec); **fleet-wide adoption — using the generated hooks everywhere and deleting the hand-copied types — is Phase 5.** Phase 0 sets up the tooling only (`orval.config.ts`, `make gen-client`, CI drift check). The `x-invalidates` OpenAPI extension maps each mutation to the `ENTITY_INVALIDATION` graph, and orval emits the matching `queryClient.invalidateQueries` calls automatically.

**Proposed orval config:**
```ts
// orval.config.ts
export default defineConfig({
  hub: {
    input: { target: './openapi.json' },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated',
      client: 'react-query',
      httpClient: 'fetch',
      override: {
        mutator: { path: 'src/api/client.ts', name: 'apiClient' },
        query: { useQuery: true, signal: true, options: {} },
        mutator: { ... },   // injects credentials: 'include' + same-origin
      },
    },
    hooks: { afterAllFilesWrite: 'prettier --write' },
  },
});
```

OpenAPI tags drive the invalidation mapping: tag a mutation `POST /nodes/{pk}/tags` with `x-invalidates: [nodes, messages, advertisements, dashboard]` (an orval extension), and the generator emits the matching `queryClient.invalidateQueries({ queryKey: ['nodes'] })` automatically — mirroring the API's `ENTITY_INVALIDATION` graph on the client side.

## Route-level code-splitting (concrete)

Lazy-load the four heaviest pages + their library dependencies:

```tsx
// Before: everything in the main chunk (776 KB today)
// After: split by route
const DashboardPage = lazy(() => import('@/pages/Dashboard'));   // chart.js
const MapPage       = lazy(() => import('@/pages/Map'));         // leaflet
const RoutesPage    = lazy(() => import('@/pages/Routes'));      // route-modal logic
const CustomPage    = lazy(() => import('@/pages/CustomPage'));  // react-markdown

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage/>} />                    // eager (landing)
        <Route path="/setup" element={<SetupWizard/>} />            // rendered when config.needs_setup (F12); gate redirects all other paths here
        <Route path="/nodes" element={<NodesPage/>} />               // eager (common)
        <Route path="/dashboard" element={<Suspense fallback={<Skeleton/>}><DashboardPage/></Suspense>} />
        <Route path="/map" element={<Suspense fallback={<Skeleton/>}><MapPage/></Suspense>} />
        <Route path="/routes" element={<Suspense fallback={<Skeleton/>}><RoutesPage/></Suspense>} />
        <Route path="/pages/:slug" element={<Suspense fallback={<Skeleton/>}><CustomPage/></Suspense>} />
        ...
      </Routes>
    </BrowserRouter>
  );
}
```

**Vite manual chunks** complement route-splitting for vendor libraries:
```ts
// vite.config.ts
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        'vendor-react': ['react','react-dom','react-router'],
        'vendor-query': ['@tanstack/react-query'],
        'vendor-charts': ['chart.js','react-chartjs-2'],   // only Dashboard imports
        'vendor-map': ['leaflet','react-leaflet'],         // only Map imports
        'vendor-markdown': ['react-markdown','remark-gfm','rehype-slug','rehype-autolink-headings'],
      },
    },
  },
}
```

**Budget targets:**
| Chunk | Target | Today |
|---|---|---|
| Initial (shell + nav + home + nodes) | < 180 KB | ~1.06 MB |
| Dashboard (chart.js) | < 250 KB lazy | (in main) |
| Map (leaflet) | < 150 KB lazy | (in main) |
| Markdown | < 80 KB lazy | (in main) |

Initial load should drop ~6×.

## Static shell + bootstrap

The HTML shell becomes a **build-time static artifact** (CDN-cacheable), carrying no user-specific data. Personalisation happens client-side after a two-call bootstrap:

```tsx
// main.tsx — renders the public shell immediately, personalises after /config + /me
async function bootstrap() {
  const [config, me] = await Promise.all([
    apiGet<PublicConfig>('/api/v1/config'),                // public: branding, features, auth_mode, custom_pages, needs_setup
    apiGet<PrincipalRead | null>('/api/v1/me').catch(() => null),  // null if not logged in
  ]);
  return { config, me };
}

bootstrap().then(({ config, me }) => {
  createRoot(document.getElementById('app')!).render(
    <AppConfigProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider initialUser={me}>
          <App />
        </AuthProvider>
      </QueryClientProvider>
    </AppConfigProvider>
  );
});
```

- `/api/v1/config` is public + cacheable (`Cache-Control: public, max-age=60`) — the network name, features, theme don't change per user. The browser caches it; every tab after the first is instant.
- `/api/v1/me` returns the resolved Principal or `null` (anonymous). One call, no per-request inlining.
- The shell renders **before** these resolve (a branded loading state), so first paint is fast and the personalisation is a progressive enhancement. This replaces today's per-request `__APP_CONFIG__` inlining with a cacheable shell.
- **First-run gate (F12):** if `config.needs_setup` is true, `<App/>` mounts the `<SetupWizard/>` at `/setup` and the web-tier gate middleware redirects every other path there until setup completes (auth.md → First-run setup wizard). No server-rendered wizard — the same static shell renders it client-side.

## SSE-driven live pages

A single `useEventStream` hook connects to the SSE endpoint and patches the TanStack Query cache. The browser's native `EventSource` authenticates via the session cookie (same-origin, sent automatically) — no custom headers needed, because the web tier proxies the SSE connection and injects the JWT upstream (see [api.md → SSE Auth](api.md#sse-auth-cookie-based-proxy-transparent)).

```tsx
function useEventStream(eventTypes: string[]) {
  const queryClient = useQueryClient();
  useEffect(() => {
    const es = new EventSource('/api/v1/events/stream');
    eventTypes.forEach((type) => {
      es.addEventListener(type, (e) => {
        const payload = JSON.parse(e.data);
        // Patch the relevant query cache optimistically
        queryClient.setQueriesData<{ items: unknown[] }>(
          { queryKey: [type.split('.')[0]] },   // e.g. 'message' → ['message']
          (old) => old ? { ...old, items: [payload, ...old.items].slice(0, old.items.length) } : old
        );
      });
    });
    es.addEventListener('settings.updated', () => queryClient.invalidateQueries({ queryKey: ['config'] }));
    es.onerror = () => es.close();   // TanStack's refetchOnReconnect + the 30s poll recover
    return () => es.close();
  }, [eventTypes.join(','), queryClient]);
}

// Messages page:
function MessagesPage() {
  useEventStream(['message.new']);
  const { data } = useMessagesQuery(filters);   // generated hook
  ...
}
```

- The SSE patch gives **instant** UI updates (no 30s poll wait).
- TanStack Query's existing `refetchInterval` (the 30s poll, aligned to Redis TTL) stays as a **safety net** — if SSE drops, the poll catches up. Polling is the fallback, SSE is the primary.
- `settings.updated` events invalidate the config query, so a branding/maintenance change propagates to all open tabs within seconds (replacing the current "reload to see the announcement" friction).

## Login page (D12)

Renders based on `PublicConfig.auth_mode`:

```tsx
function LoginPage() {
  const { auth_mode } = useAppConfig();   // 'local' | 'oidc' | 'hybrid'
  return (
    <div>
      {auth_mode !== 'oidc' && <LocalLoginForm onSuccess={redirect} />}
      {auth_mode !== 'local' && <OidcLoginButton />}
      {auth_mode === 'hybrid' && <Divider>or</Divider>}
    </div>
  );
}
```

`LocalLoginForm` POSTs to `/auth/login`; on 401 it shows the error inline (no `alert()`, per the consolidation section). On success the cookie is set and the app re-bootstraps (`/api/v1/me` re-fetched).

## Settings + Users admin pages

Two new admin pages, both using the generated client:

**Settings** (`/admin/settings`): category-grouped forms (branding, features, tuning, webhooks, radio), each a controlled form `PUT /api/v1/settings/{category}`. Saves invalidate `['config']` + `['settings']`. The features section drives runtime feature flags.

**Users** (`/admin/users`): a table of `user_profiles` with their credential source (local/OIDC badge), roles, and actions:
- Create local user (modal: username, password, roles).
- Reset password (local users only).
- Toggle roles (admin/operator/member).
- Disable/enable.
- OIDC users are listed read-only (roles editable, no password — managed by the IdP).

**Pages** (`/admin/pages`): CRUD for custom pages (D20). Table of `custom_pages` rows with slug, title, menu_order, enabled toggle. Create/edit modal with a markdown editor (textarea + live preview via the existing `<Markdown>` component). Saves invalidate `['pages']` + `['config']` (nav metadata changes).

Both pages are admin-gated (`useAppConfig().roles.includes('admin')`) and route-guarded.

## i18n (carried forward)

Keep **react-i18next** with the existing en/nl translation files. The architecture is fine; two fixes from the warts catalog:

- **Kill `window.t`** (FE10). One path: `useTranslation()` everywhere. The `window.t` global (assigned after `initI18n()` resolves) is removed — code that needs translations before boot uses the `t` function from the `useTranslation` hook inside a component, not a global.
- **Locale is a Tier-2 setting.** `branding.locale` (default `"en"`) and `branding.datetime_locale` (default `"en-US"`) come from `/api/v1/config`. The SPA initializes i18next with the configured locale; the user's browser preference is a fallback, not the source of truth (the operator sets the community's language).
- **Translation files** stay in the repo (`src/i18n/en.json`, `src/i18n/nl.json`). No server-side translation — the SPA bundles all locales and switches client-side. Adding a locale is a new JSON file + a one-line registration.
- **Server-rendered content** (the setup wizard, if server-rendered) uses the platform default locale. The SPA handles everything else.

## Carried-forward features (unchanged)

- **QR codes** (node detail, channel detail): `react-qr-code` — unchanged. QR encodes the node's public key or the channel's connection string. No server involvement.
- **Announcements/maintenance banner**: `branding.announcement` and `branding.system_announcement` (Tier-2 settings) render as dismissible banners on every page. `branding.maintenance_mode = true` returns 503 for non-admin API requests (see [api.md → Error response format](api.md#error-response-format)); the SPA shows a full-page maintenance view with the announcement text.
- **Theme toggle** (dark/light): `branding.default_theme` sets the default; user preference in `localStorage` overrides. Unchanged from today.
