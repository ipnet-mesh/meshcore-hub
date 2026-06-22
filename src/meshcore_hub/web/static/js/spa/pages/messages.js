import { apiGet, isAbortError } from '../api.js';
import {
    html, litRender, nothing, t,
    getConfig, formatDateTime, formatDateTimeShort,
    getChannelLabelsMap, resolveChannelLabel,
    warningBadge,
    pagination, sortableTableHeader, mobileSortSelect,
    renderFilterCard, autoSubmit,
    observerIcons, getDisabledObservers, toggleObserver, observerFilterBadges
} from '../components.js';
import { createAutoRefresh } from '../auto-refresh.js';

export async function render(container, params, router) {
    const { signal } = params || {};
    const query = params.query || {};
    const message_type = query.message_type || '';
    const channel_idx = query.channel_idx || '';
    const includeSpamParam = query.include_spam === 'true' || query.include_spam === true;
    const page = parseInt(query.page, 10) || 1;
    const limit = parseInt(query.limit, 10) || 50;
    const offset = (page - 1) * limit;
    const sort = query.sort || 'time';
    const order = query.order || 'desc';

    // Observer filter is sourced from localStorage (shared toggle badges), not the URL.
    let disabledObservers = getDisabledObservers();

    const config = getConfig();
    const features = config.features || {};
    const packetsEnabled = features.packets !== false;
    // Spam toggle is only shown when the feature is enabled; when off the API
    // returns everything anyway, so the include_spam param is a no-op.
    const spamEnabled = features.spam === true;
    const includeSpam = spamEnabled && includeSpamParam;
    let channelLabels = new Map();
    const tz = config.timezone || '';
    const tzBadge = tz && tz !== 'UTC' ? html`<span class="text-sm opacity-60">${tz}</span>` : nothing;
    const navigate = (url) => router.navigate(url);
    // Packet-detail target for a row/card, or null when not navigable.
    const packetDetailUrl = (packetHash) =>
        (packetsEnabled && packetHash) ? `/packets/hash/${packetHash}` : null;

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

    // Collapse any run of newlines (and the whitespace around them) into a
    // single space so multi-line messages don't blow up the table/card layout.
    function collapseNewlines(text) {
        if (!text || typeof text !== 'string') return text;
        return text.replace(/\s*\n\s*/g, ' ');
    }

    function messageTextWithSender(msg, text) {
        const parsed = parseSenderFromText(text || '-');
        const explicitSender = msg.sender_tag_name || msg.sender_name || (msg.pubkey_prefix || '').slice(0, 12) || null;
        const sender = explicitSender || parsed.sender;
        const body = collapseNewlines((parsed.text || text || '-').trim()) || '-';
        if (!sender) {
            return body;
        }
        if (body.toLowerCase().startsWith(`${sender.toLowerCase()}:`)) {
            return body;
        }
        return `${sender}: ${body}`;
    }

    // Small badge for rows the scorer flagged as likely spam. Only meaningful
    // when the spam feature is on (otherwise spam_score is null on every row).
    function spamBadge(msg) {
        if (!spamEnabled || msg.spam_score == null || msg.spam_score < 0.6) {
            return nothing;
        }
        return html`<span class="badge badge-warning badge-sm"
            title=${`${t('messages.spam.badge')} ${msg.spam_score.toFixed(2)}`}>${t('messages.spam.badge')}</span>`;
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
            // Phase 1: fetch the observer node list (and channels) first. The messages
            // API filters observers by inclusion only, so we need the full observer list
            // to translate the stored "disabled" set into an explicit include-list.
            const [nodesData, channelsData] = await Promise.all([
                apiGet('/api/v1/nodes', { limit: 500, observer: true }, { signal }),
                apiGet('/api/v1/channels', {}, { signal }),
            ]);
            const builtinLabels = getChannelLabelsMap(config);
            const customLabels = new Map(
                (channelsData.items || [])
                    .map(ch => [parseInt(ch.channel_hash, 16), ch.name])
                    .filter(([idx]) => Number.isInteger(idx)),
            );
            channelLabels = new Map([...builtinLabels, ...customLabels]);
            const allNodes = nodesData.items || [];

            const sortedNodes = allNodes.map(n => {
                const tagName = n.tags?.find(t => t.key === 'name')?.value;
                return { ...n, _sortName: (tagName || n.name || '').toLowerCase(), _displayName: tagName || n.name || n.public_key.slice(0, 12) + '...' };
            }).sort((a, b) => a._sortName.localeCompare(b._sortName));

            const enabledObserverKeys = sortedNodes
                .filter(n => !disabledObservers.has(n.public_key))
                .map(n => n.public_key);
            // Only constrain when some current observer is actually hidden (a stale
            // disabled key that no longer matches a node should not filter anything).
            const observerFilterActive = enabledObserverKeys.length < sortedNodes.length;

            const onObserverToggle = (pubkey) => {
                disabledObservers = toggleObserver(pubkey, sortedNodes.length);
                if (page > 1) {
                    // Re-scoping the data invalidates the current page; reset to page 1.
                    const sp = new URLSearchParams(window.location.search);
                    sp.delete('page');
                    const qs = sp.toString();
                    navigate(qs ? `/messages?${qs}` : '/messages');
                } else {
                    fetchAndRenderData();
                }
            };

            // Phase 2: fetch the messages with the resolved observer filter.
            const apiParams = { limit, offset, message_type, channel_idx, sort, order };
            if (observerFilterActive) apiParams.observed_by = enabledObserverKeys;
            if (includeSpam) apiParams.include_spam = true;
            const data = await apiGet('/api/v1/messages', apiParams, { signal });
            const messages = dedupeBySignature(data.items || []);
            const total = data.total || 0;
            const totalPages = Math.ceil(total / limit);

            const observerBadges = (extraClass) => observerFilterBadges({
                nodes: sortedNodes, disabled: disabledObservers, onToggle: onObserverToggle, extraClass,
            });

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
                        receiversBlock = observerIcons(msg.observers);
                    } else if (msg.observed_by) {
                        receiversBlock = html`<span class="opacity-50 text-xs">\u{1F4E1}</span>`;
                    }
                    const detailUrl = packetDetailUrl(msg.packet_hash);
                    return html`<div class="card bg-base-100 shadow-sm ${detailUrl ? 'cursor-pointer' : ''}"
                @click=${detailUrl ? () => navigate(detailUrl) : undefined}>
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
                            <div class="text-xs opacity-60 flex items-center gap-1">
                                ${formatDateTimeShort(msg.received_at)}
                                ${spamBadge(msg)}
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
                    if (msg.observers && msg.observers.length >= 1) {
                        receiversBlock = html`${observerIcons(msg.observers)}`;
                    } else if (msg.observed_by) {
                        receiversBlock = html`<span class="opacity-50">\u{1F4E1}</span>`;
                    } else {
                        receiversBlock = html`<span class="opacity-50">-</span>`;
                    }
                    const detailUrl = packetDetailUrl(msg.packet_hash);
                    return html`<tr class="${detailUrl ? 'hover cursor-pointer' : ''}"
                    @click=${detailUrl ? () => navigate(detailUrl) : undefined}>
                    <td class="text-lg" title=${typeTitle}>${typeIcon}</td>
                    <td class="text-sm whitespace-nowrap">${formatDateTime(msg.received_at)}</td>
                    <td class="text-sm whitespace-nowrap">
                        <div>${fromPrimary}</div>
                    </td>
                    <td class="break-words max-w-md" style="white-space: pre-wrap;">
                        <div class="flex items-start gap-2">
                            <span>${displayMessage}</span>
                            ${spamBadge(msg)}
                        </div>
                    </td>
                    <td>${receiversBlock}</td>
                </tr>`;
                });

            const spamParam = includeSpam ? { include_spam: 'true' } : {};
            const paginationBlock = pagination(page, totalPages, '/messages', {
                message_type, channel_idx, limit, sort, order, ...spamParam,
            });

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
            if (spamEnabled) {
                filterFields.push(() => html`
            <div class="flex flex-col gap-1">
                <label class="flex items-center py-1">
                    <span class="opacity-80 text-sm">${t('messages.spam.filter_label')}</span>
                </label>
                <label class="label cursor-pointer justify-start gap-2 py-1">
                    <input type="checkbox" name="include_spam" value="true"
                           class="checkbox checkbox-sm" ?checked=${includeSpam}
                           @change=${autoSubmit} />
                    <span class="text-sm">${t('messages.spam.show')}</span>
                </label>
            </div>`);
            }
            const hasActiveFilters = message_type !== '' || channel_idx !== '' || includeSpam;
            const existingDetails = container.querySelector('details.collapse');
            const isFilterOpen = existingDetails ? existingDetails.open : hasActiveFilters;

            const filterCard = renderFilterCard({
                fields: filterFields,
                basePath: '/messages',
                navigate,
                collapsible: true,
                defaultOpen: isFilterOpen,
            });

            const headerParams = { message_type, channel_idx, limit, ...spamParam };
            const sortable = (label, sortKey) => sortableTableHeader(label, {
                sortKey, currentSort: sort, currentOrder: order,
                navigate, basePath: '/messages', params: headerParams,
            });

            renderPage(html`${filterCard}

${observerBadges('hidden lg:flex mb-4')}

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

${observerBadges('flex lg:hidden mb-4')}

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
            if (isAbortError(e)) return;
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
