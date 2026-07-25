# Multi-Tenancy

> **Related decisions:** D21 (shared platform, tenant-scoped observers), D3 (row-level `instance_id` + RLS), D4 (NATS JetStream for ingest + fan-out), D12 (multi-source auth — per-tenant OIDC), D11 (three-tier config — per-tenant settings)
>
> **Phase:** 7 (extension after the single-tenant Phases 0–6 are stable). The schema does not change.
>
> **Note:** Code examples are illustrative pseudocode showing design patterns (shapes, flows, contracts).
> The implementation uses the TypeScript stack (D22): Fastify middleware, Drizzle ORM, @nats-io/jetstream, Node crypto.

---

## 1. Architecture overview

```mermaid
flowchart TB
    subgraph Edge
        O1[Observer A] & O2[Observer B] & O3[Observer C]
    end
    O1 & O2 & O3 -->|MQTT WSS| MQTT[(Shared MQTT Broker<br/>accepts ALL observers)]

    subgraph "Shared ingest plane"
        ING[MqttIngester<br/>decodes ALL traffic<br/>routes per tenant]
    end
    MQTT --> ING
    ING -->|observer → tenant lookup| ROUTE{ObserverAllowlistCache<br/>dict[prefix → set[tenant_id]]}

    ROUTE -->|"O1 → Tenant A"| NS_A[(NATS: meshcore.ingest.&lt;A&gt;.*)]
    ROUTE -->|"O2 → Tenant A+B"| NS_A & NS_B
    ROUTE -->|"O3 → Tenant B"| NS_B[(NATS: meshcore.ingest.&lt;B&gt;.*)]

    subgraph "Tenant A"
        W_A[IngestWorker A] --> PG[(Shared Postgres<br/>RLS: instance_id)]
        DW_A[DerivedStateWorker A] --> PG
        WW_A[WebhookWorker A]
    end
    subgraph "Tenant B"
        W_B[IngestWorker B] --> PG
        DW_B[DerivedStateWorker B] --> PG
        WW_B[WebhookWorker B]
    end

    NS_A --> W_A
    NS_B --> W_B
    NS_A -.->|events.new.&lt;A&gt;.*| WW_A
    NS_B -.->|events.new.&lt;B&gt;.*| WW_B

    subgraph "Shared read plane"
        API[API<br/>resolves tenant from<br/>JWT claim or hostname]
        WEB[Web tier<br/>resolves tenant from<br/>hostname]
    end
    PG --> API
    WEB -->|per-tenant JWT| API

    CA[community-a.example.com] --> WEB
    CB[community-b.example.com] --> WEB

    REDIS[(Shared Redis<br/>keys scoped by instance)] -.-> API

    classDef shared fill:#e3f2fd,stroke:#1565c0;
    classDef tenant fill:#e8f5e9,stroke:#388e3c;
    class MQTT,ING,ROUTE,API,WEB,PG,REDIS shared;
    class W_A,DW_A,WW_A,W_B,DW_B,WW_B tenant;
```

**One deployment, N tenants.** Shared: MQTT broker, MqttIngester, Postgres (+TimescaleDB), NATS, Redis, API process, Web tier process. Per-tenant: IngestWorker pool, DerivedStateWorker, WebhookWorker, all data (via RLS).

---

## 2. What's already free

The single-tenant design (Phases 0–6) built multi-tenant foundations by default. These require **zero changes**:

| Capability | Why it's free |
|---|---|
| Per-tenant data isolation | `instance_id` + RLS on every table (D3) |
| Per-tenant settings/branding | `settings` table is per-instance (D11) |
| Per-tenant custom pages | `custom_pages` table is per-instance (D20) |
| Per-tenant channels/routes/tags/profiles | All tables carry `instance_id` |
| Per-tenant NATS subjects | Already namespaced: `meshcore.ingest.<inst>.*`, `events.new.<inst>.*` |
| Per-tenant cache keys | Already scoped by instance |
| Per-tenant JWT | `instance_id` claim already in the token (D6) |
| Per-tenant local users | `local_users.instance_id` (D12) |
| Per-tenant webhooks | Tier-2 settings, per-instance |

The single-tenant assumption lives in exactly **three places** that Phase 7 modifies:

1. `MqttIngester.__init__(instance_id=...)` — becomes a routing table lookup.
2. `AuthMiddleware.instance_id` (from env) — becomes hostname/JWT resolution.
3. OIDC config (Tier-1 env vars) — gains a per-instance DB path.

---

## 3. Observer → tenant mapping

Observer assignment is a **tenant-admin function** (D21). Each tenant manages their own allowlist via the Admin UI. The MQTT backend accepts all observers; the tenant chooses which ones they want.

### The table

```sql
CREATE TABLE tenant_observers (
  instance_id            uuid NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
  observer_pubkey_prefix text NOT NULL,          -- prefix match (like today's OBSERVER_ALLOW_LIST)
  label                  text,                    -- optional human note ("IPT downtown repeater")
  created_at             timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (instance_id, observer_pubkey_prefix)
);
```

### Semantics

- **Empty allowlist = all observers.** A tenant with no rows in `tenant_observers` receives traffic from every observer. This is the default for a fresh tenant — it mirrors today's single-tenant behaviour (no filter = accept all).
- **Non-empty allowlist = only those observers.** Prefix-match, identical to today's `OBSERVER_ALLOW_LIST` semantics. A prefix of `01ab21` matches observer `01ab2186c4d5...`.
- **Shared observers.** An observer can appear in multiple tenants' allowlists (or in one tenant's allowlist while another tenant has an empty list). The MqttIngester fans out the envelope to all matching tenants.
- **No deny list.** If a tenant wants "all except X," they enumerate the observers they want. This keeps the model simple; a deny list is a future refinement if demanded.

### Management API

```typescript
@router.get("/observers", response_model=list[ObserverAllowlistEntry])
async def list_observers(principal: RequireAdmin) -> list[ObserverAllowlistEntry]:
    """Tenant admin: list the observer allowlist. Empty = all observers."""

@router.post("/observers", response_model=ObserverAllowlistEntry, dependencies=[Depends(require_role("admin"))])
async def add_observer(body: ObserverAdd, principal: RequireAdmin) -> ObserverAllowlistEntry:
    """Add an observer prefix to the allowlist. Publishes observer.allowlist.updated on NATS."""

@router.delete("/observers/{prefix}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def remove_observer(prefix: str, principal: RequireAdmin) -> None:
    """Remove an observer prefix. Publishes observer.allowlist.updated on NATS."""
```

Mutations publish `observer.allowlist.updated.<instance_id>` on NATS core, triggering the MqttIngester's `ObserverAllowlistCache` to reload (same pattern as `ChannelKeyCache`).

### Admin UI

A new section in the Settings page (or a dedicated `/admin/observers` page): a table of observer prefixes with labels, an "add observer" input, and a note explaining "empty list = all observers." The tenant admin can also see a live list of known observers (from `nodes WHERE is_observer = true`) to pick from, but the allowlist is prefix-based (so they can add an observer before it's ever seen).

---

## 4. MqttIngester multi-tenant routing

The single MqttIngester process decodes **all** MQTT traffic and routes each envelope to the tenant(s) that want it.

### ObserverAllowlistCache

```typescript
class ObserverAllowlistCache:
    """Read-only snapshot: observer_prefix → set[instance_id].
    Loaded from tenant_observers at startup; reloaded on NATS notification.
    Immutable-snapshot swap (same pattern as ChannelKeyCache)."""

    def route(self, observer_pubkey: str) -> list[UUID]:
        """Return the tenant IDs that want this observer's traffic.
        Empty allowlist tenants match ALL observers."""
        matching = set()
        for prefix, tenant_ids in self._prefix_map.items():
            if observer_pubkey.startswith(prefix):
                matching |= tenant_ids
        matching |= self._allow_all_tenants   # tenants with empty allowlists
        return list(matching)
```

- **Load:** `SELECT instance_id, observer_pubkey_prefix FROM tenant_observers` at startup. Build two structures: `_prefix_map: dict[str, set[UUID]]` and `_allow_all_tenants: set[UUID]` (tenants with zero rows).
- **Reload:** subscribe to `observer.allowlist.updated.*` (core NATS); on notification, reload the snapshot atomically. The notification carries the `instance_id` so the cache can do a targeted reload (`WHERE instance_id = ?`) instead of a full table scan.
- **Thread safety:** single-writer (the reload task), readers go through an immutable snapshot reference. Same as `ChannelKeyCache` (§ingest.md 11).

### Routing in on_message

```typescript
async def on_message(self, topic: str, payload: bytes) -> None:
    # 1. parse topic → observer pubkey (unchanged)
    # 2. envelope = self._build_envelope(topic, payload)   # decode + normalize + classify
    # 3. tenant_ids = self.observer_cache.route(envelope.observer.public_key)
    # 4. for tenant_id in tenant_ids:
    #        await js.publish(
    #            subject=f"meshcore.ingest.{tenant_id}.{envelope.observer.feed}",
    #            payload=JSON.stringify(envelope),
    #            headers: { "Nats-Msg-Id": `${tenant_id}:${envelope.wire_hash}` })
    # Envelope is tenant-agnostic; tenant routing is purely at the NATS subject level.
```

**Key detail:** the `Nats-Msg-Id` is prefixed with `tenant_id` so that the same physical packet (same `wire_hash`) delivered to two tenants gets two distinct dedup keys. Without this, JetStream's server-side dedup would suppress the second tenant's copy.

**Cost:** one hash-map lookup per packet (`route()`), plus N publishes for N matching tenants. For the typical case (1–2 tenants per observer), this is negligible. The envelope is serialized once and published N times (same bytes, different subjects).

---

## 5. ChannelKeyCache multi-tenant

The MqttIngester needs channel keys from **all tenants** to decrypt channel messages (the `channel_idx` is in the decrypted payload, needed for classification and the SSE visibility filter).

```typescript
class ChannelKeyCache:
    """Multi-tenant: dict[instance_id, frozenset[ChannelKey]].
    Loads enabled channels for ALL instances at startup.
    Reloads one tenant's keys on channel.keys.<inst>.updated."""

    def all_keys(self) -> Iterator[ChannelKey]:
        """Yield keys from all tenants (for decryption attempts)."""
        for keys in self._snapshots.values():
            yield from keys
```

- **Load:** `SELECT instance_id, key_hex, key_hash FROM channels WHERE enabled` at startup (all instances).
- **Reload:** the existing `channel.keys.<inst>.updated` NATS notification triggers a reload of that tenant's keys only.
- **Decryption:** the ingester tries all tenants' keys (it already tries all keys today — the loop is unchanged, just over a larger set). The decrypted `channel_idx` is tagged with the `instance_id` of the key that matched, so the envelope's `meta.channel_idx` is tenant-correct.

For a small number of tenants (2–10) with a handful of channels each, the key set is tiny. For a large deployment, the decryption loop could be optimized with a key-hash index, but that's premature.

---

## 6. Per-tenant OIDC

OIDC config moves from Tier-1 env vars to a per-instance DB table. The Tier-1 env vars become **platform-level defaults** (used when a tenant hasn't configured their own).

```sql
CREATE TABLE tenant_oidc_configs (
  instance_id    uuid PRIMARY KEY REFERENCES instances(id) ON DELETE CASCADE,
  discovery_url  text NOT NULL,
  client_id      text NOT NULL,
  client_secret      text NOT NULL,             -- encrypted at rest (Node crypto.createCipheriv, key from Tier-1 env)
  auth_mode      text NOT NULL DEFAULT 'hybrid',   -- 'local' | 'oidc' | 'hybrid' per tenant
  enabled        boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
```

### Resolution

The web tier resolves OIDC config per request:

```typescript
async def resolve_oidc_config(instance_id: UUID, settings: SettingsCache) -> OidcConfig | None:
    # 1. Per-tenant DB config (authoritative if present)
    if (cfg := await get_tenant_oidc(instance_id)) and cfg.enabled:
        return cfg
    # 2. Platform-level env-var defaults (fallback)
    if settings.oidc_client_id:   # from Tier-1 env
        return OidcConfig.from_env()
    # 3. No OIDC — local-only
    return None
```

- Each tenant can point at their own IdP, share one with different client IDs, or use local-only auth.
- `AUTH_MODE` becomes per-tenant (stored in `tenant_oidc_configs.auth_mode` or the `settings` table). The Tier-1 `AUTH_MODE` env var is the platform default.
- The `client_secret` is encrypted at rest using AES-256-GCM via Node's `crypto` module, with a key from a Tier-1 env var (`FIELD_ENCRYPTION_KEY`). It's never returned by the API (write-only).

### Management

Tenant admins configure OIDC via the Settings UI (a new "Authentication" section) or the API:

```typescript
@router.put("/settings/oidc", dependencies=[Depends(require_role("admin"))])
async def update_oidc_config(body: OidcConfigUpdate, principal: RequireAdmin) -> OidcConfigRead:
    """Tenant admin: configure their own IdP. client_secret is write-only."""
```

---

## 7. Instance resolution (hostname-based, self-service)

Each community gets their own subdomain of the platform domain, chosen at registration. No per-tenant DNS configuration is required from the platform operator.

### Wildcard DNS + subdomain model

The platform runs a **wildcard DNS record**: `*.meshhub.example.com → <platform IP>`. Tenants pick a subdomain at registration (`community-a` → `community-a.meshhub.example.com`). The reverse proxy (nginx/caddy/traefik) terminates TLS with a **wildcard certificate** (`*.meshhub.example.com`) and routes all hostnames to the same web tier process. No per-tenant proxy config, no per-tenant certificate.

**Custom domains** (optional, tenant-admin self-service): a tenant admin adds a hostname in the Admin UI (Settings → Community → Custom domain). They configure a CNAME at their own DNS provider (`mesh.community-a.org → community-a.meshhub.example.com`). The `HostnameCache` picks up the new hostname on save (NATS notification → reload). For TLS on custom domains, the reverse proxy uses ACME (Let's Encrypt) per hostname — caddy does this automatically; nginx needs `certbot --webroot`. See [Custom domains](#custom-domains) below for the full design.

### Hostname mapping

```sql
CREATE TABLE instance_hostnames (
  hostname     text PRIMARY KEY,            -- 'community-a.meshhub.example.com'
  instance_id  uuid NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
  is_primary   boolean NOT NULL DEFAULT false,
  is_custom    boolean NOT NULL DEFAULT false,  -- true for tenant-added custom domains
  added_at     timestamptz NOT NULL DEFAULT now()
);
```

A tenant can have multiple hostnames (their subdomain + custom domains). One is primary (used in generated URLs). The subdomain is always present and cannot be removed while the instance exists.

### Custom domains

Tenants who own a domain (e.g. `mesh.community-a.org`) can use it instead of (or alongside) their platform subdomain. The flow is fully self-service — no platform-operator action.

**The flow:**

```
Tenant admin                              Platform                        Tenant's DNS
     |                                       |                                |
     |-- POST /api/v1/domains -------------->|                                |
     |   { hostname: "mesh.community-a.org" }|                                |
     |                                       |-- INSERT instance_hostnames    |
     |                                       |   (is_custom=true)             |
     |                                       |-- publish hostname.updated     |
     |                                       |   on NATS                      |
     |                                       |-- HostnameCache reloads        |
     |<-- 201 { hostname, cname_target } ----|                                |
     |                                       |                                |
     |-- configure CNAME ----------------------------------------------- -->  |
     |   mesh.community-a.org                |                                |
     |     CNAME community-a.meshhub.example.com                             |
     |                                       |                                |
     |                                       |<--- TLS: ACME challenge ------|
     |                                       |    (caddy/certbot auto)       |
     |                                       |--- certificate issued -------->|
     |                                       |                                |
     |   mesh.community-a.org now serves the tenant's site                   |
```

**API:**

```typescript
// Tenant admin: add a custom domain
fastify.post("/api/v1/domains", { preHandler: requireAdmin }, async (request, reply) => {
    const { hostname } = request.body;   // e.g. "mesh.community-a.org"

    // Validate: well-formed hostname, not a subdomain of PLATFORM_DOMAIN (those are registration-only)
    if (hostname.endsWith(`.${PLATFORM_DOMAIN}`))
        return reply.status(400).send({ detail: "use the registration flow for platform subdomains" });
    if (await hostnameExists(hostname))
        return reply.status(409).send({ detail: "hostname already in use" });

    await db.insert(instanceHostnames).values({
        hostname, instance_id: request.instanceId, is_custom: true,
    });
    await nats.publish("hostname.updated", JSON.stringify({ hostname, instance_id: request.instanceId }));

    return reply.status(201).send({
        hostname,
        cname_target: `${primarySubdomain}.${PLATFORM_DOMAIN}`,   // "community-a.meshhub.example.com"
        status: "pending_dns",   // flips to "active" once the reverse proxy serves TLS for it
    });
});

// Tenant admin: list domains (subdomain + custom)
fastify.get("/api/v1/domains", { preHandler: requireAdmin }, async (request, reply) => {
    const rows = await db.select().from(instanceHostnames)
        .where(eq(instanceHostnames.instance_id, request.instanceId));
    return rows;   // [{ hostname, is_primary, is_custom, added_at }]
});

// Tenant admin: remove a custom domain (cannot remove the primary subdomain)
fastify.delete("/api/v1/domains/:hostname", { preHandler: requireAdmin }, async (request, reply) => {
    const row = await getHostname(request.params.hostname);
    if (!row || row.instance_id !== request.instanceId) return reply.status(404).send();
    if (!row.is_custom) return reply.status(400).send({ detail: "cannot remove the platform subdomain" });
    await db.delete(instanceHostnames).where(eq(instanceHostnames.hostname, request.params.hostname));
    await nats.publish("hostname.updated", JSON.stringify({ hostname: request.params.hostname }));
    return reply.status(204).send();
});

// Tenant admin: promote a custom domain to primary (used in generated URLs)
fastify.put("/api/v1/domains/:hostname/primary", { preHandler: requireAdmin }, async (request, reply) => {
    // Unset current primary, set new primary — one transaction
    await db.transaction(async (tx) => {
        await tx.update(instanceHostnames).set({ is_primary: false })
            .where(eq(instanceHostnames.instance_id, request.instanceId));
        await tx.update(instanceHostnames).set({ is_primary: true })
            .where(eq(instanceHostnames.hostname, request.params.hostname));
    });
    await nats.publish("hostname.updated", JSON.stringify({ hostname: request.params.hostname }));
    return { ok: true };
});
```

**DNS verification — not required.** The hostname is a routing key, not a credential. Adding a hostname you don't control is harmless: without a DNS record pointing to the platform, the domain simply doesn't resolve. The tenant is motivated to configure DNS correctly because they want their domain to work. The Admin UI shows the CNAME target and a "pending DNS" hint until the first request arrives on that hostname (tracked via a `last_seen_at` column or the reverse proxy's access log — lightweight, no active probing).

**TLS provisioning:** the reverse proxy handles this automatically:

| Reverse proxy | Mechanism | Config |
|---|---|---|
| **Caddy** | Built-in ACME (Let's Encrypt) — issues + renews per-hostname certificates automatically | `caddyfile: *.meshhub.example.com + on-demand TLS for custom domains` |
| **nginx + certbot** | `certbot --webroot -d mesh.community-a.org` — cron renewal | `tls_on_demand` via `lua-resty-auto-ssl` or a `certbot` hook |
| **Traefik** | Built-in ACME with `tlsChallenge` | `certificatesResolvers.letsencrypt.acme.tlsChallenge = true` |

The platform's wildcard certificate covers all subdomains (`*.meshhub.example.com`). Custom domains get individual certificates via ACME. No operator action — the reverse proxy provisions them on first TLS handshake.

**Constraints:**
- A hostname can only belong to one tenant (PK on `hostname`).
- The platform subdomain (created at registration) cannot be removed while the instance exists.
- Custom domains are additive — the subdomain always works as a fallback.
- Maximum hostnames per tenant: configurable platform setting (default 5) to prevent abuse.

### Resolution middleware

```typescript
async function instanceResolution(request: FastifyRequest, reply: FastifyReply) {
    // 1. JWT-authenticated requests: instance_id from the token claim (already there)
    // 2. Unauthenticated requests: resolve from hostname
    const hostname = request.headers.host?.split(":")[0];
    const instanceId = await hostnameCache.resolve(hostname);
    if (!instanceId) {
        return reply.status(404).send({ detail: "unknown host" });
    }
    request.instanceId = instanceId;
}
```

- The `HostnameCache` is a read-only snapshot (loaded at startup, refreshed on NATS notification when hostnames change). Same immutable-snapshot pattern as `ChannelKeyCache`.
- **Fallback:** a Tier-1 env var `DEFAULT_INSTANCE_ID` for single-tenant deployments (Phases 0–6). When set, hostname resolution is skipped and all requests map to the default instance. This is the backwards-compatible path.

### What changes in the web tier

- `GET /api/v1/config` returns the **tenant's** settings (branding, features, pages, auth_mode).
- The login page renders the **tenant's** auth options (local form, OIDC button, or both per the tenant's `auth_mode`).
- JWT issuance uses the **tenant's** OIDC config (for the OIDC redirect) and the platform's `OIDC_SESSION_SECRET` (for signing — shared across tenants, since the API verifies with the same key).
- The setup wizard (D12) runs per-tenant: a fresh tenant with no admin sees the wizard on their hostname.
- The platform's root domain (`meshhub.example.com`) serves a **landing page** with a "Create your community" link → the registration flow (§8).

---

## 8. Tenant lifecycle

### Creation (self-service registration — no platform-operator action)

Tenants self-provision via a public registration flow. **No CLI, no superadmin, no operator intervention.**

**Registration API:**

```typescript
// Public — no auth required
fastify.post("/api/v1/register", { schema: { body: RegisterBody } }, async (request, reply) => {
    const { community_name, subdomain, admin_username, admin_password } = request.body;

    // Validate subdomain: alphanumeric + hyphens, 3-63 chars, unique
    if (!/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(subdomain))
        return reply.status(400).send({ detail: "invalid subdomain" });

    const hostname = `${subdomain}.${PLATFORM_DOMAIN}`;
    if (await hostnameExists(hostname))
        return reply.status(409).send({ detail: "subdomain taken" });

    // One transaction: instance + hostname + settings seed + admin bootstrap
    await db.transaction(async (tx) => {
        const [instance] = await tx.insert(instances).values({ name: community_name }).returning();
        await tx.insert(instanceHostnames).values({
            hostname, instance_id: instance.id, is_primary: true,
        });
        await seedDefaultSettings(tx, instance.id);          // same seed as single-tenant
        await bootstrapAdmin(tx, instance.id, admin_username, admin_password);  // 3-table insert (D12)
    });

    // After commit: notify all services
    await nats.publish("instance.created", JSON.stringify({ instance_id: instance.id, hostname }));

    // Auto-login: mint session cookie, redirect to the tenant's dashboard
    return startSession(reply, { sub: `local:${admin_username}`, instance_id: instance.id, roles: ["admin"] })
        .redirect(302, `https://${hostname}/`);
});
```

**Registration UI:** a public page at the platform's root domain (`PLATFORM_DOMAIN/register`). Simple form: community name, subdomain (with live availability check via `GET /api/v1/register/check?subdomain=...`), admin username + password + confirm. On success, the browser is redirected to `https://<subdomain>.<PLATFORM_DOMAIN>/`, already logged in as the new admin.

**Abuse prevention (Tier-2 platform settings):**

| Control | Default | Purpose |
|---|---|---|
| `registration.enabled` | `true` | Kill switch — disable registration platform-wide |
| `registration.rate_limit_per_ip` | `3/hour` | Reverse-proxy `limit_req` on `POST /api/v1/register` |
| `registration.require_captcha` | `false` | Optional hCaptcha/Turnstile challenge on the form |
| `registration.subdomain_reserved` | `["www","api","admin","mail"]` | Reserved subdomains that can't be registered |

These are **platform-level** settings (stored in the `settings` table with `instance_id = NULL` or a dedicated `platform_settings` scope — see note below). They are editable by the platform's first tenant's admin (the "platform admin" is just the admin of the first-created instance, not a separate role).

> **Platform settings note:** the `settings` table is instance-scoped. Platform-level settings (registration control, `PLATFORM_DOMAIN`) are stored with a well-known `instance_id` (the first instance, created at initial deployment via the existing `NETWORK_NAME` seed). The registration endpoint reads from this instance's settings. This avoids a new table while keeping the "no superadmin role" principle — the platform admin is a regular tenant admin with access to the platform settings category.

**CLI fallback:** `meshcore-hub admin create-instance` still exists for bulk provisioning, scripting, air-gapped deployments, or when the registration UI is disabled. Same transaction sequence (instance + hostname + settings seed + admin bootstrap). The CLI is a convenience, not a gate.

### Tenant admin self-service

Once created, the tenant admin manages (all already per-instance):

| What | Where |
|---|---|
| Observer allowlist | `/admin/observers` (new page) |
| Branding, announcements, features | `/admin/settings` (existing) |
| Custom pages | `/admin/pages` (D20) |
| OIDC config | `/admin/settings` → Authentication section |
| Channels, routes, tags | Existing admin pages |
| Users (local + OIDC role overrides) | `/admin/users` (existing) |
| Webhooks | `/admin/settings` → Webhooks section |
| Custom domains | `/admin/settings` → Community → Add domain |

### Deletion

Two-step: **soft-delete** (reversible, self-service) then **purge** (permanent, CLI-only).

**Soft-delete** — tenant admin self-service via Settings → Community → Delete community, or CLI `meshcore-hub admin delete-instance --name "Community A"`:

1. Sets `instances.deleted_at = now()` (the row stays; FKs are unaffected).
2. The hostname resolution middleware excludes soft-deleted instances: `HostnameCache.resolve()` returns null → the tenant's hostname serves a 404. Existing JWTs (5-minute lifetime) expire naturally; no new sessions can be minted.
3. Shared workers stop processing the tenant's data: the DerivedStateWorker skips deleted instances on its next tick; the IngestWorker's envelopes for the deleted tenant are acked-and-dropped (the `ObserverAllowlistCache` no longer routes to the deleted instance).
4. The tenant's data stays in the DB behind RLS. It's inaccessible via the application (hostname 404s, tokens expire). Reversible: `admin undelete-instance --name "Community A"` clears `deleted_at`, or the tenant admin contacts the platform admin who re-enables via the CLI.

**Purge** — `meshcore-hub admin purge-instance --name "Community A"` (CLI-only, after a grace period, e.g. 30 days):

1. Deletes all tenant data table-by-table in dependency order (children before parents, hypertables last). The core tables do **not** use `ON DELETE CASCADE` on `instance_id` — that would force TimescaleDB to scan every chunk on cascade, and an accidental `DELETE FROM instances` would be catastrophic. Instead, the purge is an explicit multi-table operation:

```sql
-- OLTP tables (dependency order: children first)
DELETE FROM route_recent_matches WHERE route_id IN (SELECT id FROM routes WHERE instance_id = :id);
DELETE FROM route_result_history  WHERE route_id IN (SELECT id FROM routes WHERE instance_id = :id);
DELETE FROM route_results         WHERE route_id IN (SELECT id FROM routes WHERE instance_id = :id);
DELETE FROM user_profile_roles    WHERE profile_id IN (SELECT id FROM user_profiles WHERE instance_id = :id);
DELETE FROM user_profile_nodes    WHERE user_profile_id IN (SELECT id FROM user_profiles WHERE instance_id = :id);
DELETE FROM local_users           WHERE instance_id = :id;
DELETE FROM node_tags             WHERE node_id IN (SELECT id FROM nodes WHERE instance_id = :id);
DELETE FROM route_observers       WHERE route_id IN (SELECT id FROM routes WHERE instance_id = :id);
DELETE FROM route_nodes           WHERE route_id IN (SELECT id FROM routes WHERE instance_id = :id);
DELETE FROM custom_pages          WHERE instance_id = :id;
DELETE FROM settings              WHERE instance_id = :id;
DELETE FROM messages              WHERE instance_id = :id;
DELETE FROM advertisements        WHERE instance_id = :id;
DELETE FROM trace_paths           WHERE instance_id = :id;
DELETE FROM user_profiles         WHERE instance_id = :id;
DELETE FROM routes                WHERE instance_id = :id;
DELETE FROM channels              WHERE instance_id = :id;
DELETE FROM nodes                 WHERE instance_id = :id;
-- Hypertables (filtered by instance_id; no chunk exclusion on this column)
DELETE FROM event_observers       WHERE instance_id = :id;
DELETE FROM raw_receptions        WHERE instance_id = :id;
DELETE FROM telemetry             WHERE instance_id = :id;
DELETE FROM event_logs            WHERE instance_id = :id;
-- Phase 7 tables (these DO have ON DELETE CASCADE from instances)
DELETE FROM tenant_observers      WHERE instance_id = :id;
DELETE FROM tenant_oidc_configs   WHERE instance_id = :id;
DELETE FROM instance_hostnames    WHERE instance_id = :id;
-- Finally, the instance row itself
DELETE FROM instances             WHERE id = :id;
```

2. The CLI confirms interactively and runs each DELETE in a transaction, reporting row counts. The hypertable deletes are the slowest (full chunk scan filtered by `instance_id`); for 30 days of community-mesh data this is a multi-minute but not catastrophic operation.

**Why not `ON DELETE CASCADE` on core tables:** (a) TimescaleDB would scan every hypertable chunk on cascade — O(all data) with no chunk exclusion; (b) an accidental `DELETE FROM instances` (wrong WHERE, typo) would irrevocably destroy an entire tenant; (c) the explicit purge gives the operator row-count feedback and a confirmation gate. The Phase 7-specific tables (`tenant_observers`, `tenant_oidc_configs`, `instance_hostnames`) do use CASCADE because they're small and directly owned by the instance row.

---

## 9. Shared worker pool (dynamic tenant discovery)

Workers are **tenant-agnostic**. They discover active tenants dynamically and process work for all of them. No per-tenant processes, no Compose profiles, no operator action when a new tenant registers. A tenant registers → the system handles them within seconds.

| Process | Multi-tenant behavior |
|---|---|
| **MqttIngester** | Already shared — decodes all MQTT traffic, routes per tenant via `ObserverAllowlistCache` (§4). New tenants picked up on `instance.created` NATS notification (cache reload). |
| **IngestWorker** (pool) | Subscribes to `meshcore.ingest.>` (**wildcard — all tenants**). Each envelope carries `instance_id`; the worker sets `SET LOCAL app.instance_id` per batch. Consumer group `workers` distributes across replicas. New tenants need zero config — the wildcard subscription already covers their subject. |
| **DerivedStateWorker** | Queries `SELECT id FROM instances WHERE deleted_at IS NULL` at startup + on `instance.created`/`instance.deleted` NATS notifications. For each active instance, runs the job manifest with `SET LOCAL app.instance_id`. Per-instance advisory lock keys (`lock_key = base_key + instance_index`) prevent one tenant's long-running job from blocking another's. Round-robin across instances. |
| **WebhookWorker** | Subscribes to `events.new.>` (**wildcard — all tenants**). Each event carries `instance_id`; the worker loads that tenant's webhook settings from `SettingsCache`. New tenants need zero config. |

### New-tenant pickup (zero operator intervention)

When `instance.created` fires on NATS:

| Service | Reaction | Latency |
|---|---|---|
| MqttIngester `ObserverAllowlistCache` | Reload (already designed — §4) | <1s |
| MqttIngester `ChannelKeyCache` | Reload (already designed — §5) | <1s |
| `HostnameCache` | Reload (§7) | <1s |
| IngestWorker | **None** — wildcard subscription already covers the new subject | 0 |
| DerivedStateWorker | Picks up the new instance on its next tick (or immediately on NATS notification) | ≤1s (notification) or ≤300s (next tick) |
| WebhookWorker | **None** — wildcard subscription; settings loaded per-event | 0 |
| API `SettingsCache` | Loads the new instance's settings on first request | lazy |

The tenant registers, and the system is fully operational for them within seconds. No containers started, no Compose profiles applied, no CLI commands run.

### Isolation

- **NATS level:** separate subjects per tenant (`meshcore.ingest.<A>.*` vs `meshcore.ingest.<B>.*`). One tenant's burst doesn't consume another's messages.
- **DB level:** the batch model (100 envelopes per transaction) limits blast radius. RLS (`SET LOCAL app.instance_id`) prevents cross-tenant writes even if a bug misroutes.
- **DerivedStateWorker:** per-instance advisory lock keys mean one tenant's long route-evaluation doesn't block another's. Jobs run sequentially per instance but instances are processed round-robin.
- **Resource-constrained deployments:** for 2–5 tenants, one IngestWorker replica + one DerivedStateWorker replica (with HA pair) is sufficient. The wildcard subscription model scales to more tenants by adding replicas to the consumer group.

### Scaling

- **IngestWorker:** add replicas to the `workers` consumer group. JetStream distributes messages across them. Each replica handles all tenants (wildcard subscription).
- **DerivedStateWorker:** two replicas with advisory locks (D16) cover HA. For very large deployments (50+ tenants), shard by instance: each replica handles a subset (`WHERE id % N = replica_index`). This is a future optimization, not a Phase 7 requirement.
- **WebhookWorker:** one process is sufficient (webhook dispatch is I/O-bound, not CPU-bound). Scale by adding replicas with the same NATS subscription (each event is delivered to one subscriber in a queue group).

### Why not per-tenant Compose profiles

The original design gave each tenant their own worker processes via Compose profiles (`--profile tenant-a`). This requires the platform operator to create/modify/start a Compose profile for every new tenant — the exact "superadmin action" that self-provisioning eliminates. The shared worker pool achieves the same isolation (NATS subjects + RLS) with zero per-tenant infrastructure. The tradeoff: a single IngestWorker pool processes all tenants' traffic, so a pathological tenant (millions of packets/sec) could starve others. Mitigation: per-tenant rate limiting at the MqttIngester level (a future refinement, §13) and the batch model's natural backpressure (JetStream delivery rate is bounded by the consumer's `fetch` loop).

---

## 10. Shared observers (fan-out)

When an observer belongs to multiple tenants:

```
Observer IPT-01 sends a packet
  → MqttIngester decodes it (once)
  → ObserverAllowlistCache.route("01ab21...") → [Tenant A, Tenant B]
  → Publish envelope to meshcore.ingest.<A>.packets
  → Publish envelope to meshcore.ingest.<B>.packets
  → Tenant A's IngestWorker processes it (dedup, persist, fan-out)
  → Tenant B's IngestWorker processes it (dedup, persist, fan-out)
```

- The envelope is **immutable and tenant-agnostic** — it carries observer info, not tenant info.
- Each tenant's `event_observers` junction records the observer independently.
- Each tenant's dedup (`event_hash`) is independent — the same physical packet creates one dedup'd event per tenant.
- The `Nats-Msg-Id` is `{tenant_id}:{wire_hash}` so JetStream dedup doesn't suppress the second tenant's copy.
- Cost: one extra NATS publish per additional tenant. Negligible for 2–3 tenants sharing an observer.

**Empty-allowlist tenants** (want all observers) receive every envelope. This is the `_allow_all_tenants` set in the routing cache.

---

## 11. Migration from single-tenant

A single-tenant deployment (Phases 0–6) becomes multi-tenant with:

1. **Set `DEFAULT_INSTANCE_ID`** (Tier-1 env) to the existing instance's UUID. All existing traffic maps to this instance. Hostname resolution is skipped.
2. **Set `PLATFORM_DOMAIN`** (Tier-1 env) and configure wildcard DNS (`*.PLATFORM_DOMAIN → platform IP`) + wildcard TLS certificate.
3. **Enable registration** (default: enabled). New tenants self-provision via the registration page.
4. **Existing tenant's observer allowlist** stays empty (all observers) unless the admin narrows it.

No schema migration. No data migration. No per-tenant worker setup. The existing instance is the first tenant; new tenants are additive and self-provisioned.

---

## 12. What needs building

| Component | Work | Size |
|---|---|---|
| **Registration API + UI** | `POST /api/v1/register`, subdomain availability check, registration page at platform root, abuse-prevention settings | Medium |
| `tenant_observers` table + CRUD API | New table, 3 endpoints, NATS notification | Small |
| `ObserverAllowlistCache` in MqttIngester | Read-only cache + NATS reload (ChannelKeyCache pattern) | Small |
| MqttIngester multi-tenant produce | `route()` lookup + N publishes + tenant-prefixed `Nats-Msg-Id` | Small |
| `ChannelKeyCache` multi-tenant | Load all instances' keys; tag decrypted `channel_idx` with `instance_id` | Small |
| `tenant_oidc_configs` table + API | New table, OIDC config CRUD, encrypted secret, resolution logic | Medium |
| `instance_hostnames` table + `HostnameCache` | New table, resolution middleware, NATS reload, custom-domain support | Medium |
| **Custom domains API** | `POST/GET/DELETE /api/v1/domains`, `PUT /api/v1/domains/:hostname/primary`; ACME TLS provisioning (caddy/certbot); Admin UI (Settings → Community) | Medium |
| Instance resolution middleware | Hostname → `instance_id` for unauthenticated requests; `DEFAULT_INSTANCE_ID` fallback | Medium |
| Per-tenant auth flow | Web tier resolves OIDC config per tenant; login page per tenant's `auth_mode` | Medium |
| **Shared worker pool** | Wildcard NATS subscriptions (`meshcore.ingest.>`, `events.new.>`); DerivedStateWorker multi-instance loop with per-instance advisory keys; `instance.created`/`instance.deleted` NATS handlers | Medium |
| Tenant management CLI (fallback) | `create-instance`, `delete-instance` (soft), `undelete-instance`, `purge-instance` (hard, multi-table), `list-instances` | Medium |
| Observer admin UI | `/admin/observers` page (allowlist CRUD + known-observer picker) | Small |
| OIDC admin UI | Settings → Authentication section (OIDC config form) | Small |
| Custom-domain admin UI | Settings → Community → Add/remove custom domain | Small |
| Landing page + registration UI | Platform root page with "Create your community" flow | Small |

**Total:** ~5 small + ~7 medium components. No schema changes to existing tables. The work is additive — new tables, new cache classes, new middleware, new API endpoints, new UI pages.

---

## 13. Open refinements (post-Phase 7)

These are explicitly **not** in scope for the initial multi-tenant release but are natural extensions:

- **Observer deny list** — "all observers except X" without enumerating the full allowlist.
- **Per-tenant rate limiting** — one tenant's traffic burst shouldn't starve others at the MQTT/ingester level.
- **Tenant-level metrics** — per-tenant Prometheus labels (`instance_id`) on ingest/dashboard metrics.
- **Schema-per-instance** — for very large tenants, move from RLS to a dedicated Postgres schema (D3 already mentions this as belt-and-braces).
- **Tenant billing/quotas** — storage limits, observer caps, feature tiers.
- **Cross-tenant observer handoff** — when an observer moves from Tenant A to Tenant B, migrate the observer's historical data.
