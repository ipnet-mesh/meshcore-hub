import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, warningBadge, copyToClipboard
} from '../components.js';

function field(label, value) {
    return html`
    <div class="flex flex-col gap-0.5 py-2 border-b border-base-200">
        <span class="text-xs uppercase opacity-60">${label}</span>
        <span class="text-sm">${value}</span>
    </div>`;
}

export async function render(container, params, router) {
    const { signal } = params || {};
    const id = params.id;
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

<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('packets.detail_title')}</h1>
    ${tzBadge}
</div>
${content}`, container);
    }

    shell(html`<div class="opacity-60">${t('common.loading')}</div>`);

    try {
        const [p, channelsData] = await Promise.all([
            apiGet(`/api/v1/packets/${id}`, {}, { signal }),
            apiGet('/api/v1/channels', { limit: 200 }, { signal }).catch(() => ({ items: [] })),
        ]);

        const channelNames = new Map(
            (channelsData.items || [])
                .map(c => [parseInt(c.channel_hash, 16), c.name])
                .filter(([idx]) => !Number.isNaN(idx))
        );

        let channelDisplay = html`<span class="opacity-50">—</span>`;
        if (p.channel_idx != null) {
            const name = channelNames.get(p.channel_idx);
            channelDisplay = html`${name ? `${name} (${p.channel_idx})` : `${p.channel_idx}`}`;
        }

        const observerDisplay = p.observed_by
            ? html`<a href="/nodes/${p.observed_by}" class="link link-hover">${p.observer_tag_name || p.observer_name || p.observed_by}</a>`
            : html`<span class="opacity-50">—</span>`;

        const redactedNotice = p.redacted
            ? html`<div class="alert alert-warning mb-4">\u{1F512} ${t('packets.redacted_notice')}</div>`
            : nothing;

        const rawBlock = p.redacted
            ? nothing
            : html`
        <div class="mt-4">
            <div class="flex items-center justify-between mb-1">
                <span class="text-xs uppercase opacity-60">${t('packets.col_raw')}</span>
                ${p.raw_hex ? html`<button class="btn btn-xs btn-ghost" @click=${(e) => copyToClipboard(e, p.raw_hex)}>${t('packets.copy_raw')}</button>` : nothing}
            </div>
            <pre class="bg-base-200 rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap break-all">${p.raw_hex || '—'}</pre>
        </div>`;

        const decodedBlock = (!p.redacted && p.decoded)
            ? html`
        <div class="mt-4">
            <span class="text-xs uppercase opacity-60">${t('packets.decoded')}</span>
            <pre class="bg-base-200 rounded p-3 text-xs overflow-x-auto">${JSON.stringify(p.decoded, null, 2)}</pre>
        </div>`
            : nothing;

        shell(html`
${redactedNotice}
<div class="card bg-base-100 shadow-sm">
    <div class="card-body">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-8">
            ${field(t('common.time'), formatDateTime(p.received_at))}
            ${field(t('common.observers'), observerDisplay)}
            ${field(t('packets.col_event_type'), p.event_type || '—')}
            ${field(t('entities.channel'), channelDisplay)}
            ${field(t('packets.col_source'), p.source_pubkey_prefix
                ? html`<code class="font-mono text-xs">${p.source_pubkey_prefix}</code>`
                : html`<span class="opacity-50">—</span>`)}
            ${field(t('packets.packet_hash'), p.packet_hash
                ? html`<code class="font-mono text-xs">${p.packet_hash}</code>`
                : html`<span class="opacity-50">—</span>`)}
            ${field(t('packets.packet_type'), p.packet_type != null ? p.packet_type : '—')}
            ${field(t('packets.payload_type'), p.payload_type != null ? p.payload_type : '—')}
            ${field(t('packets.col_route_type'), p.route_type || '—')}
            ${field(t('common.snr_db'), p.snr != null ? Number(p.snr).toFixed(1) : '—')}
            ${field(t('common.hops'), p.path_len != null ? p.path_len : '—')}
        </div>
        ${rawBlock}
        ${decodedBlock}
    </div>
</div>`, p.packet_hash || p.event_type);
    } catch (e) {
        if (isAbortError(e)) return;
        if (e.status === 404) {
            shell(html`<div class="alert alert-error">${t('common.entity_not_found_details', { entity: t('entities.packet').toLowerCase() })}</div>`);
            return;
        }
        shell(warningBadge(e.message));
    }
}
