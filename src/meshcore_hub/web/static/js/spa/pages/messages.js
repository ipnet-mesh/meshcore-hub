import { apiGet } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort,
    truncateKey, errorAlert,
    pagination, timezoneIndicator,
    createFilterHandler, autoSubmit, submitOnEnter
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

export async function render(container, params, router) {
    const query = params.query || {};
    const message_type = query.message_type || '';
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 50;
    const offset = (page - 1) * limit;

    const config = getConfig();
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);
    const configuredChannelLabels = new Map(
        Object.entries(config.channel_labels || {})
            .map(([idx, label]) => [parseInt(idx, 10), typeof label === 'string' ? label.trim() : ''])
            .filter(([idx, label]) => Number.isInteger(idx) && label.length > 0),
    );
    const builtInChannelLabels = new Map([
        [17, 'Public'],
        [217, '#test'],
        [202, '#bot'],
        [184, '#chat'],
        [159, '#jokes'],
        [221, '#sports'],
        [104, '#emergency'],
    ]);

    function knownChannelLabel(channelIdx) {
        return configuredChannelLabels.get(channelIdx) || builtInChannelLabels.get(channelIdx) || null;
    }

    function channelInfo(msg) {
        if (msg.message_type !== 'channel') {
            return { label: null, text: msg.text || '-' };
        }
        const rawText = msg.text || '';
        const match = rawText.match(/^\[([^\]]+)\]\s+([\s\S]*)$/);
        if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
            const knownLabel = knownChannelLabel(msg.channel_idx);
            if (knownLabel) {
                return {
                    label: knownLabel,
                    text: match ? (match[2] || '-') : (rawText || '-'),
                };
            }
        }
        if (msg.channel_name) {
            return { label: msg.channel_name, text: msg.text || '-' };
        }
        if (match) {
            return {
                label: match[1],
                text: match[2] || '-',
            };
        }
        if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
            const knownLabel = knownChannelLabel(msg.channel_idx);
            return { label: knownLabel || `Ch ${msg.channel_idx}`, text: rawText || '-' };
        }
        return { label: t('messages.type_channel'), text: rawText || '-' };
    }

    function senderBlock(msg, emphasize = false) {
        const senderName = msg.sender_tag_name || msg.sender_name;
        if (senderName) {
            return emphasize
                ? html`<span class="font-medium">${senderName}</span>`
                : html`${senderName}`;
        }
        const prefix = (msg.pubkey_prefix || '').slice(0, 12);
        if (prefix) {
            return html`<span class="font-mono text-xs">${prefix}</span>`;
        }
        return html`<span class="opacity-50">-</span>`;
    }

    function parseSenderFromText(text) {
        if (!text || typeof text !== 'string') {
            return { sender: null, text: text || '-' };
        }
        const patterns = [
            /^\s*ack\s+@\[(.+?)\]\s*:\s*([\s\S]+)$/i,
            /^\s*@\[(.+?)\]\s*:\s*([\s\S]+)$/i,
            /^\s*ack\s+([^:|\n]{1,80})\s*:\s*([\s\S]+)$/i,
        ];
        for (const pattern of patterns) {
            const match = text.match(pattern);
            if (!match) continue;
            const sender = (match[1] || '').trim();
            const remaining = (match[2] || '').trim();
            if (!sender) continue;
            return {
                sender,
                text: remaining || text,
            };
        }
        return { sender: null, text };
    }

    function messageTextWithSender(msg, text) {
        const parsed = parseSenderFromText(text || '-');
        const explicitSender = msg.sender_tag_name || msg.sender_name || (msg.pubkey_prefix || '').slice(0, 12) || null;
        const sender = explicitSender || parsed.sender;
        const body = (parsed.text || text || '-').trim() || '-';
        if (!sender) {
            return body;
        }
        if (body.toLowerCase().startsWith(`${sender.toLowerCase()}:`)) {
            return body;
        }
        return `${sender}: ${body}`;
    }

    function dedupeBySignature(items) {
        const deduped = [];
        const bySignature = new Map();

        for (const msg of items) {
            const signature = typeof msg.signature === 'string' ? msg.signature.trim().toUpperCase() : '';
            const canDedupe = msg.message_type === 'channel' && signature.length >= 8;
            if (!canDedupe) {
                deduped.push(msg);
                continue;
            }

            const existing = bySignature.get(signature);
            if (!existing) {
                const clone = {
                    ...msg,
                    receivers: [...(msg.receivers || [])],
                };
                bySignature.set(signature, clone);
                deduped.push(clone);
                continue;
            }

            const combined = [...(existing.receivers || []), ...(msg.receivers || [])];
            const seenReceivers = new Set();
            existing.receivers = combined.filter((recv) => {
                const key = recv?.public_key || recv?.node_id || `${recv?.received_at || ''}:${recv?.snr || ''}`;
                if (seenReceivers.has(key)) return false;
                seenReceivers.add(key);
                return true;
            });

            if (!existing.received_by && msg.received_by) existing.received_by = msg.received_by;
            if (!existing.receiver_name && msg.receiver_name) existing.receiver_name = msg.receiver_name;
            if (!existing.receiver_tag_name && msg.receiver_tag_name) existing.receiver_tag_name = msg.receiver_tag_name;
            if (!existing.pubkey_prefix && msg.pubkey_prefix) existing.pubkey_prefix = msg.pubkey_prefix;
            if (!existing.sender_name && msg.sender_name) existing.sender_name = msg.sender_name;
            if (!existing.sender_tag_name && msg.sender_tag_name) existing.sender_tag_name = msg.sender_tag_name;
            if (!existing.channel_name && msg.channel_name) existing.channel_name = msg.channel_name;
            if (
                existing.channel_name === 'Public'
                && msg.channel_name
                && msg.channel_name !== 'Public'
            ) {
                existing.channel_name = msg.channel_name;
            }
            if (existing.channel_idx === null || existing.channel_idx === undefined) {
                if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
                    existing.channel_idx = msg.channel_idx;
                }
            } else if (
                existing.channel_idx === 17
                && msg.channel_idx !== null
                && msg.channel_idx !== undefined
                && msg.channel_idx !== 17
            ) {
                existing.channel_idx = msg.channel_idx;
            }
        }

        return deduped;
    }

    function renderPage(content, { total = null } = {}) {
        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">${t('entities.messages')}</h1>
    <div class="flex items-center gap-2">
        <span id="auto-refresh-toggle"></span>
        ${tzBadge}
        ${total !== null ? html`<span class="badge badge-lg">${t('common.total', { count: total })}</span>` : nothing}
    </div>
</div>
${content}`, container);
    }

    // Render page header immediately (old content stays visible until data loads)
    renderPage(nothing);

    async function fetchAndRenderData() {
        try {
            const data = await apiGet('/api/v1/messages', { limit, offset, message_type });
            const messages = dedupeBySignature(data.items || []);
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);

            const mobileCards = messages.length === 0
                ? html`<div class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.messages').toLowerCase() })}</div>`
                : messages.map(msg => {
                    const isChannel = msg.message_type === 'channel';
                    const typeIcon = isChannel ? '\u{1F4FB}' : '\u{1F464}';
                    const typeTitle = isChannel ? t('messages.type_channel') : t('messages.type_contact');
                    const chInfo = channelInfo(msg);
                    const sender = senderBlock(msg);
                    const displayMessage = messageTextWithSender(msg, chInfo.text);
                    const fromPrimary = isChannel
                        ? html`<span class="font-medium">${chInfo.label || t('messages.type_channel')}</span>`
                        : sender;
                    let receiversBlock = nothing;
                    if (msg.receivers && msg.receivers.length >= 1) {
                        receiversBlock = html`<div class="flex gap-0.5">
                            ${msg.receivers.map(recv => {
                                const recvName = recv.tag_name || recv.name || truncateKey(recv.public_key, 12);
                                return html`<a href="/nodes/${recv.public_key}" class="text-sm hover:opacity-70" title=${recvName}>\u{1F4E1}</a>`;
                            })}
                        </div>`;
                    } else if (msg.received_by) {
                        const recvTitle = msg.receiver_tag_name || msg.receiver_name || truncateKey(msg.received_by, 12);
                        receiversBlock = html`<a href="/nodes/${msg.received_by}" class="text-sm hover:opacity-70" title=${recvTitle}>\u{1F4E1}</a>`;
                    }
                    return html`<div class="card bg-base-100 shadow-sm">
            <div class="card-body p-3">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                        <span class="text-lg flex-shrink-0" title=${typeTitle}>
                            ${typeIcon}
                        </span>
                        <div class="min-w-0">
                            <div class="font-medium text-sm truncate">
                                ${fromPrimary}
                            </div>
                            <div class="text-xs opacity-60">
                                ${formatDateTimeShort(msg.received_at)}
                            </div>
                        </div>
                    </div>
                    <div class="flex items-center gap-2 flex-shrink-0">
                        ${receiversBlock}
                    </div>
                </div>
                <p class="text-sm mt-2 break-words whitespace-pre-wrap">${displayMessage}</p>
            </div>
        </div>`;
                });

            const tableRows = messages.length === 0
                ? html`<tr><td colspan="5" class="text-center py-8 opacity-70">${t('common.no_entity_found', { entity: t('entities.messages').toLowerCase() })}</td></tr>`
                : messages.map(msg => {
                    const isChannel = msg.message_type === 'channel';
                    const typeIcon = isChannel ? '\u{1F4FB}' : '\u{1F464}';
                    const typeTitle = isChannel ? t('messages.type_channel') : t('messages.type_contact');
                    const chInfo = channelInfo(msg);
                    const sender = senderBlock(msg, true);
                    const displayMessage = messageTextWithSender(msg, chInfo.text);
                    const fromPrimary = isChannel
                        ? html`<span class="font-medium">${chInfo.label || t('messages.type_channel')}</span>`
                        : sender;
                    let receiversBlock;
                    if (msg.receivers && msg.receivers.length >= 1) {
                        receiversBlock = html`<div class="flex gap-1">
                            ${msg.receivers.map(recv => {
                                const recvName = recv.tag_name || recv.name || truncateKey(recv.public_key, 12);
                                return html`<a href="/nodes/${recv.public_key}" class="text-lg hover:opacity-70" title=${recvName}>\u{1F4E1}</a>`;
                            })}
                        </div>`;
                    } else if (msg.received_by) {
                        const recvTitle = msg.receiver_tag_name || msg.receiver_name || truncateKey(msg.received_by, 12);
                        receiversBlock = html`<a href="/nodes/${msg.received_by}" class="text-lg hover:opacity-70" title=${recvTitle}>\u{1F4E1}</a>`;
                    } else {
                        receiversBlock = html`<span class="opacity-50">-</span>`;
                    }
                    return html`<tr class="hover align-top">
                    <td class="text-lg" title=${typeTitle}>${typeIcon}</td>
                    <td class="text-sm whitespace-nowrap">${formatDateTime(msg.received_at)}</td>
                    <td class="text-sm whitespace-nowrap">
                        <div>${fromPrimary}</div>
                    </td>
                    <td class="break-words max-w-md" style="white-space: pre-wrap;">${displayMessage}</td>
                    <td>${receiversBlock}</td>
                </tr>`;
                });

            const paginationBlock = pagination(page, totalPages, '/messages', {
                message_type, limit,
            });

            renderPage(html`
<div class="card shadow mb-6 panel-solid" style="--panel-color: var(--color-neutral)">
    <div class="card-body py-4">
        <form method="GET" action="/messages" class="flex gap-4 flex-wrap items-end" @submit=${createFilterHandler('/messages', navigate)}>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">${t('common.type')}</span>
                </label>
                <select name="message_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_types')}</option>
                    <option value="contact" ?selected=${message_type === 'contact'}>${t('messages.type_direct')}</option>
                    <option value="channel" ?selected=${message_type === 'channel'}>${t('messages.type_channel')}</option>
                </select>
            </div>
            <div class="flex gap-2 w-full sm:w-auto">
                <button type="submit" class="btn btn-primary btn-sm">${t('common.filter')}</button>
                <a href="/messages" class="btn btn-ghost btn-sm">${t('common.clear')}</a>
            </div>
        </form>
    </div>
</div>

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow">
    <table class="table table-zebra">
        <thead>
            <tr>
                <th>${t('common.type')}</th>
                <th>${t('common.time')}</th>
                <th>${t('common.from')}</th>
                <th>${t('entities.message')}</th>
                <th>${t('common.receivers')}</th>
            </tr>
        </thead>
        <tbody>
            ${tableRows}
        </tbody>
    </table>
</div>

${paginationBlock}`, { total });

        } catch (e) {
            renderPage(errorAlert(e.message));
        }
    }

    await fetchAndRenderData();

    const toggleEl = container.querySelector('#auto-refresh-toggle');
    const { cleanup } = createAutoRefresh({
        fetchAndRender: fetchAndRenderData,
        toggleContainer: toggleEl,
    });
    return cleanup;
}
