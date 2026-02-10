import { apiGet } from '../api.js';
import {
    html, litRender, nothing,
    formatRelativeTime, formatDateTime, errorAlert,
} from '../components.js';
import { iconInfo } from '../icons.js';

function nodeTypeEmoji(advType) {
    switch ((advType || '').toLowerCase()) {
        case 'chat': return '\u{1F4AC}';
        case 'repeater': return '\u{1F4E1}';
        case 'room': return '\u{1FAA7}';
        default: return advType ? '\u{1F4CD}' : '\u{1F4E6}';
    }
}

function nodeSortKey(node) {
    const t = (node.adv_type || '').toLowerCase();
    if (t === 'repeater') return 0;
    if (t === 'chat') return 1;
    return 2;
}

function renderNodeCard(node) {
    const tagName = node.tags ? (node.tags.find(t => t.key === 'name') || {}).value : null;
    const displayName = tagName || node.name;
    const emoji = nodeTypeEmoji(node.adv_type);
    const relTime = formatRelativeTime(node.last_seen);
    const fullTime = formatDateTime(node.last_seen);

    const nameBlock = displayName
        ? html`<div class="font-medium text-sm">${displayName}</div>
               <div class="font-mono text-xs opacity-60">${node.public_key.slice(0, 12)}...</div>`
        : html`<div class="font-mono text-sm">${node.public_key.slice(0, 12)}...</div>`;

    const timeBlock = node.last_seen
        ? html`<time class="text-xs opacity-60 whitespace-nowrap" datetime=${node.last_seen} title=${fullTime} data-relative-time>${relTime}</time>`
        : nothing;

    return html`<a href="/nodes/${node.public_key}" class="flex items-center gap-3 p-2 bg-base-200 rounded-lg hover:bg-base-300 transition-colors">
        <span class="text-lg" title=${node.adv_type || 'Unknown'}>${emoji}</span>
        <div class="flex-1 min-w-0">
            ${nameBlock}
        </div>
        ${timeBlock}
    </a>`;
}

function renderMemberCard(member, nodes) {
    const sorted = [...nodes].sort((a, b) => nodeSortKey(a) - nodeSortKey(b));
    const nodesBlock = sorted.length > 0
        ? html`<div class="mt-4 space-y-2">${sorted.map(renderNodeCard)}</div>`
        : nothing;

    const callsignBadge = member.callsign
        ? html`<span class="badge badge-neutral">${member.callsign}</span>`
        : nothing;

    const descBlock = member.description
        ? html`<p class="mt-2">${member.description}</p>`
        : nothing;

    const contactBlock = member.contact
        ? html`<p class="text-sm mt-2"><span class="opacity-70">Contact:</span> ${member.contact}</p>`
        : nothing;

    return html`<div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">
                ${member.name}
                ${callsignBadge}
            </h2>
            ${descBlock}
            ${contactBlock}
            ${nodesBlock}
        </div>
    </div>`;
}

export async function render(container, params, router) {
    try {
        const membersResp = await apiGet('/api/v1/members', { limit: 100 });
        const members = membersResp.items || [];

        if (members.length === 0) {
            litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">Members</h1>
    <span class="badge badge-lg">0 members</span>
</div>

<div class="alert alert-info">
    ${iconInfo('stroke-current shrink-0 h-6 w-6')}
    <div>
        <h3 class="font-bold">No members configured</h3>
        <p class="text-sm">To display network members, create a members.yaml file in your seed directory.</p>
    </div>
</div>

<div class="mt-6 card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title">Members File Format</h2>
        <p class="mb-4">Create a YAML file at <code>$SEED_HOME/members.yaml</code> with the following structure:</p>
        <pre class="bg-base-200 p-4 rounded-box text-sm overflow-x-auto"><code>members:
  - member_id: johndoe
    name: John Doe
    callsign: AB1CD
    role: Network Admin
    description: Manages the main repeater node.
    contact: john@example.com
  - member_id: janesmith
    name: Jane Smith
    role: Member
    description: Regular user in the downtown area.</code></pre>
        <p class="mt-4 text-sm opacity-70">
            Run <code>meshcore-hub collector seed</code> to import members.<br/>
            To associate nodes with members, add a <code>member_id</code> tag to nodes in <code>node_tags.yaml</code>.
        </p>
    </div>
</div>`, container);
            return;
        }

        const nodePromises = members.map(m =>
            apiGet('/api/v1/nodes', { member_id: m.member_id, limit: 50 })
                .then(resp => ({ memberId: m.member_id, nodes: resp.items || [] }))
                .catch(() => ({ memberId: m.member_id, nodes: [] }))
        );
        const nodeResults = await Promise.all(nodePromises);

        const nodesByMember = {};
        for (const r of nodeResults) {
            nodesByMember[r.memberId] = r.nodes;
        }

        const cards = members.map(m =>
            renderMemberCard(m, nodesByMember[m.member_id] || [])
        );

        litRender(html`
<div class="flex items-center justify-between mb-6">
    <h1 class="text-3xl font-bold">Members</h1>
    <span class="badge badge-lg">${members.length} members</span>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-start">
    ${cards}
</div>`, container);

    } catch (e) {
        litRender(errorAlert(e.message || 'Failed to load members'), container);
    }
}
