import { useState, useCallback, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { IconChevronRight } from "@/components/icons";

function primitiveClass(val: unknown): string {
  if (val === null) return "italic opacity-50";
  switch (typeof val) {
    case "string":
      return "text-success";
    case "number":
      return "text-warning";
    case "boolean":
      return "text-info";
    default:
      return "";
  }
}

function formatPrimitive(val: unknown): string {
  if (val === null) return "null";
  if (typeof val === "string") return `"${val}"`;
  return String(val);
}

function KeyLabel({ k }: { k: string | number | null }) {
  if (k === null) return null;
  if (typeof k === "number") {
    return <span className="text-primary/50">{k}:</span>;
  }
  return <span className="text-primary/70">"{k}":</span>;
}

function JsonNode({
  value,
  k,
  depth,
  openDepth,
  expandSignal,
}: {
  value: unknown;
  k: string | number | null;
  depth: number;
  openDepth: number;
  expandSignal: boolean | null;
}) {
  const [expanded, setExpanded] = useState(depth < openDepth);

  const isExpanded = expandSignal !== null ? expandSignal : expanded;
  const isContainer = value !== null && typeof value === "object";

  if (!isContainer) {
    return (
      <div className="flex gap-2 py-0.5">
        <KeyLabel k={k} />
        <span className={primitiveClass(value)}>
          {formatPrimitive(value)}
        </span>
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries: [string | number, unknown][] = isArray
    ? (value as unknown[]).map((v, i) => [i, v])
    : Object.entries(value as Record<string, unknown>);
  const open = isArray ? "[" : "{";
  const close = isArray ? "]" : "}";

  if (entries.length === 0) {
    return (
      <div className="flex gap-2 py-0.5">
        <KeyLabel k={k} />
        <span className="opacity-60">
          {open}
          {close}
        </span>
      </div>
    );
  }

  return (
    <div className="json-node">
      <button
        type="button"
        className="json-toggle inline-flex items-center gap-1 hover:opacity-70"
        onClick={() => setExpanded(!isExpanded)}
      >
        <span
          className={`json-caret inline-block transition-transform ${isExpanded ? "rotate-90" : ""}`}
        >
          <IconChevronRight className="h-3 w-3" />
        </span>
        <KeyLabel k={k} />
        <span className="opacity-50 text-[10px]">
          {open}
          {entries.length}
          {close}
        </span>
      </button>
      <div
        className={`json-children ml-2 border-l border-base-200 pl-2 ${isExpanded ? "" : "hidden"}`}
      >
        {entries.map(([ek, ev]) => (
          <JsonNode
            key={ek}
            value={ev}
            k={ek}
            depth={depth + 1}
            openDepth={openDepth}
            expandSignal={expandSignal}
          />
        ))}
      </div>
    </div>
  );
}

export function JsonTree({
  value,
  openDepth = 1,
}: {
  value: unknown;
  openDepth?: number;
}) {
  const { t } = useTranslation();
  const [expandSignal, setExpandSignal] = useState<boolean | null>(null);

  const expandAll = useCallback(() => setExpandSignal(true), []);
  const collapseAll = useCallback(() => setExpandSignal(false), []);

  return (
    <div className="json-tree-root font-mono text-xs">
      <div className="flex items-center gap-2 mb-2">
        <button type="button" className="btn btn-xs btn-ghost" onClick={expandAll}>
          {t("packets.expand_all")}
        </button>
        <button
          type="button"
          className="btn btn-xs btn-ghost"
          onClick={collapseAll}
        >
          {t("packets.collapse_all")}
        </button>
      </div>
      <div className="overflow-x-auto">
        <JsonNode
          value={value}
          k={null}
          depth={0}
          openDepth={openDepth}
          expandSignal={expandSignal}
        />
      </div>
    </div>
  );
}
