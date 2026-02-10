import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    getConfig, formatDateTime, formatDateTimeShort,
    truncateKey, errorAlert,
    pagination, timezoneIndicator,
    createFilterHandler, autoSubmit, submitOnEnter
} from '../components.js';

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

    function renderPage(content, { total = null } = {}) {
        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">Messages</h1>
    <div class="flex items-center gap-2">
        ${tzBadge}
        ${total !== null ? html`<span class="badge badge-lg">${total} total</span>` : nothing}
    </div>
</div>
${content}`, container);
    }

    // Render page header immediately (old content stays visible until data loads)
    renderPage(nothing);

    try {
        const data = await apiGet('/api/v1/messages', { limit, offset, message_type });
        const messages = data.items || [];
        const total = data.total || 0;
        const totalPages = Math.ceil(total / limit);

        const mobileCards = messages.length === 0
            ? html`<div class="text-center py-8 opacity-70">No messages found.</div>`
            : messages.map(msg => {
                const isChannel = msg.message_type === 'channel';
                const typeIcon = isChannel ? '\u{1F4FB}' : '\u{1F464}';
                const typeTitle = isChannel ? 'Channel' : 'Contact';
                let senderBlock;
                if (isChannel) {
                    senderBlock = html`<span class="opacity-60">Public</span>`;
                } else {
                    const senderName = msg.sender_tag_name || msg.sender_name;
                    if (senderName) {
                        senderBlock = senderName;
                    } else {
                        senderBlock = html`<span class="font-mono text-xs">${(msg.pubkey_prefix || '-').slice(0, 12)}</span>`;
                    }
                }
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
                            ${senderBlock}
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
            <p class="text-sm mt-2 break-words whitespace-pre-wrap">${msg.text || '-'}</p>
        </div>
    </div>`;
            });

        const tableRows = messages.length === 0
            ? html`<tr><td colspan="5" class="text-center py-8 opacity-70">No messages found.</td></tr>`
            : messages.map(msg => {
                const isChannel = msg.message_type === 'channel';
                const typeIcon = isChannel ? '\u{1F4FB}' : '\u{1F464}';
                const typeTitle = isChannel ? 'Channel' : 'Contact';
                let senderBlock;
                if (isChannel) {
                    senderBlock = html`<span class="opacity-60">Public</span>`;
                } else {
                    const senderName = msg.sender_tag_name || msg.sender_name;
                    if (senderName) {
                        senderBlock = html`<span class="font-medium">${senderName}</span>`;
                    } else {
                        senderBlock = html`<span class="font-mono text-xs">${(msg.pubkey_prefix || '-').slice(0, 12)}</span>`;
                    }
                }
                let receiversBlock;
                if (msg.receivers && msg.receivers.length >= 1) {
                    receiversBlock = html`<div class="flex gap-1">
                        ${msg.receivers.map(recv => {
                            const recvName = recv.tag_name || recv.name || truncateKey(recv.public_key, 12);
                            return html`<a href="/nodes/${recv.public_key}" class="text-lg hover:opacity-70" data-receiver-tooltip data-name=${recvName} data-timestamp=${recv.received_at || ''}>\u{1F4E1}</a>`;
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
                <td class="text-sm whitespace-nowrap">${senderBlock}</td>
                <td class="break-words max-w-md" style="white-space: pre-wrap;">${msg.text || '-'}</td>
                <td>${receiversBlock}</td>
            </tr>`;
            });

        const paginationBlock = pagination(page, totalPages, '/messages', {
            message_type, limit,
        });

        renderPage(html`
<div class="card bg-base-100 shadow mb-6">
    <div class="card-body py-4">
        <form method="GET" action="/messages" class="flex gap-4 flex-wrap items-end" @submit=${createFilterHandler('/messages', navigate)}>
            <div class="form-control">
                <label class="label py-1">
                    <span class="label-text">Type</span>
                </label>
                <select name="message_type" class="select select-bordered select-sm" @change=${autoSubmit}>
                    <option value="">All Types</option>
                    <option value="contact" ?selected=${message_type === 'contact'}>Direct</option>
                    <option value="channel" ?selected=${message_type === 'channel'}>Channel</option>
                </select>
            </div>
            <div class="flex gap-2 w-full sm:w-auto">
                <button type="submit" class="btn btn-primary btn-sm">Filter</button>
                <a href="/messages" class="btn btn-ghost btn-sm">Clear</a>
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
                <th>Type</th>
                <th>Time</th>
                <th>From</th>
                <th>Message</th>
                <th>Receivers</th>
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
