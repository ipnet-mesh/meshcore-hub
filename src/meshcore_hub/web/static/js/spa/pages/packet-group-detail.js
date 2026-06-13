import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatRelativeTime, warningBadge, copyToClipboard
} from '../components.js';

function field(label, value) {
    return html`
    <div class="flex flex-col gap-0.5 py-2 border-b border-base-200">
        <span class="text-xs uppercase opacity-60">${label}</span>
        <span class="text-sm">${value}</span>
    </div>`;
}

function formatPath(pathHashes, pathLen) {
    if (pathHashes && pathHashes.length > 0) {
        return html`<code class="font-mono text-xs">${pathHashes.join(' → ')}</code>`;
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

    function shell(content, leaf) {
        litRender(html`
<div class="breadcrumbs text-sm mb-4">
    <ul>
        <li><a href="/">${t('entities.home')}</a></li>
        <li><a href="/packets">${t('entities.packets')}</a></li>
        <li>${leaf || t('packets.detail_title')}</li>
    </ul>
</div>
<div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl font-bold">${t('packets.detail_title')}</h1>
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
                    <div class="overflow-x-auto">
                        <table class="table table-xs w-full">
                            <thead>
                                <tr>
                                    <th>${t('packets.col_path')}</th>
                                    <th>${t('common.hops')}</th>
                                    <th>${t('common.snr_db')}</th>
                                    <th>${t('common.time')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${recs.map(r => html`
                                <tr>
                                    <td>${formatPath(r.path_hashes, r.path_len)}</td>
                                    <td class="text-sm">${r.path_len != null ? r.path_len : '—'}</td>
                                    <td class="text-sm">${r.snr != null ? Number(r.snr).toFixed(1) : '—'}</td>
                                    <td class="text-xs opacity-60">
                                        <span title=${formatDateTime(r.received_at)}>${formatRelativeTime(r.received_at)}</span>
                                    </td>
                                </tr>`)}
                            </tbody>
                        </table>
                    </div>
                </div>`;
            })}
        </div>`
            : nothing;

        shell(html`
${redactedNotice}
<div class="card bg-base-100 shadow">
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
        if (isAbortError(e)) return;
        if (e.status === 404) {
            shell(html`<div class="alert alert-error">${t('common.entity_not_found_details', { entity: t('entities.packet').toLowerCase(), details: hash })}</div>`);
            return;
        }
        shell(warningBadge(e.message));
    }
}
