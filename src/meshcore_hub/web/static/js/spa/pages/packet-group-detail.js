import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatRelativeTime, warningBadge, copyToClipboard,
    loading, truncateKey
} from '../components.js';

function field(label, value) {
    return html`
    <div class="flex flex-col gap-0.5 py-2 border-b border-base-200">
        <span class="text-xs uppercase opacity-60">${label}</span>
        <span class="text-sm">${value}</span>
    </div>`;
}

// Centre-truncation thresholds for long paths. Counts hops, not characters,
// so variable-length hashes (1–3 bytes) truncate predictably.
const PATH_MAX_BADGES = 16;
const PATH_HEAD = 7;
const PATH_TAIL = 7;

// Max nodes listed in the path-hash lookup popover before linking out to the
// full (prefix-filtered) Nodes page.
const PATH_POPOVER_NODE_CAP = 8;

// Render a single path-hash as a badge. Clicking it opens a popover listing the
// node(s) whose public key starts with this hash (see openPathPopover in render).
function pathBadge(hash, onClick) {
    return html`<span class="badge badge-sm badge-primary font-mono text-xs path-hash-badge cursor-pointer"
        data-path-hash=${hash} @click=${(e) => onClick(e, hash)}>${hash}</span>`;
}

const pathArrow = html`<span class="opacity-40 text-xs">→</span>`;

// Join badges with arrow separators into a flex-wrap container so long paths
// wrap onto multiple lines (growing in height, not width) on narrow screens.
function pathRow(badges) {
    const parts = [];
    badges.forEach((b, i) => {
        if (i > 0) parts.push(pathArrow);
        parts.push(b);
    });
    return html`<span class="flex flex-wrap items-center gap-1">${parts}</span>`;
}

function formatPath(pathHashes, pathLen, onBadgeClick) {
    const badge = (h) => pathBadge(h, onBadgeClick);
    if (pathHashes && pathHashes.length > 0) {
        if (pathHashes.length <= PATH_MAX_BADGES) {
            return pathRow(pathHashes.map(badge));
        }
        const hidden = pathHashes.length - PATH_HEAD - PATH_TAIL;
        const ellipsis = html`<span class="badge badge-sm badge-ghost cursor-help" title=${t('packets.hops_hidden', { count: hidden })}>…</span>`;
        const badges = [
            ...pathHashes.slice(0, PATH_HEAD).map(badge),
            ellipsis,
            ...pathHashes.slice(-PATH_TAIL).map(badge),
        ];
        return pathRow(badges);
    }
    if (pathLen != null) {
        return html`${pathLen} ${t('common.hops').toLowerCase()}`;
    }
    return html`<span class="opacity-50">—</span>`;
}

function groupByObserver(receptions) {
    const groups = new Map();
    for (const r of receptions) {
        const key = r.observed_by || '__unknown__';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(r);
    }
    return groups;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    const hash = params.hash;
    const config = getConfig();
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;

    // ── Path-hash → node lookup popover ───────────────────────────────────────
    // Clicking a path badge opens a single floating panel (appended to <body>)
    // that lists the node(s) whose public key starts with that hex prefix. A
    // prefix may match zero or more nodes.
    let popoverEl = null;
    let popoverListeners = null;

    function closePopover() {
        if (popoverListeners) {
            document.removeEventListener('click', popoverListeners.onDocClick);
            document.removeEventListener('keydown', popoverListeners.onKey);
            popoverListeners = null;
        }
        if (popoverEl) {
            popoverEl.remove();
            popoverEl = null;
        }
    }

    function nodeDisplayName(n) {
        const tagName = n.tags?.find(tag => tag.key === 'name')?.value;
        return tagName || n.name || truncateKey(n.public_key, 12);
    }

    function positionPopover(rect) {
        if (!popoverEl) return;
        const margin = 8;
        const pw = popoverEl.offsetWidth || 256;
        const ph = popoverEl.offsetHeight || 0;
        let left = Math.min(rect.left, window.innerWidth - pw - margin);
        if (left < margin) left = margin;
        let top = rect.bottom + 4;
        if (top + ph + margin > window.innerHeight && rect.top - ph - 4 > margin) {
            top = rect.top - ph - 4;
        }
        popoverEl.style.left = `${left}px`;
        popoverEl.style.top = `${top}px`;
    }

    function popoverShell(hashLabel, body) {
        return html`
        <div class="flex items-center justify-between gap-2 px-3 py-2 border-b border-base-200 sticky top-0 bg-base-100 rounded-t-box">
            <span class="text-xs font-semibold uppercase opacity-70">${t('packets.path_nodes_title', { hash: hashLabel })}</span>
            <button class="btn btn-xs btn-ghost btn-circle" aria-label=${t('common.close')} @click=${closePopover}>✕</button>
        </div>
        <div>${body}</div>`;
    }

    async function openPathPopover(e, ph) {
        e.preventDefault();
        e.stopPropagation();
        const rect = e.currentTarget.getBoundingClientRect();
        closePopover();

        popoverEl = document.createElement('div');
        popoverEl.className = 'path-node-popover fixed z-[1000] w-64 max-w-[90vw] max-h-[60vh] overflow-y-auto bg-base-100 rounded-box shadow-lg border border-base-300';
        document.body.appendChild(popoverEl);

        litRender(popoverShell(ph, html`<div class="p-3">${loading()}</div>`), popoverEl);
        positionPopover(rect);

        const onDocClick = (ev) => { if (popoverEl && !popoverEl.contains(ev.target)) closePopover(); };
        const onKey = (ev) => { if (ev.key === 'Escape') closePopover(); };
        popoverListeners = { onDocClick, onKey };
        // Defer so the click that opened the popover doesn't immediately close it.
        setTimeout(() => {
            document.addEventListener('click', onDocClick);
            document.addEventListener('keydown', onKey);
        }, 0);

        try {
            const data = await apiGet('/api/v1/nodes',
                { pubkey_prefix: ph, sort: 'name', order: 'asc', limit: PATH_POPOVER_NODE_CAP },
                { signal });
            if (!popoverEl) return; // closed while loading
            const items = (data.items || []).slice()
                .sort((a, b) => nodeDisplayName(a).localeCompare(nodeDisplayName(b)));
            const more = (data.total || 0) - items.length;
            const body = items.length === 0
                ? html`<div class="px-3 py-4 text-sm opacity-60 text-center">${t('packets.path_no_nodes')}</div>`
                : html`<ul class="menu menu-sm w-full">
                    ${items.map(n => html`<li>
                        <a href="/nodes/${n.public_key}" @click=${closePopover} class="flex flex-col items-start gap-0">
                            <span class="text-sm">${nodeDisplayName(n)}</span>
                            <span class="font-mono text-xs opacity-50">${truncateKey(n.public_key, 16)}</span>
                        </a></li>`)}
                    ${more > 0 ? html`<li>
                        <a href="/nodes?pubkey_prefix=${ph}" @click=${closePopover} class="text-xs opacity-70">
                            ${t('packets.path_nodes_more', { count: more })}
                        </a></li>` : nothing}
                </ul>`;
            litRender(popoverShell(ph, body), popoverEl);
            positionPopover(rect);
        } catch (err) {
            if (isAbortError(err) || !popoverEl) return;
            litRender(popoverShell(ph, html`<div class="p-3">${warningBadge(err.message)}</div>`), popoverEl);
            positionPopover(rect);
        }
    }

    // ── Per-observer reception rendering ──────────────────────────────────────
    const hopsValue = (r) => (r.path_len != null ? r.path_len : '—');
    const snrValue = (r) => (r.snr != null ? Number(r.snr).toFixed(1) : '—');
    const timeValue = (r) => html`<span title=${formatDateTime(r.received_at)}>${formatRelativeTime(r.received_at)}</span>`;

    function stat(label, value) {
        return html`<div class="flex flex-col">
            <span class="text-[10px] uppercase opacity-60">${label}</span>
            <span class="text-sm">${value}</span>
        </div>`;
    }

    // Mobile (< lg): one card per reception, path full-width on top, stats below.
    function receptionCards(recs) {
        return html`<div class="lg:hidden space-y-2">
            ${recs.map(r => html`
            <div class="rounded-box bg-base-200/60 p-3">
                <div class="mb-2">${formatPath(r.path_hashes, r.path_len, openPathPopover)}</div>
                <div class="grid grid-cols-3 gap-2">
                    ${stat(t('common.time'), timeValue(r))}
                    ${stat(t('common.hops'), hopsValue(r))}
                    ${stat(t('common.snr_db'), snrValue(r))}
                </div>
            </div>`)}
        </div>`;
    }

    // Desktop (lg+): table-fixed so the right-aligned stat columns line up across
    // every observer block regardless of path length.
    function receptionTable(recs) {
        return html`<div class="hidden lg:block overflow-x-auto">
            <table class="table table-xs table-fixed w-full">
                <thead>
                    <tr>
                        <th>${t('packets.col_path')}</th>
                        <th class="w-16 text-right">${t('common.hops')}</th>
                        <th class="w-20 text-right">${t('common.snr_db')}</th>
                        <th class="w-32 text-right">${t('common.time')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${recs.map(r => html`
                    <tr>
                        <td class="whitespace-normal align-top">${formatPath(r.path_hashes, r.path_len, openPathPopover)}</td>
                        <td class="w-16 text-right text-sm align-top">${hopsValue(r)}</td>
                        <td class="w-20 text-right text-sm align-top">${snrValue(r)}</td>
                        <td class="w-32 text-right text-xs opacity-60 align-top whitespace-nowrap">${timeValue(r)}</td>
                    </tr>`)}
                </tbody>
            </table>
        </div>`;
    }

    function shell(content, leaf) {
        litRender(html`
<div class="breadcrumbs text-sm mb-4">
    <ul>
        <li><a href="/">${t('entities.home')}</a></li>
        <li><a href="/packets">${t('entities.packets')}</a></li>
        <li>${leaf || t('packets.detail_title')}</li>
    </ul>
</div>
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('packets.detail_title')}</h1>
    ${tzBadge}
</div>
${content}`, container);
    }

    shell(html`<div class="opacity-60">${t('common.loading')}</div>`);

    try {
        const [g, channelsData] = await Promise.all([
            apiGet(`/api/v1/packet-groups/${hash}`, {}, { signal }),
            apiGet('/api/v1/channels', { limit: 200 }, { signal }).catch(() => ({ items: [] })),
        ]);

        const channelNames = new Map(
            (channelsData.items || [])
                .map(c => [parseInt(c.channel_hash, 16), c.name])
                .filter(([idx]) => !Number.isNaN(idx))
        );

        let channelDisplay = html`<span class="opacity-50">—</span>`;
        if (g.channel_idx != null) {
            const name = channelNames.get(g.channel_idx);
            channelDisplay = html`${name ? `${name} (${g.channel_idx})` : `${g.channel_idx}`}`;
        }

        const redactedNotice = g.redacted
            ? html`<div class="alert alert-warning mb-4">\u{1F512} ${t('packets.redacted_notice')}</div>`
            : nothing;

        const rawBlock = (!g.redacted && g.raw_hex)
            ? html`
        <div class="mt-4">
            <div class="flex items-center justify-between mb-1">
                <span class="text-xs uppercase opacity-60">${t('packets.col_raw')}</span>
                <button class="btn btn-xs btn-ghost" @click=${(e) => copyToClipboard(e, g.raw_hex)}>${t('packets.copy_raw')}</button>
            </div>
            <pre class="bg-base-200 rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap break-all">${g.raw_hex}</pre>
        </div>`
            : nothing;

        const decodedBlock = (!g.redacted && g.decoded)
            ? html`
        <div class="mt-4">
            <span class="text-xs uppercase opacity-60">${t('packets.decoded')}</span>
            <pre class="bg-base-200 rounded p-3 text-xs overflow-x-auto">${JSON.stringify(g.decoded, null, 2)}</pre>
        </div>`
            : nothing;

        const receptions = g.receptions || [];
        const observerGroups = groupByObserver(receptions);

        const receptionsSection = receptions.length > 0
            ? html`
        <div class="mt-6">
            <h2 class="text-sm font-semibold uppercase opacity-60 mb-3">
                ${t('packets.receptions_title')}
                <span class="ml-1 normal-case opacity-80">(${g.reception_count} ${g.reception_count === 1 ? t('packets.reception_singular') : t('packets.reception_plural')}, ${g.observer_count} ${t('common.observers').toLowerCase()})</span>
            </h2>
            ${[...observerGroups.entries()].map(([_key, recs]) => {
                const first = recs[0];
                const displayName = first.observer_tag_name || first.observer_name
                    || (first.observed_by ? first.observed_by.slice(0, 12) + '…' : '—');
                return html`
                <div class="mb-5">
                    <div class="text-sm font-medium mb-1">
                        \u{1F4E1}
                        ${first.observed_by
                            ? html`<a href="/nodes/${first.observed_by}" class="link link-hover">${displayName}</a>`
                            : html`${displayName}`}
                        ${recs.length > 1
                            ? html`<span class="text-xs opacity-50 ml-1">(${recs.length} ${t('packets.reception_plural')})</span>`
                            : nothing}
                    </div>
                    ${receptionCards(recs)}
                    ${receptionTable(recs)}
                </div>`;
            })}
        </div>`
            : nothing;

        shell(html`
${redactedNotice}
<div class="card bg-base-100 shadow-sm">
    <div class="card-body">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-8">
            ${field(t('common.time'), formatDateTime(g.first_seen))}
            ${field(t('packets.col_event_type'), g.event_type || '—')}
            ${field(t('entities.channel'), channelDisplay)}
            ${field(t('packets.col_source'), g.source_pubkey_prefix
                ? html`<code class="font-mono text-xs">${g.source_pubkey_prefix}</code>`
                : html`<span class="opacity-50">—</span>`)}
            ${field(t('packets.packet_hash'), g.packet_hash
                ? html`<code class="font-mono text-xs">${g.packet_hash}</code>`
                : html`<span class="opacity-50">—</span>`)}
            ${field(t('packets.packet_type'), g.packet_type != null ? g.packet_type : '—')}
            ${field(t('packets.payload_type'), g.payload_type != null ? g.payload_type : '—')}
            ${field(t('packets.col_route_type'), g.route_type || '—')}
            ${field(t('packets.receptions_count'),
                html`${g.reception_count} ${g.reception_count === 1 ? t('packets.reception_singular') : t('packets.reception_plural')} · ${g.observer_count} ${t('common.observers').toLowerCase()}`)}
        </div>
        ${receptionsSection}
        ${rawBlock}
        ${decodedBlock}
    </div>
</div>`, g.packet_hash || g.event_type);

    } catch (e) {
        if (isAbortError(e)) return closePopover;
        if (e.status === 404) {
            shell(html`<div class="alert alert-warning">${t('packets.not_found_retention')}</div>`, t('entities.packet'));
            return closePopover;
        }
        shell(warningBadge(e.message));
    }

    // Tear down any open popover (and its global listeners) on navigation.
    return closePopover;
}
