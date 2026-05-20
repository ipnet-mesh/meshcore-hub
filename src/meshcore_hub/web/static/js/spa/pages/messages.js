import { apiGet } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort, formatRelativeTime,
    getChannelLabelsMap, resolveChannelLabel,
    truncateKey, warningBadge,
    pagination, sortableTableHeader, mobileSortSelect, timezoneIndicator,
    renderFilterCard, autoSubmit, submitOnEnter,
    observerIcons, observerDetailRow, toggleObserverDetail, toggleCardObserverDetail
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

export async function render(container, params, router) {
    const query = params.query || {};
    const message_type = query.message_type || '';
    const channel_idx = query.channel_idx || '';
    const observed_by = query.observed_by
        ? (Array.isArray(query.observed_by) ? query.observed_by : [query.observed_by])
        : [];
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 50;
    const offset = (page - 1) * limit;
    const sort = query.sort || 'time';
    const order = query.order || 'desc';

    const config = getConfig();
    let channelLabels = new Map();
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);

    function channelInfo(msg) {
        if (msg.message_type !== 'channel') {
            return { label: null, text: msg.text || '-' };
        }
        const rawText = msg.text || '';
        const match = rawText.match(/^\[([^\]]+)\]\s+([\s\S]*)$/);
        if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
            const knownLabel = resolveChannelLabel(msg.channel_idx, channelLabels);
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
            const knownLabel = resolveChannelLabel(msg.channel_idx, channelLabels);
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
                    observers: [...(msg.observers || [])],
                };
                bySignature.set(signature, clone);
                deduped.push(clone);
                continue;
            }

            const combined = [...(existing.observers || []), ...(msg.observers || [])];
            const seenReceivers = new Set();
            existing.observers = combined.filter((recv) => {
                const key = recv?.public_key || recv?.node_id || `${recv?.observed_at || ''}:${recv?.snr || ''}`;
                if (seenReceivers.has(key)) return false;
                seenReceivers.add(key);
                return true;
            });

            if (!existing.observed_by && msg.observed_by) existing.observed_by = msg.observed_by;
            if (!existing.observer_name && msg.observer_name) existing.observer_name = msg.observer_name;
            if (!existing.observer_tag_name && msg.observer_tag_name) existing.observer_tag_name = msg.observer_tag_name;
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

    let lastContent = nothing;
    let lastTotal = null;

    function renderPage(content, { total = null, error = null } = {}) {
        if (!error) {
            lastContent = content;
            lastTotal = total;
        }
        const displayContent = error ? lastContent : content;
        const displayTotal = error ? lastTotal : total;
        litRender(html`
<div class="flex items-center justify-between mb-4">
    <h1 class="text-3xl font-bold">${t('entities.messages')}</h1>
    ${tzBadge}
</div>
<div class="flex items-center gap-2 mb-4">
    ${displayTotal !== null
        ? html`<span class="badge badge-lg">${t('common.total', { count: displayTotal })}</span>`
        : nothing}
    <span id="auto-refresh-toggle"></span>
    ${error ? warningBadge(error) : nothing}
</div>
${displayContent}`, container);
    }

    // Render page header immediately (old content stays visible until data loads)
    renderPage(nothing);

    async function fetchAndRenderData() {
        try {
            const apiParams = { limit, offset, message_type, channel_idx, sort, order };
            if (observed_by.length > 0) apiParams.observed_by = observed_by;
            const [data, nodesData, channelsData] = await Promise.all([
                apiGet('/api/v1/messages', apiParams),
                apiGet('/api/v1/nodes', { limit: 500, observer: true }),
                apiGet('/api/v1/channels'),
            ]);
            const builtinLabels = getChannelLabelsMap(config);
            const customLabels = new Map(
                (channelsData.items || [])
                    .map(ch => [parseInt(ch.channel_hash, 16), ch.name])
                    .filter(([idx]) => Number.isInteger(idx)),
            );
            channelLabels = new Map([...builtinLabels, ...customLabels]);
            const messages = dedupeBySignature(data.items || []);
            const allNodes = nodesData.items || [];

            const sortedNodes = allNodes.map(n => {
                const tagName = n.tags?.find(t => t.key === 'name')?.value;
                return { ...n, _sortName: (tagName || n.name || '').toLowerCase(), _displayName: tagName || n.name || n.public_key.slice(0, 12) + '...' };
            }).sort((a, b) => a._sortName.localeCompare(b._sortName));
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
                    if (msg.observers && msg.observers.length >= 1) {
                        receiversBlock = html`<span @click=${toggleCardObserverDetail} class="cursor-pointer">${observerIcons(msg.observers)}</span>`;
                    } else if (msg.observed_by) {
                        receiversBlock = html`<span class="opacity-50 text-xs">\u{1F4E1}</span>`;
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
                ${msg.observers && msg.observers.length > 0 ? html`
                    <div class="observer-detail-card hidden mt-2">
                        <table class="table table-xs w-full">
                            <thead><tr><th>Observer</th><th>${t('common.snr_db')}</th><th>${t('common.hops')}</th><th>Received</th></tr></thead>
                            <tbody>
                                ${msg.observers.map(o => {
                                    const dn = o.tag_name || o.name || truncateKey(o.public_key, 12);
                                    const snrD = o.snr != null ? `${Number(o.snr).toFixed(1)}` : '\u2014';
                                    const pathD = o.path_len != null ? `${o.path_len}` : '\u2014';
                                    const timeD = formatRelativeTime(o.observed_at);
                                    return html`<tr>
                                        <td>\u{1F4E1} <a href="/nodes/${o.public_key}" class="link link-hover">${dn}</a></td>
                                        <td>${snrD}</td>
                                        <td>${pathD}</td>
                                        <td><span title=${formatDateTime(o.observed_at)}>${timeD}</span></td>
                                    </tr>`;
                                })}
                            </tbody>
                        </table>
                    </div>
                ` : nothing}
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
                    if (msg.observers && msg.observers.length >= 1) {
                        receiversBlock = html`${observerIcons(msg.observers)}`;
                    } else if (msg.observed_by) {
                        receiversBlock = html`<span class="opacity-50">\u{1F4E1}</span>`;
                    } else {
                        receiversBlock = html`<span class="opacity-50">-</span>`;
                    }
                    return html`<tr class="hover cursor-pointer" @click=${toggleObserverDetail}>
                    <td class="text-lg" title=${typeTitle}>${typeIcon}</td>
                    <td class="text-sm whitespace-nowrap">${formatDateTime(msg.received_at)}</td>
                    <td class="text-sm whitespace-nowrap">
                        <div>${fromPrimary}</div>
                    </td>
                    <td class="break-words max-w-md" style="white-space: pre-wrap;">${displayMessage}</td>
                    <td>${receiversBlock}</td>
                </tr>${observerDetailRow(msg.observers || [])}`;
                });

            const paginationBlock = pagination(page, totalPages, '/messages', {
                message_type, channel_idx, observed_by, limit, sort, order,
            });

            const observerFilter = sortedNodes.length > 0
                ? html`
                <div class="flex flex-col gap-1">
                    <label class="flex items-center py-1">
                        <span class="opacity-80 text-sm">${t('common.filter_observer_label')}</span>
                    </label>
                    <select name="observed_by" multiple size="3"
                            class="select select-bordered select-sm w-full max-w-xs">
                        ${sortedNodes.map(n => html`
                            <option value=${n.public_key}
                                    ?selected=${observed_by.includes(n.public_key)}>
                                ${n._displayName}
                            </option>
                        `)}
                    </select>
                </div>`
                : nothing;

            const filterFields = [
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('common.type')}</span>
                </label>
                <select name="message_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_types')}</option>
                    <option value="contact" ?selected=${message_type === 'contact'}>${t('messages.type_direct')}</option>
                    <option value="channel" ?selected=${message_type === 'channel'}>${t('messages.type_channel')}</option>
                </select>
            </div>`,
                () => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('entities.channel')}</span>
                </label>
                <select name="channel_idx" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">${t('common.all_channels')}</option>
                    ${builtinLabels.size > 0 ? html`<optgroup label=${t('channels.optgroup_standard')}>${[...builtinLabels.entries()].map(([idx, label]) =>
                        html`<option value=${idx} ?selected=${channel_idx === String(idx)}>${label}</option>`
                    )}</optgroup>` : nothing}
                    ${customLabels.size > 0 ? html`<optgroup label=${t('channels.optgroup_custom')}>${[...customLabels.entries()].map(([idx, label]) =>
                        html`<option value=${idx} ?selected=${channel_idx === String(idx)}>${label}</option>`
                    )}</optgroup>` : nothing}
                </select>
            </div>`,
            ];
            if (sortedNodes.length > 0) {
                filterFields.push(() => observerFilter);
            }

            const hasActiveFilters = message_type !== '' || channel_idx !== '' || observed_by.length > 0;
            const existingDetails = container.querySelector('details.collapse');
            const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;

            const filterCard = renderFilterCard({
                fields: filterFields,
                basePath: '/messages',
                navigate,
                collapsible: true,
                defaultOpen: isFilterOpen,
            });

            const headerParams = { message_type, channel_idx, observed_by, limit };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/messages', params: headerParams,
            });

            renderPage(html`${filterCard}

${mobileSortSelect({
    currentSort: sort, currentOrder: order,
    navigate, basePath: '/messages',
    params: headerParams,
    options: [
        { value: 'time:desc', label: t('messages.sort.newest') },
        { value: 'time:asc', label: t('messages.sort.oldest') },
        { value: 'type:asc', label: t('messages.sort.type_az') },
        { value: 'type:desc', label: t('messages.sort.type_za') },
        { value: 'from:asc', label: t('messages.sort.from_az') },
        { value: 'from:desc', label: t('messages.sort.from_za') },
        { value: 'message:asc', label: t('messages.sort.message_az') },
        { value: 'message:desc', label: t('messages.sort.message_za') },
    ],
})}

<div class="lg:hidden space-y-3">
    ${mobileCards}
</div>

<div class="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow">
    <table class="table table-zebra">
        <thead>
            <tr>
                ${sortable(t('common.type'), 'type')}
                ${sortable(t('common.time'), 'time')}
                ${sortable(t('common.from'), 'from')}
                ${sortable(t('entities.message'), 'message')}
                <th>${t('common.observers')}</th>
            </tr>
        </thead>
        <tbody>
            ${tableRows}
        </tbody>
    </table>
</div>

${paginationBlock}`, { total });

        } catch (e) {
            renderPage(nothing, { error: e.message });
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
