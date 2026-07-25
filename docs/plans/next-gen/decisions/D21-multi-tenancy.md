# D21: Multi-Tenancy — Shared Platform, Self-Provisioning Tenants

- **Status:** Locked
- **Iteration:** 7 (revised: self-provisioning)

## Context

The schema is instance-scoped from Phase 0: every tenant table carries `instance_id` with RLS (D3), NATS subjects are namespaced (`meshcore.ingest.<inst>.*`), cache keys are scoped, and settings/pages/channels/routes/tags/profiles are all per-instance. The single-tenant assumption lives in exactly three places: the MqttIngester's constructor (`instance_id` is a process-level arg), the API middleware (`instance_id` from env), and OIDC config (Tier-1 env vars).

> **Correction (iteration 8, F1/F8).** "The schema does not change" only holds because the base schema is
> built multi-tenant-ready — which required four fixes folded into Phase 0: (1) every business-key unique
> is `UNIQUE (instance_id, …)` (`nodes.public_key`, the `event_hash` columns, `channels.name/key_hex`);
> (2) `settings` PK is `(instance_id, key)`, not `key` alone; (3) a **single** platform-wide `INGEST`
> NATS stream (`meshcore.ingest.>`), so the Phase 7 wildcard consumer needs no new stream; (4) RLS is
> `FORCE`d and the app runs as a non-owner role. With global uniques or a per-instance stream, Phase 7
> would in fact require schema/topology migrations. See [review-findings.md](../review-findings.md).

The question (iteration 7): can multiple MeshCore communities share one platform deployment — each with their own branding, pages, OIDC, and observer pool — while the MQTT backend accepts all observers and each tenant chooses which ones they want?

**Design constraint (user-directed):** tenants must be able to self-provision. No superadmin/platform-operator action should be required to create a tenant, configure workers, or set up DNS.

## Decision

**Multi-tenancy as a Phase 7 extension** on top of the single-tenant Phases 0–6. The schema does not change. Three core mechanisms:

1. **Self-service registration.** Tenants create themselves via a public `POST /api/v1/register` endpoint (community name, subdomain, admin credentials). The system creates the instance, hostname, settings seed, and admin user in one transaction. The tenant admin is immediately logged in at their subdomain. No CLI, no operator, no approval gate. Abuse prevention via rate limiting + optional captcha (platform-level settings).
2. **Shared worker pool with dynamic discovery.** Workers are tenant-agnostic: IngestWorkers subscribe to `meshcore.ingest.>` (wildcard), WebhookWorkers to `events.new.>` (wildcard), and the DerivedStateWorker iterates over all active instances. New tenants are picked up automatically via NATS `instance.created` notifications — zero per-tenant infrastructure, no Compose profiles, no operator action.
3. **Wildcard DNS + self-service subdomains.** The platform runs `*.PLATFORM_DOMAIN` with a wildcard TLS certificate. Tenants pick a subdomain at registration. Custom domains are tenant-admin self-service (add hostname in Admin UI, configure CNAME at their DNS provider).

Supporting mechanisms (unchanged from original design):

4. **Observer scoping is a tenant-admin function.** Each tenant manages an observer allowlist (prefix-based, DB-backed, per-instance). Empty allowlist = all observers. The MqttIngester routes each envelope to the tenant(s) that want it.
5. **Per-tenant OIDC.** OIDC config moves from Tier-1 env vars to a per-instance DB table. The web tier resolves which tenant's config to use from the request hostname.
6. **Tenant deletion is self-service (soft) + CLI (purge).** A tenant admin soft-deletes their own community (reversible). Purge (permanent, multi-table) is CLI-only after a grace period.

## Consequences

**Positive:** Multiple communities share one deployment with **zero platform-operator intervention** for tenant creation. Registration → operational in seconds. Each community has their own website (subdomain), branding, pages, OIDC, and observer pool. The schema is unchanged — no migration from single-tenant. Observer assignment is self-service (tenant admin). Shared observers work naturally (fan-out at the NATS subject level). The shared worker pool eliminates per-tenant infrastructure entirely.

**Negative:** The MqttIngester's routing cache grows with the number of tenants × observers. The ChannelKeyCache loads keys for all tenants. A shared worker pool means a pathological tenant could starve others (mitigated by per-tenant rate limiting as a future refinement). Wildcard DNS requires the platform operator to control a domain and its DNS zone. The "platform admin" is the first tenant's admin — no separate superadmin role exists, which means platform-level settings (registration control) are managed by a regular tenant admin.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Shared platform, self-provisioning tenants** (chosen) | Zero operator intervention; wildcard DNS + shared workers + registration API. |
| CLI-only tenant creation (original design) | Rejected — requires platform-operator action for every new tenant; violates self-provisioning constraint. |
| Per-tenant Compose profiles (original design) | Rejected — requires operator to create/start profiles per tenant; doesn't scale with self-provisioning. |
| Per-tenant DNS configuration | Rejected — requires operator to configure DNS per tenant; wildcard DNS eliminates this. |
| Approval-based registration | Rejected — adds a superadmin gate; violates "no superadmin action" constraint. Optional as a future refinement. |
| Separate platform-admin role | Rejected — adds a new auth concept; the first tenant's admin manages platform settings. |
