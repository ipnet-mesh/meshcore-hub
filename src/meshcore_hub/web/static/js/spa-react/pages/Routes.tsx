import {
  Fragment,
  useCallback,
  useEffect,
  useRef,
  useState,
  type SVGProps,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { useAppConfig, hasRole } from "@/context/AppConfigContext";
import { apiGet, apiPost, apiPut, apiDelete } from "@/utils/api";
import { usePageTitle } from "@/hooks/usePageTitle";
import { Loading, ErrorAlert } from "@/components/Alerts";
import {
  IconClock,
  IconEdit,
  IconNodes,
  IconPackets,
  IconPath,
  IconPlus,
  IconRuler,
  IconSatelliteDish,
  IconTrash,
} from "@/components/icons";

interface RouteResultInfo {
  quality?: string | null;
  state?: string | null;
  matched_count?: number | null;
  threshold?: number | null;
  effective_clear?: number | null;
}

interface RouteNodeInfo {
  node_id?: string | null;
  public_key?: string | null;
  name?: string | null;
  expected_hash?: string | null;
}

interface RouteObserverInfo {
  public_key?: string | null;
  name?: string | null;
}

interface RouteItem {
  id: string;
  from_label?: string | null;
  to_label?: string | null;
  description?: string | null;
  visibility?: string | null;
  enabled: boolean;
  reversible?: boolean | null;
  match_width?: number | null;
  window_hours?: number | null;
  packet_count_threshold?: number | null;
  clear_threshold?: number | null;
  max_hop_span?: number | null;
  max_path_length?: number | null;
  quality_avg?: string | null;
  route_result?: RouteResultInfo | null;
  route_nodes?: RouteNodeInfo[];
  route_observers?: RouteObserverInfo[];
}

interface RouteListResponse {
  items: RouteItem[];
}

interface MatchHop {
  node_hash?: string | null;
}

interface RouteMatch {
  packet_hash?: string | null;
  received_at?: string | null;
  hops?: MatchHop[];
}

interface RouteDetail {
  recent_matches?: RouteMatch[];
}

interface HistoryDay {
  date: string;
  quality?: string | null;
  matched_count?: number | null;
}

interface RouteHistory {
  data?: HistoryDay[];
}

interface NodeSearchResult {
  public_key: string;
  name?: string | null;
  adv_type?: string | null;
}

interface NodeListResponse {
  items: NodeSearchResult[];
}

interface SelectedNode {
  public_key: string;
  name?: string | null;
}

interface ChartInstance {
  destroy: () => void;
}

interface ModalState {
  type: "add" | "edit" | "delete";
  route: RouteItem | null;
  pathNodes: SelectedNode[];
  observerNodes: SelectedNode[];
  pathResults: NodeSearchResult[];
  obsResults: NodeSearchResult[];
  saving: boolean;
}

interface RouteFormValues {
  from_label: string;
  to_label: string;
  description: string;
  visibility: string;
  match_width: number;
  window_hours: string;
  packet_count_threshold: string;
  clear_threshold: string;
  max_hop_span: string;
  max_path_length: string;
  enabled: boolean;
  reversible: boolean;
}

type MatchEntry =
  | { kind: "hop"; hop: MatchHop }
  | { kind: "ellipsis"; hidden: number };

type TranslateFn = ReturnType<typeof useTranslation>["t"];

const VISIBILITY_ORDER = ["community", "member", "operator", "admin"];
const PATH_MAX = 5;
const PATH_HEAD = 2;
const PATH_TAIL = 2;

function qualityOf(route: RouteItem): string {
  return route.quality_avg || route.route_result?.quality || "unknown";
}

function qualityBadgeClass(quality: string, enabled: boolean): string {
  if (!enabled) return "badge-neutral";
  const map: Record<string, string> = {
    clear: "badge-success",
    marginal: "badge-warning",
    failing: "badge-error",
    no_coverage: "badge-info",
    unknown: "badge-ghost",
  };
  return map[quality] || "badge-ghost";
}

function qualityLabel(
  quality: string,
  enabled: boolean,
  t: TranslateFn,
): string {
  if (!enabled) return t("routes.disabled");
  const map: Record<string, string> = {
    clear: t("routes.quality_clear"),
    marginal: t("routes.quality_marginal"),
    failing: t("routes.quality_failing"),
    no_coverage: t("routes.quality_no_coverage"),
    unknown: t("routes.quality_unknown"),
  };
  return map[quality] || quality || t("routes.quality_unknown");
}

function qualityDot(quality: string, enabled: boolean): string {
  if (!enabled) return "\u25CC";
  const dots: Record<string, string> = {
    clear: "\u25CF",
    marginal: "\u25CF",
    failing: "\u25CF",
    no_coverage: "\u25D0",
    unknown: "\u25D0",
  };
  return dots[quality] || "\u25D0";
}

function diagnosisText(route: RouteItem, t: TranslateFn): string {
  const result = route.route_result;
  if (!result || !route.enabled) return "";
  if (result.state === "healthy") return t("routes.diagnosis_healthy");
  if (result.state === "unhealthy") return t("routes.diagnosis_unhealthy");
  if (result.state === "no_coverage") return t("routes.diagnosis_no_coverage");
  return "";
}

function IconRouteFrom(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      className="h-5 w-5"
      {...props}
    >
      <circle cx="5" cy="12" r="2.5" strokeWidth={2} />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7.5 12H21m0 0l-4-4m4 4l-4 4"
      />
    </svg>
  );
}

function IconRouteTo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      className="h-5 w-5"
      {...props}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 12h13.5m0 0l-4-4m4 4l-4 4"
      />
      <circle cx="19" cy="12" r="2.5" strokeWidth={2} />
    </svg>
  );
}

function SummaryStrip({ routes }: { routes: RouteItem[] }) {
  const { t } = useTranslation();
  const counts = { clear: 0, marginal: 0, failing: 0, no_coverage: 0, disabled: 0 };
  for (const r of routes) {
    if (!r.enabled) {
      counts.disabled++;
      continue;
    }
    const q = qualityOf(r);
    if (q === "clear") counts.clear++;
    else if (q === "marginal") counts.marginal++;
    else if (q === "failing") counts.failing++;
    else counts.no_coverage++;
  }
  return (
    <div className="flex flex-wrap gap-4 mb-6 text-sm">
      <span className="flex items-center gap-1">
        <span className="text-success">{"\u25CF"}</span> {counts.clear}{" "}
        {t("routes.quality_clear")}
      </span>
      <span className="flex items-center gap-1">
        <span className="text-warning">{"\u25CF"}</span> {counts.marginal}{" "}
        {t("routes.quality_marginal")}
      </span>
      <span className="flex items-center gap-1">
        <span className="text-error">{"\u25CF"}</span> {counts.failing}{" "}
        {t("routes.quality_failing")}
      </span>
      <span className="flex items-center gap-1">
        <span className="text-info">{"\u25D0"}</span> {counts.no_coverage}{" "}
        {t("routes.quality_no_coverage")}
      </span>
      <span className="flex items-center gap-1 opacity-50">
        {"\u25CC"} {counts.disabled} {t("routes.disabled")}
      </span>
    </div>
  );
}

function PathChips({ route }: { route: RouteItem }) {
  const nodes = route.route_nodes || [];
  const arrow = route.reversible !== false ? "\u2194" : "\u2192";
  const prefixLen = 2 * (route.match_width || 1);
  return (
    <div className="flex flex-wrap items-center gap-1 text-sm">
      {nodes.map((rn, i) => (
        <Fragment key={rn.node_id || rn.public_key || i}>
          {i > 0 && <span className="opacity-50">{arrow}</span>}
          <span className="badge badge-ghost badge-sm">
            {rn.name
              ? `${rn.name} (${rn.public_key?.slice(0, prefixLen)})`
              : rn.public_key?.slice(0, prefixLen) || rn.node_id?.slice(0, 8)}
          </span>
        </Fragment>
      ))}
    </div>
  );
}

function StatsRow({ route }: { route: RouteItem }) {
  const { t } = useTranslation();
  const result = route.route_result;
  const matched = result?.matched_count ?? "?";
  const threshold = result?.threshold ?? "?";
  const degraded = result?.effective_clear ?? "?";
  const nodeCount = (route.route_nodes || []).length;
  const obsCount = (route.route_observers || []).length;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs opacity-60 mt-1">
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_matched_tip")}
      >
        <IconPackets className="h-3.5 w-3.5" />
        <span>
          {matched}/{threshold}
          {"\u2192"}
          {degraded}
        </span>
      </span>
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_window_tip")}
      >
        <IconClock className="h-3.5 w-3.5" />
        <span>{route.window_hours}h</span>
      </span>
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_width_tip")}
      >
        <IconRuler className="h-3.5 w-3.5" />
        <span>{route.match_width}B</span>
      </span>
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_nodes_tip")}
      >
        <IconNodes className="h-3.5 w-3.5" />
        <span>{nodeCount}</span>
      </span>
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_span_tip")}
      >
        <IconPath className="h-3.5 w-3.5" />
        <span>{route.max_hop_span || "\u221E"}</span>
      </span>
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_length_tip")}
      >
        <IconRuler className="h-3.5 w-3.5" />
        <span>{route.max_path_length || "\u221E"}</span>
      </span>
      <span
        className="inline-flex items-center gap-1 tooltip tooltip-top"
        data-tip={t("routes.stats_observers_tip")}
      >
        <IconSatelliteDish className="h-3.5 w-3.5" />
        <span>{obsCount || "\u221E"}</span>
      </span>
    </div>
  );
}

function MatchRow({
  match,
  route,
  packetsEnabled,
  onNavigate,
}: {
  match: RouteMatch;
  route: RouteItem;
  packetsEnabled: boolean;
  onNavigate: (url: string) => void;
}) {
  const { t } = useTranslation();
  const prefixLen = 2 * (route.match_width || 1);
  const pathLookup = new Map(
    (route.route_nodes || []).map((rn) => [
      (rn.expected_hash || "").toLowerCase(),
      rn,
    ]),
  );
  const detailUrl =
    packetsEnabled && match.packet_hash
      ? `/packets/hash/${match.packet_hash}`
      : null;
  const hops = match.hops || [];
  const entries: MatchEntry[] = [];
  if (hops.length > PATH_MAX) {
    const hidden = hops.length - PATH_HEAD - PATH_TAIL;
    for (const h of hops.slice(0, PATH_HEAD)) entries.push({ kind: "hop", hop: h });
    entries.push({ kind: "ellipsis", hidden });
    for (const h of hops.slice(-PATH_TAIL)) entries.push({ kind: "hop", hop: h });
  } else {
    for (const h of hops) entries.push({ kind: "hop", hop: h });
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-0.5 text-xs pb-1 border-b border-base-300 last:border-0 ${
        detailUrl
          ? "hover:bg-base-200 cursor-pointer -mx-1 px-1 rounded transition-colors"
          : ""
      }`}
      onClick={
        detailUrl
          ? (e) => {
              e.stopPropagation();
              onNavigate(detailUrl);
            }
          : undefined
      }
    >
      {entries.map((entry, i) => {
        if (entry.kind === "ellipsis") {
          return (
            <Fragment key={i}>
              {i > 0 && <span className="opacity-30 mx-0.5">{"\u2192"}</span>}
              <span
                className="badge badge-ghost badge-sm cursor-help"
                title={t("packets.hops_hidden", { count: entry.hidden })}
              >
                {"\u2026"}
              </span>
            </Fragment>
          );
        }
        const hash = (entry.hop.node_hash || "").toLowerCase();
        const inPath = pathLookup.has(hash.slice(0, prefixLen));
        return (
          <Fragment key={i}>
            {i > 0 && <span className="opacity-30 mx-0.5">{"\u2192"}</span>}
            {inPath ? (
              <span className="badge badge-primary badge-sm">{hash}</span>
            ) : (
              <span className="badge badge-ghost badge-sm opacity-50">{hash}</span>
            )}
          </Fragment>
        );
      })}
      {match.received_at && (
        <span className="ml-auto opacity-40 whitespace-nowrap">
          {new Date(match.received_at).toLocaleString()}
        </span>
      )}
    </div>
  );
}

function DetailContent({
  route,
  detail,
  history,
  packetsEnabled,
  onNavigate,
}: {
  route: RouteItem;
  detail: RouteDetail;
  history: RouteHistory | undefined;
  packetsEnabled: boolean;
  onNavigate: (url: string) => void;
}) {
  const { t } = useTranslation();
  const matches = detail.recent_matches || [];
  const historyData = history?.data ?? [];

  return (
    <div className="mt-2 space-y-3 text-sm">
      {history && (
        <div className="mb-3">
          <div style={{ height: "40px" }}>
            <canvas id={`routeStripChart-${route.id}`}></canvas>
          </div>
          {historyData.length > 0 && (
            <div className="flex text-xs opacity-50 mt-0.5">
              {historyData.map((d, i) => (
                <span key={d.date} className="flex-1 text-center">
                  {i === historyData.length - 1
                    ? t("routes.last_n_hours", { n: route.window_hours })
                    : new Date(`${d.date}T00:00:00`).toLocaleDateString(
                        undefined,
                        { day: "2-digit", month: "2-digit" },
                      )}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {matches.length > 0 && (
        <div>
          <strong className="opacity-70">{t("routes.recent_packets")}</strong>
          <div className="mt-2 space-y-2">
            {matches.map((m, i) => (
              <MatchRow
                key={`${m.packet_hash || "match"}-${i}`}
                match={m}
                route={route}
                packetsEnabled={packetsEnabled}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RouteCard({
  route,
  detail,
  history,
  isAdmin,
  packetsEnabled,
  onEdit,
  onDelete,
  onNavigate,
}: {
  route: RouteItem;
  detail: RouteDetail | undefined;
  history: RouteHistory | undefined;
  isAdmin: boolean;
  packetsEnabled: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onNavigate: (url: string) => void;
}) {
  const { t } = useTranslation();
  const q = qualityOf(route);
  const badgeCls = qualityBadgeClass(q, route.enabled);
  const label = qualityLabel(q, route.enabled, t);
  const dot = qualityDot(q, route.enabled);
  const tip = diagnosisText(route, t);

  return (
    <div className="card bg-base-100 shadow-xl h-full">
      <div className="card-body">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h2 className="card-title">
              <div className="grid grid-cols-[auto_1fr] gap-x-2 items-center min-w-0">
                <span className="flex items-center text-base-content/60">
                  <IconRouteFrom className="h-5 w-5" />
                </span>
                <span className="truncate" title={route.from_label || ""}>
                  {route.from_label}
                </span>
                <span className="flex items-center text-base-content/60">
                  <IconRouteTo className="h-5 w-5" />
                </span>
                <span className="truncate" title={route.to_label || ""}>
                  {route.to_label}
                </span>
              </div>
            </h2>
            {route.description && (
              <p className="text-sm opacity-70 mt-1">{route.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {tip ? (
              <span
                className={`badge ${badgeCls} badge-sm tooltip tooltip-left`}
                data-tip={tip}
              >
                {dot} {label}
              </span>
            ) : (
              <span className={`badge ${badgeCls} badge-sm`}>
                {dot} {label}
              </span>
            )}
          </div>
        </div>
        <div className="mt-2">
          <PathChips route={route} />
        </div>
        <StatsRow route={route} />
        {detail ? (
          <DetailContent
            route={route}
            detail={detail}
            history={history}
            packetsEnabled={packetsEnabled}
            onNavigate={onNavigate}
          />
        ) : (
          <div className="mt-4 pt-4 border-t border-base-300 flex justify-center">
            <span className="loading loading-spinner loading-sm opacity-50"></span>
          </div>
        )}
        {isAdmin && (
          <div className="flex gap-2 mt-auto pt-2">
            <button className="btn btn-xs btn-outline" onClick={onEdit}>
              <IconEdit className="h-3 w-3" /> {t("common.edit")}
            </button>
            <button
              className="btn btn-xs btn-outline btn-error"
              onClick={onDelete}
            >
              <IconTrash className="h-3 w-3" /> {t("common.delete")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function NodeSearchResultRow({
  node,
  onSelect,
}: {
  node: NodeSearchResult;
  onSelect: () => void;
}) {
  const name = node.name || `${node.public_key.slice(0, 12)}\u2026`;
  return (
    <li>
      <button
        type="button"
        className="w-full text-left flex items-center gap-2"
        onClick={onSelect}
      >
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-medium truncate">{name}</span>
          <span className="block text-xs opacity-50 font-mono truncate">
            {node.public_key}
          </span>
        </span>
        {node.adv_type && (
          <span className="badge badge-ghost badge-xs">{node.adv_type}</span>
        )}
      </button>
    </li>
  );
}

interface RouteModalProps {
  route: RouteItem | null;
  isEdit: boolean;
  pathNodes: SelectedNode[];
  observerNodes: SelectedNode[];
  pathResults: NodeSearchResult[];
  obsResults: NodeSearchResult[];
  saving: boolean;
  onPathSearch: (query: string) => void;
  onPathSelect: (node: NodeSearchResult) => void;
  onPathRemove: (index: number) => void;
  onPathMove: (index: number, dir: number) => void;
  onPathEnter: (query: string) => void;
  onObsSearch: (query: string) => void;
  onObsSelect: (node: NodeSearchResult) => void;
  onObsRemove: (index: number) => void;
  onObsEnter: (query: string) => void;
  onSubmit: (values: RouteFormValues) => void;
  onCancel: () => void;
}

function RouteModal({
  route,
  isEdit,
  pathNodes,
  observerNodes,
  pathResults,
  obsResults,
  saving,
  onPathSearch,
  onPathSelect,
  onPathRemove,
  onPathMove,
  onPathEnter,
  onObsSearch,
  onObsSelect,
  onObsRemove,
  onObsEnter,
  onSubmit,
  onCancel,
}: RouteModalProps) {
  const { t } = useTranslation();
  const [fromLabel, setFromLabel] = useState(route?.from_label ?? "");
  const [toLabel, setToLabel] = useState(route?.to_label ?? "");
  const [description, setDescription] = useState(route?.description ?? "");
  const [visibility, setVisibility] = useState(
    route?.visibility || "community",
  );
  const [matchWidth, setMatchWidth] = useState(route?.match_width || 1);
  const [pathQuery, setPathQuery] = useState("");
  const [obsQuery, setObsQuery] = useState("");
  const [windowHours, setWindowHours] = useState(
    String(route?.window_hours || 48),
  );
  const [threshold, setThreshold] = useState(
    String(route?.packet_count_threshold || 5),
  );
  const [clearThreshold, setClearThreshold] = useState(
    route?.clear_threshold ? String(route.clear_threshold) : "",
  );
  const [hopSpan, setHopSpan] = useState(
    route ? (route.max_hop_span ? String(route.max_hop_span) : "") : "8",
  );
  const [pathLength, setPathLength] = useState(
    route?.max_path_length ? String(route.max_path_length) : "",
  );
  const [enabled, setEnabled] = useState(route?.enabled !== false);
  const [reversible, setReversible] = useState(route?.reversible !== false);

  const selectedPathKeys = new Set(pathNodes.map((n) => n.public_key));
  const selectedObsKeys = new Set(observerNodes.map((n) => n.public_key));
  const availPathResults = pathResults.filter(
    (n) => !selectedPathKeys.has(n.public_key),
  );
  const availObsResults = obsResults.filter(
    (n) => !selectedObsKeys.has(n.public_key),
  );

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    onSubmit({
      from_label: fromLabel,
      to_label: toLabel,
      description,
      visibility,
      match_width: matchWidth,
      window_hours: windowHours,
      packet_count_threshold: threshold,
      clear_threshold: clearThreshold,
      max_hop_span: hopSpan,
      max_path_length: pathLength,
      enabled,
      reversible,
    });
  };

  const handlePathKeydown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const first = availPathResults[0];
    if (first) {
      onPathSelect(first);
      setPathQuery("");
      return;
    }
    onPathEnter(pathQuery);
    setPathQuery("");
  };

  const handleObsKeydown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const first = availObsResults[0];
    if (first) {
      onObsSelect(first);
      setObsQuery("");
      return;
    }
    onObsEnter(obsQuery);
    setObsQuery("");
  };

  return (
    <dialog open className="modal modal-open">
      <div className="modal-box modal-box-lg">
        <h3 className="font-bold text-lg mb-4">
          {isEdit ? t("routes.edit_route") : t("routes.add_route")}
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 gap-3 mb-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.from_label")}
                </label>
                <input
                  type="text"
                  className="input input-sm w-full"
                  value={fromLabel}
                  onChange={(e) => setFromLabel(e.target.value)}
                  placeholder={t("routes.from_label")}
                  required
                  maxLength={255}
                />
              </div>
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.to_label")}
                </label>
                <input
                  type="text"
                  className="input input-sm w-full"
                  value={toLabel}
                  onChange={(e) => setToLabel(e.target.value)}
                  placeholder={t("routes.to_label")}
                  required
                  maxLength={255}
                />
              </div>
            </div>
            <div>
              <label className="text-sm opacity-70">
                {t("routes.description_label")}
              </label>
              <input
                type="text"
                className="input input-sm w-full"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("routes.description_label")}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.visibility_label")}
                </label>
                <select
                  className="select select-sm w-full"
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                >
                  <option value="community">community</option>
                  <option value="member">member</option>
                  <option value="operator">operator</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.width_label")}
                </label>
                <div className="flex gap-1 mt-1">
                  {[1, 2, 3].map((w) => (
                    <button
                      key={w}
                      type="button"
                      className={`btn btn-xs ${
                        matchWidth === w ? "btn-primary" : "btn-outline"
                      }`}
                      onClick={() => setMatchWidth(w)}
                    >
                      {w}B
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div>
              <label className="text-sm opacity-70">
                {t("routes.path_label")}
              </label>
              <div className="relative">
                <input
                  type="text"
                  className="input input-sm w-full"
                  value={pathQuery}
                  onChange={(e) => {
                    setPathQuery(e.target.value);
                    onPathSearch(e.target.value);
                  }}
                  onKeyDown={handlePathKeydown}
                  placeholder={t("routes.search_nodes_placeholder")}
                  autoComplete="off"
                />
                {availPathResults.length > 0 && (
                  <ul className="menu bg-base-200 rounded-box absolute z-50 left-0 right-0 top-full mt-1 p-2 shadow-lg max-h-60 overflow-auto">
                    {availPathResults.map((n) => (
                      <NodeSearchResultRow
                        key={n.public_key}
                        node={n}
                        onSelect={() => {
                          onPathSelect(n);
                          setPathQuery("");
                        }}
                      />
                    ))}
                  </ul>
                )}
              </div>
              <p className="text-xs opacity-50 mt-1">{t("routes.path_help")}</p>
              <div className="flex flex-wrap items-center gap-1 mt-2 min-h-[2.5rem] p-2 bg-base-200 rounded-box">
                {pathNodes.length === 0 ? (
                  <span className="text-sm opacity-40">
                    {t("routes.path_empty")}
                  </span>
                ) : (
                  pathNodes.map((n, i) => (
                    <Fragment key={n.public_key}>
                      {i > 0 && (
                        <span className="text-primary text-sm px-0.5">
                          {"\u2192"}
                        </span>
                      )}
                      <span className="inline-flex items-center gap-0.5 bg-primary text-primary-content rounded-full px-2 py-1 text-sm">
                        {i > 0 && (
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs btn-circle text-primary-content opacity-60 hover:opacity-100"
                            onClick={() => onPathMove(i, -1)}
                          >
                            {"\u25C4"}
                          </button>
                        )}
                        <span>{n.name || n.public_key.slice(0, 8)}</span>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs btn-circle text-primary-content opacity-60 hover:opacity-100"
                          onClick={() => onPathRemove(i)}
                        >
                          {"\u2715"}
                        </button>
                        {i < pathNodes.length - 1 && (
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs btn-circle text-primary-content opacity-60 hover:opacity-100"
                            onClick={() => onPathMove(i, 1)}
                          >
                            {"\u25BA"}
                          </button>
                        )}
                      </span>
                    </Fragment>
                  ))
                )}
              </div>
            </div>
            <div>
              <label className="text-sm opacity-70">
                {t("routes.observers_label")}
              </label>
              <div className="relative">
                <input
                  type="text"
                  className="input input-sm w-full"
                  value={obsQuery}
                  onChange={(e) => {
                    setObsQuery(e.target.value);
                    onObsSearch(e.target.value);
                  }}
                  onKeyDown={handleObsKeydown}
                  placeholder={t("routes.search_nodes_placeholder")}
                  autoComplete="off"
                />
                {availObsResults.length > 0 && (
                  <ul className="menu bg-base-200 rounded-box absolute z-50 left-0 right-0 top-full mt-1 p-2 shadow-lg max-h-60 overflow-auto">
                    {availObsResults.map((n) => (
                      <NodeSearchResultRow
                        key={n.public_key}
                        node={n}
                        onSelect={() => {
                          onObsSelect(n);
                          setObsQuery("");
                        }}
                      />
                    ))}
                  </ul>
                )}
              </div>
              <p className="text-xs opacity-50 mt-1">
                {t("routes.observers_help")}
              </p>
              <div className="flex flex-wrap items-center gap-1 mt-2 min-h-[2.5rem] p-2 bg-base-200 rounded-box">
                {observerNodes.length === 0 ? (
                  <span className="text-sm opacity-40">
                    {t("routes.observers_empty")}
                  </span>
                ) : (
                  observerNodes.map((n, i) => (
                    <span
                      key={n.public_key}
                      className="inline-flex items-center gap-0.5 bg-base-300 rounded-full px-2 py-1 text-sm"
                    >
                      <span>{n.name || n.public_key.slice(0, 8)}</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs btn-circle opacity-60 hover:opacity-100"
                        onClick={() => onObsRemove(i)}
                      >
                        {"\u2715"}
                      </button>
                    </span>
                  ))
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.window_label")}
                </label>
                <input
                  type="number"
                  className="input input-sm w-full"
                  value={windowHours}
                  onChange={(e) => setWindowHours(e.target.value)}
                  min={1}
                  max={720}
                />
              </div>
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.threshold_label")}
                </label>
                <input
                  type="number"
                  className="input input-sm w-full"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  min={1}
                  max={10000}
                />
              </div>
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.clear_label")}
                </label>
                <input
                  type="number"
                  className="input input-sm w-full"
                  value={clearThreshold}
                  onChange={(e) => setClearThreshold(e.target.value)}
                  placeholder={String(3 * (parseInt(threshold, 10) || 5))}
                  min={1}
                />
              </div>
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.span_label")}
                </label>
                <input
                  type="number"
                  className="input input-sm w-full"
                  value={hopSpan}
                  onChange={(e) => setHopSpan(e.target.value)}
                  placeholder={"\u221E"}
                  min={1}
                />
              </div>
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.path_length_label")}
                </label>
                <input
                  type="number"
                  className="input input-sm w-full"
                  value={pathLength}
                  onChange={(e) => setPathLength(e.target.value)}
                  placeholder={"\u221E"}
                  min={1}
                />
              </div>
            </div>
            <div className="flex gap-6">
              <label className="label cursor-pointer justify-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />
                <span className="text-sm">{t("routes.enabled_label")}</span>
              </label>
              <label className="label cursor-pointer justify-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  checked={reversible}
                  onChange={(e) => setReversible(e.target.checked)}
                />
                <span className="text-sm">{t("routes.reversible_label")}</span>
              </label>
            </div>
          </div>
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={onCancel}
              disabled={saving}
            >
              {t("common.cancel")}
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving && (
                <span className="loading loading-spinner loading-sm"></span>
              )}
              {t("common.save")}
            </button>
          </div>
        </form>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onCancel}></button>
      </form>
    </dialog>
  );
}

function DeleteRouteModal({
  route,
  saving,
  onConfirm,
  onCancel,
}: {
  route: RouteItem;
  saving: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const arrow = route.reversible !== false ? "\u2194" : "\u2192";
  const label = `${route.from_label} ${arrow} ${route.to_label}`;

  return (
    <dialog open className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg mb-4">{t("routes.delete_route")}</h3>
        <p>{t("routes.delete_confirm", { label })}</p>
        <div className="modal-action">
          <button
            className="btn btn-ghost"
            onClick={onCancel}
            disabled={saving}
          >
            {t("common.cancel")}
          </button>
          <button className="btn btn-error" onClick={onConfirm} disabled={saving}>
            {saving && (
              <span className="loading loading-spinner loading-sm"></span>
            )}
            {t("common.delete")}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onCancel}></button>
      </form>
    </dialog>
  );
}

export function RoutesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const config = useAppConfig();
  const packetsEnabled = config.features?.packets !== false;
  const isAdmin = hasRole("admin");
  usePageTitle("routes.title");

  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [detailCache, setDetailCache] = useState<Record<string, RouteDetail>>(
    {},
  );
  const [historyCache, setHistoryCache] = useState<
    Record<string, RouteHistory>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState | null>(null);

  const detailCacheRef = useRef<Record<string, RouteDetail>>({});
  const historyCacheRef = useRef<Record<string, RouteHistory>>({});
  const chartsRef = useRef<ChartInstance[]>([]);
  const pathTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const obsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pathSearchIdRef = useRef(0);
  const obsSearchIdRef = useRef(0);

  const destroyCharts = useCallback(() => {
    chartsRef.current.forEach((c) => {
      try {
        c.destroy();
      } catch (_) {}
    });
    chartsRef.current = [];
  }, []);

  const loadAllDetails = useCallback(async (routesList: RouteItem[]) => {
    const newDetails: Record<string, RouteDetail> = {};
    const newHistories: Record<string, RouteHistory> = {};
    const promises: Promise<void>[] = [];
    for (const r of routesList) {
      if (!detailCacheRef.current[r.id]) {
        promises.push(
          apiGet<RouteDetail>(`/api/v1/routes/${r.id}`)
            .then((d) => {
              newDetails[r.id] = d;
            })
            .catch(() => undefined),
        );
      }
      if (!historyCacheRef.current[r.id]) {
        promises.push(
          apiGet<RouteHistory>(`/api/v1/routes/${r.id}/history`, { days: 6 })
            .then((h) => {
              newHistories[r.id] = h;
            })
            .catch(() => undefined),
        );
      }
    }
    if (promises.length === 0) return;
    await Promise.allSettled(promises);
    if (Object.keys(newDetails).length > 0) {
      detailCacheRef.current = { ...detailCacheRef.current, ...newDetails };
      setDetailCache(detailCacheRef.current);
    }
    if (Object.keys(newHistories).length > 0) {
      historyCacheRef.current = { ...historyCacheRef.current, ...newHistories };
      setHistoryCache(historyCacheRef.current);
    }
  }, []);

  const fetchRoutes = useCallback(async (): Promise<RouteItem[]> => {
    try {
      const data = await apiGet<RouteListResponse>("/api/v1/routes");
      const items = data.items || [];
      setRoutes(items);
      setError(null);
      return items;
    } catch (e) {
      setError((e as Error).message || t("common.failed_to_load_page"));
      return [];
    } finally {
      setLoading(false);
    }
  }, [t]);

  const refresh = useCallback(async () => {
    const items = await fetchRoutes();
    await loadAllDetails(items);
  }, [fetchRoutes, loadAllDetails]);

  useEffect(() => {
    let active = true;
    (async () => {
      const items = await fetchRoutes();
      if (active) await loadAllDetails(items);
    })();
    return () => {
      active = false;
    };
  }, [fetchRoutes, loadAllDetails]);

  useEffect(() => {
    destroyCharts();
    for (const r of routes) {
      const h = historyCache[r.id];
      if (detailCache[r.id] && h) {
        const chart = window.createRouteDetailStrip(
          `routeStripChart-${r.id}`,
          h,
        ) as ChartInstance | null;
        if (chart) chartsRef.current.push(chart);
      }
    }
  }, [routes, detailCache, historyCache, destroyCharts]);

  useEffect(() => {
    return () => {
      destroyCharts();
      if (pathTimerRef.current) clearTimeout(pathTimerRef.current);
      if (obsTimerRef.current) clearTimeout(obsTimerRef.current);
    };
  }, [destroyCharts]);

  const openAddModal = () => {
    setModal({
      type: "add",
      route: null,
      pathNodes: [],
      observerNodes: [],
      pathResults: [],
      obsResults: [],
      saving: false,
    });
  };

  const openEditModal = (route: RouteItem) => {
    setModal({
      type: "edit",
      route,
      pathNodes: (route.route_nodes || []).map((rn) => ({
        public_key: rn.public_key ?? "",
        name: rn.name,
      })),
      observerNodes: (route.route_observers || []).map((ro) => ({
        public_key: ro.public_key ?? "",
        name: ro.name,
      })),
      pathResults: [],
      obsResults: [],
      saving: false,
    });
  };

  const openDeleteModal = (route: RouteItem) => {
    setModal({
      type: "delete",
      route,
      pathNodes: [],
      observerNodes: [],
      pathResults: [],
      obsResults: [],
      saving: false,
    });
  };

  const handlePathSearch = (query: string) => {
    if (pathTimerRef.current) clearTimeout(pathTimerRef.current);
    const q = query.trim();
    if (q.length < 2) {
      setModal((m) => (m ? { ...m, pathResults: [] } : m));
      return;
    }
    pathTimerRef.current = setTimeout(async () => {
      const myId = ++pathSearchIdRef.current;
      try {
        const data = await apiGet<NodeListResponse>("/api/v1/nodes", {
          search: q,
          limit: 10,
        });
        if (myId !== pathSearchIdRef.current) return;
        setModal((m) => (m ? { ...m, pathResults: data.items || [] } : m));
      } catch (_) {}
    }, 300);
  };

  const handlePathSelect = (node: NodeSearchResult) => {
    setModal((m) => {
      if (!m) return m;
      if (m.pathNodes.some((n) => n.public_key === node.public_key)) return m;
      return {
        ...m,
        pathNodes: [
          ...m.pathNodes,
          { public_key: node.public_key, name: node.name },
        ],
        pathResults: [],
      };
    });
  };

  const handlePathRemove = (index: number) => {
    setModal((m) => {
      if (!m) return m;
      const next = [...m.pathNodes];
      next.splice(index, 1);
      return { ...m, pathNodes: next };
    });
  };

  const handlePathMove = (index: number, dir: number) => {
    setModal((m) => {
      if (!m) return m;
      const newIndex = index + dir;
      if (newIndex < 0 || newIndex >= m.pathNodes.length) return m;
      const next = [...m.pathNodes];
      [next[index], next[newIndex]] = [next[newIndex], next[index]];
      return { ...m, pathNodes: next };
    });
  };

  const handlePathEnter = async (query: string) => {
    const q = query.trim();
    if (q.length < 2) return;
    if (pathTimerRef.current) clearTimeout(pathTimerRef.current);
    const myId = ++pathSearchIdRef.current;
    try {
      const data = await apiGet<NodeListResponse>("/api/v1/nodes", {
        search: q,
        limit: 10,
      });
      if (myId !== pathSearchIdRef.current) return;
      const items = data.items || [];
      const selectedKeys = new Set(
        (modal?.pathNodes ?? []).map((n) => n.public_key),
      );
      setModal((m) => (m ? { ...m, pathResults: items } : m));
      const first = items.find((n) => !selectedKeys.has(n.public_key));
      if (first) handlePathSelect(first);
    } catch (_) {}
  };

  const handleObsSearch = (query: string) => {
    if (obsTimerRef.current) clearTimeout(obsTimerRef.current);
    const q = query.trim();
    if (q.length < 2) {
      setModal((m) => (m ? { ...m, obsResults: [] } : m));
      return;
    }
    obsTimerRef.current = setTimeout(async () => {
      const myId = ++obsSearchIdRef.current;
      try {
        const data = await apiGet<NodeListResponse>("/api/v1/nodes", {
          search: q,
          limit: 10,
          observer: true,
        });
        if (myId !== obsSearchIdRef.current) return;
        setModal((m) => (m ? { ...m, obsResults: data.items || [] } : m));
      } catch (_) {}
    }, 300);
  };

  const handleObsSelect = (node: NodeSearchResult) => {
    setModal((m) => {
      if (!m) return m;
      if (m.observerNodes.some((n) => n.public_key === node.public_key))
        return m;
      return {
        ...m,
        observerNodes: [
          ...m.observerNodes,
          { public_key: node.public_key, name: node.name },
        ],
        obsResults: [],
      };
    });
  };

  const handleObsRemove = (index: number) => {
    setModal((m) => {
      if (!m) return m;
      const next = [...m.observerNodes];
      next.splice(index, 1);
      return { ...m, observerNodes: next };
    });
  };

  const handleObsEnter = async (query: string) => {
    const q = query.trim();
    if (q.length < 2) return;
    if (obsTimerRef.current) clearTimeout(obsTimerRef.current);
    const myId = ++obsSearchIdRef.current;
    try {
      const data = await apiGet<NodeListResponse>("/api/v1/nodes", {
        search: q,
        limit: 10,
        observer: true,
      });
      if (myId !== obsSearchIdRef.current) return;
      const items = data.items || [];
      const selectedKeys = new Set(
        (modal?.observerNodes ?? []).map((n) => n.public_key),
      );
      setModal((m) => (m ? { ...m, obsResults: items } : m));
      const first = items.find((n) => !selectedKeys.has(n.public_key));
      if (first) handleObsSelect(first);
    } catch (_) {}
  };

  const handleSave = async (values: RouteFormValues) => {
    if (!modal || modal.type === "delete") return;
    if (modal.pathNodes.length < 2) {
      alert(t("routes.min_nodes_error"));
      return;
    }
    const isEdit = modal.type === "edit" && modal.route !== null;
    const body: Record<string, unknown> = {
      from_label: values.from_label.trim(),
      to_label: values.to_label.trim(),
      description: values.description.trim() || null,
      visibility: values.visibility,
      match_width: values.match_width || 1,
      window_hours: parseInt(values.window_hours, 10) || 48,
      packet_count_threshold: parseInt(values.packet_count_threshold, 10) || 5,
      max_hop_span: values.max_hop_span
        ? parseInt(values.max_hop_span, 10)
        : null,
      max_path_length: values.max_path_length
        ? parseInt(values.max_path_length, 10)
        : null,
      enabled: values.enabled,
      reversible: values.reversible,
      node_public_keys: modal.pathNodes.map((n) => n.public_key),
      observer_public_keys: modal.observerNodes.map((n) => n.public_key),
    };
    if (values.clear_threshold.trim()) {
      body.clear_threshold = parseInt(values.clear_threshold, 10);
    }
    setModal((m) => (m ? { ...m, saving: true } : m));
    try {
      if (isEdit && modal.route) {
        const id = modal.route.id;
        await apiPut(`/api/v1/routes/${id}`, body);
        const nextDetails = { ...detailCacheRef.current };
        delete nextDetails[id];
        detailCacheRef.current = nextDetails;
        setDetailCache(nextDetails);
        const nextHistories = { ...historyCacheRef.current };
        delete nextHistories[id];
        historyCacheRef.current = nextHistories;
        setHistoryCache(nextHistories);
      } else {
        await apiPost("/api/v1/routes", body);
      }
      setModal(null);
      await refresh();
    } catch (e) {
      setModal((m) => (m ? { ...m, saving: false } : m));
      alert((e as Error).message || "Failed to save route");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!modal || modal.type !== "delete" || !modal.route) return;
    setModal((m) => (m ? { ...m, saving: true } : m));
    try {
      await apiDelete(`/api/v1/routes/${modal.route.id}`);
      setModal(null);
      await refresh();
    } catch (e) {
      setModal((m) => (m ? { ...m, saving: false } : m));
      alert((e as Error).message || "Failed to delete route");
    }
  };

  if (loading) return <Loading />;

  const groups = new Map<string, RouteItem[]>();
  for (const vis of VISIBILITY_ORDER) groups.set(vis, []);
  for (const r of routes) {
    const vis = r.visibility || "community";
    if (!groups.has(vis)) groups.set(vis, []);
    groups.get(vis)!.push(r);
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <IconPath className="h-8 w-8" />
          {t("routes.title")}
        </h1>
      </div>

      <SummaryStrip routes={routes} />

      {error && <ErrorAlert message={error} />}

      {isAdmin && (
        <div className="flex justify-end mb-4">
          <button
            className="btn btn-primary btn-sm"
            onClick={openAddModal}
          >
            <IconPlus className="h-4 w-4" /> {t("routes.add_route")}
          </button>
        </div>
      )}

      {routes.length === 0 && (
        <div className="text-center py-8 opacity-70">
          {t("common.no_entity_found", {
            entity: t("entities.routes").toLowerCase(),
          })}
        </div>
      )}

      {VISIBILITY_ORDER.map((vis) => {
        const group = (groups.get(vis) || []).slice().sort((a, b) => {
          const cmp = (a.from_label || "").localeCompare(b.from_label || "");
          return cmp !== 0
            ? cmp
            : (a.to_label || "").localeCompare(b.to_label || "");
        });
        if (group.length === 0) return null;
        return (
          <div key={vis}>
            <h2 className="text-lg font-semibold mt-6 mb-3 opacity-70">
              {t(`routes.visibility_${vis}`)}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {group.map((r) => (
                <RouteCard
                  key={r.id}
                  route={r}
                  detail={detailCache[r.id]}
                  history={historyCache[r.id]}
                  isAdmin={isAdmin}
                  packetsEnabled={packetsEnabled}
                  onEdit={() => openEditModal(r)}
                  onDelete={() => openDeleteModal(r)}
                  onNavigate={navigate}
                />
              ))}
            </div>
          </div>
        );
      })}

      {modal && (modal.type === "add" || modal.type === "edit") && (
        <RouteModal
          key={modal.type === "edit" && modal.route ? `edit-${modal.route.id}` : "add"}
          route={modal.route}
          isEdit={modal.type === "edit"}
          pathNodes={modal.pathNodes}
          observerNodes={modal.observerNodes}
          pathResults={modal.pathResults}
          obsResults={modal.obsResults}
          saving={modal.saving}
          onPathSearch={handlePathSearch}
          onPathSelect={handlePathSelect}
          onPathRemove={handlePathRemove}
          onPathMove={handlePathMove}
          onPathEnter={handlePathEnter}
          onObsSearch={handleObsSearch}
          onObsSelect={handleObsSelect}
          onObsRemove={handleObsRemove}
          onObsEnter={handleObsEnter}
          onSubmit={handleSave}
          onCancel={() => setModal(null)}
        />
      )}

      {modal?.type === "delete" && modal.route && (
        <DeleteRouteModal
          route={modal.route}
          saving={modal.saving}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  );
}
