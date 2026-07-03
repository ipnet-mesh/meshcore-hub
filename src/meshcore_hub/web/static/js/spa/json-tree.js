/**
 * MeshCore Hub SPA - JSON Tree
 *
 * Renders an arbitrary JSON value as an expandable/collapsible tree.
 * Imperative toggling (class flips): the host page renders once after load,
 * so no re-render loop is required.
 */
import { html, nothing } from 'lit-html';
import { t } from './components.js';
import { iconChevronRight } from './icons.js';

function toggleNode(e) {
    const btn = e.currentTarget;
    const children = btn.nextElementSibling;
    if (!children) return;
    const nowHidden = children.classList.toggle('hidden');
    btn.querySelector('.json-caret').classList.toggle('rotate-90', !nowHidden);
}

function expandAll(e) {
    const root = e.currentTarget.closest('.json-tree-root');
    if (!root) return;
    root.querySelectorAll('.json-children').forEach((el) => el.classList.remove('hidden'));
    root.querySelectorAll('.json-caret').forEach((el) => el.classList.add('rotate-90'));
}

function collapseAll(e) {
    const root = e.currentTarget.closest('.json-tree-root');
    if (!root) return;
    root.querySelectorAll('.json-children').forEach((el) => el.classList.add('hidden'));
    root.querySelectorAll('.json-caret').forEach((el) => el.classList.remove('rotate-90'));
}

function primitiveClass(val) {
    if (val === null) return 'italic opacity-50';
    switch (typeof val) {
        case 'string': return 'text-success';
        case 'number': return 'text-warning';
        case 'boolean': return 'text-info';
        default: return '';
    }
}

function formatPrimitive(val) {
    if (val === null) return 'null';
    if (typeof val === 'string') return `"${val}"`;
    return String(val);
}

function keyLabel(key) {
    if (key == null) return nothing;
    if (typeof key === 'number') {
        return html`<span class="text-primary/50">${key}:</span>`;
    }
    return html`<span class="text-primary/70">"${key}":</span>`;
}

function renderNode(value, key, depth, openDepth) {
    const isContainer = value !== null && typeof value === 'object';

    if (!isContainer) {
        return html`
        <div class="flex gap-2 py-0.5">
            ${keyLabel(key)}
            <span class=${primitiveClass(value)}>${formatPrimitive(value)}</span>
        </div>`;
    }

    const isArray = Array.isArray(value);
    const entries = isArray
        ? value.map((v, i) => [i, v])
        : Object.entries(value);
    const open = isArray ? '[' : '{';
    const close = isArray ? ']' : '}';
    const hint = isArray ? `${entries.length}` : `${entries.length}`;

    if (entries.length === 0) {
        return html`
        <div class="flex gap-2 py-0.5">
            ${keyLabel(key)}
            <span class="opacity-60">${open}${close}</span>
        </div>`;
    }

    const isExpanded = depth < openDepth;

    return html`
    <div class="json-node">
        <button type="button" class="json-toggle inline-flex items-center gap-1 hover:opacity-70" @click=${toggleNode}>
            <span class="json-caret inline-block transition-transform ${isExpanded ? 'rotate-90' : ''}">${iconChevronRight('h-3 w-3')}</span>
            ${keyLabel(key)}
            <span class="opacity-50 text-[10px]">${open}${hint}${close}</span>
        </button>
        <div class="json-children ml-2 border-l border-base-200 pl-2 ${isExpanded ? '' : 'hidden'}">
            ${entries.map(([k, v]) => renderNode(v, k, depth + 1, openDepth))}
        </div>
    </div>`;
}

export function jsonTree(value, { openDepth = 1 } = {}) {
    return html`
    <div class="json-tree-root font-mono text-xs">
        <div class="flex items-center gap-2 mb-2">
            <button type="button" class="btn btn-xs btn-ghost" @click=${expandAll}>${t('packets.expand_all')}</button>
            <button type="button" class="btn btn-xs btn-ghost" @click=${collapseAll}>${t('packets.collapse_all')}</button>
        </div>
        <div class="overflow-x-auto">
            ${renderNode(value, null, 0, openDepth)}
        </div>
    </div>`;
}
