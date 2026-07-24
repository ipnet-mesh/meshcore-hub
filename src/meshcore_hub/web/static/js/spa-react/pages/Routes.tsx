import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type SVGProps,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useAppConfig, hasRole } from "@/context/AppConfigContext";
import { apiGet, apiPost, apiPut, apiDelete } from "@/utils/api";
import { qk, invalidate } from "@/utils/queryKeys";
import { usePageTitle } from "@/hooks/usePageTitle";
import { Loading, ErrorAlert } from "@/components/Alerts";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { FilterForm, FilterField, FilterToggle, autoSubmit } from "@/components/FilterForm";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { SectionGroup } from "@/components/SectionGroup";
import { RouteDetailStrip } from "@/components/charts/Charts";
import {
  qualityOf,
  qualityBadgeClass,
  qualityLabel,
  diagnosisText,
} from "@/utils/routesHelpers";
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
  IconUser,
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

interface RouteOwnerInfo {
  user_id: string;
  name?: string | null;
  callsign?: string | null;
  profile_id: string;
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
  created_by?: string | null;
  owner?: RouteOwnerInfo | null;
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

/** Max route-visibility tier the current user may set or modify. Mirrors the
 * backend caller cap so a user can never scope a route above their own role
 * (which would make it invisible/unmodifiable to them). */
function maxVisibilityLevel(): number {
  if (hasRole("admin")) return 3;
  if (hasRole("operator")) return 2;
  if (hasRole("member")) return 1;
  return 0;
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
        <div className="mb-3 min-w-0">
          <RouteDetailStrip data={history} />
          {historyData.length > 0 && (
            <div className="flex text-xs opacity-50 mt-0.5 min-w-0">
              {historyData.map((d, i) => (
                <span key={d.date} className="flex-1 text-center min-w-0 truncate">
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
          <div className="mt-2 space-y-2 overflow-hidden">
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
  canEdit,
  packetsEnabled,
  onEdit,
  onDelete,
  onNavigate,
}: {
  route: RouteItem;
  canEdit: boolean;
  packetsEnabled: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onNavigate: (url: string) => void;
}) {
  const { t } = useTranslation();
  const { data: detail } = useQuery({
    queryKey: qk.routes.detail(route.id),
    queryFn: ({ signal }) =>
      apiGet<RouteDetail>(`/api/v1/routes/${route.id}`, {}, { signal }),
  });
  const { data: history } = useQuery({
    queryKey: qk.routes.history(route.id, 6),
    queryFn: ({ signal }) =>
      apiGet<RouteHistory>(
        `/api/v1/routes/${route.id}/history`,
        { days: 6 },
        { signal },
      ),
  });
  const q = qualityOf(route);
  const badgeCls = qualityBadgeClass(q, route.enabled);
  const label = qualityLabel(q, route.enabled, t);
  const dot = qualityDot(q, route.enabled);
  const tip = diagnosisText(route, t);

  return (
    <div
      className="card bg-base-100 shadow-xl h-full min-w-0"
      data-testid="route-card"
      data-route-label={`${route.from_label} → ${route.to_label}`}
    >
      <div className="card-body overflow-hidden">
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
        {route.created_by && (
          <div className="text-xs opacity-60 flex items-center gap-1 mt-1">
            <IconUser className="h-3 w-3" />
            {route.owner ? (
              <Link
                to={`/profile/${route.owner.profile_id}`}
                className="link link-hover"
              >
                {route.owner.name || route.owner.user_id}
              </Link>
            ) : (
              <span>{route.created_by}</span>
            )}
          </div>
        )}
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
        {canEdit && (
          <div className="flex gap-2 mt-auto pt-2">
            <button
              className="btn btn-xs btn-outline"
              data-testid="edit-route"
              onClick={onEdit}
            >
              <IconEdit className="h-3 w-3" /> {t("common.edit")}
            </button>
            <button
              className="btn btn-xs btn-outline btn-error"
              data-testid="delete-route"
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
        data-testid="node-search-result"
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
    <Modal
      size="lg"
      title={isEdit ? t("routes.edit_route") : t("routes.add_route")}
      onClose={onCancel}
    >
        <form onSubmit={handleSubmit} data-testid="route-modal">
          <div className="grid grid-cols-1 gap-3 mb-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-sm opacity-70">
                  {t("routes.from_label")}
                </label>
                <input
                  type="text"
                  className="input input-sm w-full"
                  data-testid="route-from"
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
                  data-testid="route-to"
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
                data-testid="route-description"
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
                  data-testid="route-visibility"
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                >
                  {VISIBILITY_ORDER.map((vis) =>
                    VISIBILITY_ORDER.indexOf(vis) <= maxVisibilityLevel() ? (
                      <option key={vis} value={vis}>
                        {vis}
                      </option>
                    ) : null,
                  )}
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
                      data-testid="route-width"
                      data-width={w}
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
                  data-testid="route-path-search"
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
                      <span
                        className="inline-flex items-center gap-0.5 bg-primary text-primary-content rounded-full px-2 py-1 text-sm"
                        data-testid="route-path-chip"
                      >
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
                  data-testid="route-observer-search"
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
                  data-testid="route-window"
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
                  data-testid="route-threshold"
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
                  data-testid="route-clear-threshold"
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
                  data-testid="route-max-span"
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
                  data-testid="route-max-path-length"
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
                  data-testid="route-enabled"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />
                <span className="text-sm">{t("routes.enabled_label")}</span>
              </label>
              <label className="label cursor-pointer justify-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  data-testid="route-reversible"
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
              data-testid="route-cancel"
              onClick={onCancel}
              disabled={saving}
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              data-testid="route-save"
              disabled={saving}
            >
              {saving && (
                <span className="loading loading-spinner loading-sm"></span>
              )}
              {t("common.save")}
            </button>
          </div>
        </form>
    </Modal>
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
    <ConfirmDialog
      title={t("routes.delete_route")}
      message={<p>{t("routes.delete_confirm", { label })}</p>}
      confirmLabel={t("common.delete")}
      cancelLabel={t("common.cancel")}
      saving={saving}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

export function RoutesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const config = useAppConfig();
  const packetsEnabled = config.features?.packets !== false;
  const canManage = hasRole("admin") || hasRole("operator");
  const currentUserId = config.user?.sub;
  const isAdmin = hasRole("admin");
  const canEditRoute = (r: RouteItem) =>
    isAdmin || (!!r.created_by && r.created_by === currentUserId);
  const mine = searchParams.get("mine") === "true";
  const [filterOpen, setFilterOpen] = useState(false);
  usePageTitle("entities.routes");

  const queryClient = useQueryClient();

  const {
    data: routesData,
    isLoading: loading,
    error: queryError,
  } = useQuery({
    queryKey: qk.routes.list({ mine }),
    queryFn: async ({ signal }) => {
      const data = await apiGet<RouteListResponse>(
        "/api/v1/routes",
        mine ? { mine: "true" } : {},
        { signal },
      );
      return data.items || [];
    },
  });
  const routes = routesData ?? [];
  const error = queryError ? queryError.message : null;
  const [modal, setModal] = useState<ModalState | null>(null);

  const pathTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const obsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pathSearchIdRef = useRef(0);
  const obsSearchIdRef = useRef(0);

  const saveMutation = useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id?: string;
      body: Record<string, unknown>;
    }) => {
      if (id) {
        await apiPut(`/api/v1/routes/${id}`, body);
      } else {
        await apiPost("/api/v1/routes", body);
      }
    },
    onSuccess: () => invalidate.routes(queryClient),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiDelete(`/api/v1/routes/${id}`),
    onSuccess: () => invalidate.routes(queryClient),
  });

  useEffect(() => {
    return () => {
      if (pathTimerRef.current) clearTimeout(pathTimerRef.current);
      if (obsTimerRef.current) clearTimeout(obsTimerRef.current);
    };
  }, []);

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
      await saveMutation.mutateAsync({
        id: isEdit && modal.route ? modal.route.id : undefined,
        body,
      });
      setModal(null);
    } catch (e) {
      setModal((m) => (m ? { ...m, saving: false } : m));
      alert((e as Error).message || "Failed to save route");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!modal || modal.type !== "delete" || !modal.route) return;
    setModal((m) => (m ? { ...m, saving: true } : m));
    try {
      await deleteMutation.mutateAsync(modal.route.id);
      setModal(null);
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
    <div className="overflow-x-hidden">
      <PageHeader title={t("entities.routes")} icon={IconPath} />

      <SummaryStrip routes={routes} />

      {error && <ErrorAlert message={error} />}

      {canManage && (
        <div className="flex items-center justify-between mb-4 gap-2">
          <FilterToggle open={filterOpen} onChange={() => setFilterOpen((v) => !v)} />
          <button
            className="btn btn-primary btn-sm"
            data-testid="add-route"
            onClick={openAddModal}
          >
            <IconPlus className="h-4 w-4" /> {t("routes.add_route")}
          </button>
        </div>
      )}

      {filterOpen && canManage && (
        <div className="mb-4">
          <FilterForm basePath="/routes">
            <FilterField label={t("routes.filter_mine")}>
              <label className="label cursor-pointer justify-start gap-2 py-1">
                <input
                  type="checkbox"
                  name="mine"
                  value="true"
                  data-testid="routes-mine-toggle"
                  className="checkbox checkbox-sm"
                  key={`mine-${mine}`}
                  defaultChecked={mine}
                  onChange={autoSubmit}
                />
                <span className="text-sm">{t("routes.filter_mine")}</span>
              </label>
            </FilterField>
          </FilterForm>
        </div>
      )}

      {routes.length === 0 && (
        <EmptyState>
          {t("common.no_entity_found", {
            entity: t("entities.routes").toLowerCase(),
          })}
        </EmptyState>
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
            <SectionGroup title={t(`routes.visibility_${vis}`)}>
              {group.map((r) => (
                <RouteCard
                  key={r.id}
                  route={r}
                  canEdit={canEditRoute(r)}
                  packetsEnabled={packetsEnabled}
                  onEdit={() => openEditModal(r)}
                  onDelete={() => openDeleteModal(r)}
                  onNavigate={navigate}
                />
              ))}
            </SectionGroup>
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
