import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiGet, isAbortError } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import {
  formatNumber,
  resolveNodeName,
  truncateKey,
  useFormatDateTime,
} from "@/utils/format";
import { Loading, WarningBadge } from "@/components/Alerts";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { IconSatelliteDish } from "@/components/icons";
import { NotFoundState } from "@/components/NotFoundState";
import { TimeAgo } from "@/components/TimeAgo";
import { DefinitionGrid } from "@/components/Definition";
import {
  buildChannelNames,
  isNotFoundError,
  type ChannelItem,
} from "@/utils/packets";
import {
  Field,
  RedactedNotice,
  RawHexBlock,
  DecodedJsonBlock,
  channelNameDisplay,
} from "@/components/PacketParts";

const PATH_MAX_BADGES = 16;
const PATH_HEAD = 7;
const PATH_TAIL = 7;
const PATH_POPOVER_NODE_CAP = 8;

interface Reception {
  packet_id: string;
  observed_by: string | null;
  observer_name: string | null;
  observer_tag_name: string | null;
  path_hashes: string[] | null;
  path_len: number | null;
  snr: number | null;
  received_at: string | null;
}

interface PacketGroupData {
  packet_hash: string | null;
  event_type: string | null;
  channel_idx: number | null;
  source_pubkey_prefix: string | null;
  packet_type: number | null;
  payload_type: number | null;
  route_type: string | null;
  reception_count: number;
  observer_count: number;
  first_seen: string | null;
  redacted: boolean;
  raw_hex: string | null;
  decoded: unknown;
  receptions: Reception[];
}

interface ChannelsResponse {
  items: ChannelItem[];
}

interface NodeItem {
  public_key: string;
  name: string | null;
  tags?: { key: string; value: string }[];
}

interface NodesResponse {
  items: NodeItem[];
  total: number;
}

interface PopoverAnchor {
  hash: string;
  left: number;
  bottom: number;
  top: number;
}

function groupByObserver(receptions: Reception[]): Map<string, Reception[]> {
  const groups = new Map<string, Reception[]>();
  for (const r of receptions) {
    const key = r.observed_by || "__unknown__";
    const list = groups.get(key);
    if (list) {
      list.push(r);
    } else {
      groups.set(key, [r]);
    }
  }
  return groups;
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase opacity-60">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

function PathBadge({
  hash,
  onOpen,
}: {
  hash: string;
  onOpen: (e: React.MouseEvent, hash: string) => void;
}) {
  return (
    <span
      className="badge badge-sm badge-primary font-mono text-xs cursor-pointer"
      onClick={(e) => onOpen(e, hash)}
    >
      {hash}
    </span>
  );
}

function PathFlow({
  reception,
  sourcePrefix,
  onBadgeOpen,
}: {
  reception: Reception;
  sourcePrefix: string | null;
  onBadgeOpen: (e: React.MouseEvent, hash: string) => void;
}) {
  const { t } = useTranslation();
  const hashes = reception.path_hashes ?? [];

  let middle: ReactNode[];
  if (hashes.length > 0) {
    if (hashes.length <= PATH_MAX_BADGES) {
      middle = hashes.map((h, i) => (
        <PathBadge key={`${i}-${h}`} hash={h} onOpen={onBadgeOpen} />
      ));
    } else {
      const hidden = hashes.length - PATH_HEAD - PATH_TAIL;
      middle = [
        ...hashes
          .slice(0, PATH_HEAD)
          .map((h, i) => (
            <PathBadge key={`head-${i}-${h}`} hash={h} onOpen={onBadgeOpen} />
          )),
        <span
          key="ellipsis"
          className="badge badge-sm badge-ghost cursor-help"
          title={t("packets.hops_hidden", { count: hidden })}
        >
          …
        </span>,
        ...hashes
          .slice(-PATH_TAIL)
          .map((h, i) => (
            <PathBadge key={`tail-${i}-${h}`} hash={h} onOpen={onBadgeOpen} />
          )),
      ];
    }
  } else if (reception.path_len != null) {
    middle = [
      <span key="len" className="text-xs opacity-60">
        {reception.path_len} {t("common.hops").toLowerCase()}
      </span>,
    ];
  } else {
    middle = [
      <span key="none" className="opacity-50">
        —
      </span>,
    ];
  }

  const parts: ReactNode[] = [
    <span
      key="sender"
      className="inline-block h-3 w-3 rounded-full bg-success flex-shrink-0"
      title={
        sourcePrefix
          ? `${t("packets.col_source")}: ${sourcePrefix}`
          : t("packets.col_source")
      }
    />,
    ...middle,
    <span key="observer" className="flex-shrink-0">
      <IconSatelliteDish className="h-4 w-4 opacity-70" />
    </span>,
  ];

  const joined: ReactNode[] = [];
  parts.forEach((part, i) => {
    if (i > 0) {
      joined.push(
        <span key={`arrow-${i}`} className="opacity-40 text-xs">
          →
        </span>,
      );
    }
    joined.push(part);
  });

  return <span className="flex flex-wrap items-center gap-1">{joined}</span>;
}

export function PacketGroupDetail() {
  const { t } = useTranslation();
  usePageTitle("packets.detail_title");
  const { hash } = useParams();
  const { formatDateTime } = useFormatDateTime();

  const [popover, setPopover] = useState<PopoverAnchor | null>(null);
  const [popoverPos, setPopoverPos] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const [popoverNodes, setPopoverNodes] = useState<NodeItem[] | null>(null);
  const [popoverTotal, setPopoverTotal] = useState(0);
  const [popoverError, setPopoverError] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  const groupQuery = useQuery({
    queryKey: qk.packets.group(hash ?? ""),
    queryFn: ({ signal }) =>
      apiGet<PacketGroupData>(`/api/v1/packet-groups/${hash}`, {}, { signal }),
    enabled: !!hash,
  });
  const channelsQuery = useQuery({
    queryKey: qk.channels.list({ limit: 200 }),
    queryFn: ({ signal }) =>
      apiGet<ChannelsResponse>("/api/v1/channels", { limit: 200 }, {
        signal,
      }).catch(() => ({ items: [] as ChannelItem[] })),
  });

  const group = groupQuery.data ?? null;
  const channelNames = buildChannelNames(channelsQuery.data?.items || []);
  const notFound = groupQuery.error
    ? isNotFoundError(groupQuery.error)
    : false;
  const error =
    groupQuery.error && !isNotFoundError(groupQuery.error)
      ? groupQuery.error instanceof Error
        ? groupQuery.error.message
        : String(groupQuery.error)
      : null;

  useEffect(() => {
    const onDocClick = (ev: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(ev.target as Node)
      ) {
        setPopover(null);
      }
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setPopover(null);
    };
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const popoverHash = popover?.hash ?? null;
  useEffect(() => {
    if (!popoverHash) return;
    let cancelled = false;
    setPopoverNodes(null);
    setPopoverError(null);
    apiGet<NodesResponse>("/api/v1/nodes", {
      pubkey_prefix: popoverHash,
      sort: "name",
      order: "asc",
      limit: PATH_POPOVER_NODE_CAP,
    })
      .then((data) => {
        if (cancelled) return;
        const items = (data.items || [])
          .slice()
          .sort((a, b) =>
            resolveNodeName(a).localeCompare(resolveNodeName(b)),
          );
        setPopoverNodes(items);
        setPopoverTotal(data.total || 0);
      })
      .catch((e) => {
        if (cancelled || isAbortError(e)) return;
        setPopoverError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [popoverHash]);

  useLayoutEffect(() => {
    if (!popover || !popoverRef.current) return;
    const el = popoverRef.current;
    const margin = 8;
    const pw = el.offsetWidth || 256;
    const ph = el.offsetHeight || 0;
    let left = Math.min(popover.left, window.innerWidth - pw - margin);
    if (left < margin) left = margin;
    let top = popover.bottom + 4;
    if (
      top + ph + margin > window.innerHeight &&
      popover.top - ph - 4 > margin
    ) {
      top = popover.top - ph - 4;
    }
    setPopoverPos({
      left: left + window.scrollX,
      top: top + window.scrollY,
    });
  }, [popover, popoverNodes, popoverError]);

  const openPathPopover = (e: React.MouseEvent, pathHash: string) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopoverPos(null);
    setPopover({
      hash: pathHash,
      left: rect.left,
      bottom: rect.bottom,
      top: rect.top,
    });
  };

  const leaf = group?.packet_hash || group?.event_type || "";
  const receptions = group?.receptions ?? [];
  const sourcePrefix = group?.source_pubkey_prefix ?? null;
  const observerGroups = groupByObserver(receptions);
  const moreCount = popoverTotal - (popoverNodes?.length ?? 0);

  const channelDisplay = channelNameDisplay(
    channelNames,
    group?.channel_idx ?? null,
  );

  const receptionTime = (r: Reception) => <TimeAgo iso={r.received_at} />;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: t("entities.home"), to: "/" },
          { label: t("entities.packets"), to: "/packets" },
          { label: leaf || t("packets.detail_title") },
        ]}
      />

      {notFound && (
        <NotFoundState tone="warning" message={t("packets.not_found_retention")} />
      )}
      {error && <WarningBadge message={error} />}
      {!group && !notFound && !error && <Loading />}

      {group && (
        <>
          {group.redacted && <RedactedNotice />}
          <div className="card bg-base-100 shadow-sm">
            <div className="card-body">
              <DefinitionGrid>
                <Field label={t("common.time")}>
                  {formatDateTime(group.first_seen)}
                </Field>
                <Field label={t("packets.col_event_type")}>
                  {group.event_type || "—"}
                </Field>
                <Field label={t("entities.channel")}>{channelDisplay}</Field>
                <Field label={t("packets.col_source")}>
                  {group.source_pubkey_prefix ? (
                    <code className="font-mono text-xs">
                      {group.source_pubkey_prefix}
                    </code>
                  ) : (
                    <span className="opacity-50">—</span>
                  )}
                </Field>
                <Field label={t("packets.packet_hash")}>
                  {group.packet_hash ? (
                    <code className="font-mono text-xs">
                      {group.packet_hash}
                    </code>
                  ) : (
                    <span className="opacity-50">—</span>
                  )}
                </Field>
                <Field label={t("packets.packet_type")}>
                  {group.packet_type != null ? group.packet_type : "—"}
                </Field>
                <Field label={t("packets.payload_type")}>
                  {group.payload_type != null ? group.payload_type : "—"}
                </Field>
                <Field label={t("packets.col_route_type")}>
                  {group.route_type || "—"}
                </Field>
                <Field label={t("packets.receptions_count")}>
                  {formatNumber(group.reception_count)}{" "}
                  {group.reception_count === 1
                    ? t("packets.reception_singular")
                    : t("packets.reception_plural")}{" "}
                  · {formatNumber(group.observer_count)}{" "}
                  {t("common.observers").toLowerCase()}
                </Field>
              </DefinitionGrid>

              {receptions.length > 0 && (
                <div className="mt-6">
                  <h2 className="text-sm font-semibold uppercase opacity-60 mb-3">
                    {t("packets.receptions_title")}
                    <span className="ml-1 normal-case opacity-80">
                      ({formatNumber(group.reception_count)}{" "}
                      {group.reception_count === 1
                        ? t("packets.reception_singular")
                        : t("packets.reception_plural")}
                      , {formatNumber(group.observer_count)}{" "}
                      {t("common.observers").toLowerCase()})
                    </span>
                  </h2>
                  {[...observerGroups.entries()].map(([key, recs]) => {
                    const first = recs[0];
                    const displayName =
                      first.observer_tag_name ||
                      first.observer_name ||
                      (first.observed_by
                        ? first.observed_by.slice(0, 12) + "…"
                        : "—");
                    return (
                      <div key={key} className="mb-5">
                        <div className="text-sm font-medium mb-1">
                          {"\u{1F4E1}"}{" "}
                          {first.observed_by ? (
                            <Link
                              to={`/nodes/${first.observed_by}`}
                              className="link link-hover"
                            >
                              {displayName}
                            </Link>
                          ) : (
                            displayName
                          )}
                          {recs.length > 1 && (
                            <span className="text-xs opacity-50 ml-1">
                              ({formatNumber(recs.length)}{" "}
                              {t("packets.reception_plural")})
                            </span>
                          )}
                        </div>

                        <div className="lg:hidden space-y-2">
                          {recs.map((r) => (
                            <div
                              key={r.packet_id}
                              className="rounded-box bg-base-200/60 p-3"
                            >
                              <div className="mb-2">
                                <PathFlow
                                  reception={r}
                                  sourcePrefix={sourcePrefix}
                                  onBadgeOpen={openPathPopover}
                                />
                              </div>
                              <div className="grid grid-cols-3 gap-2">
                                <Stat
                                  label={t("common.time")}
                                  value={receptionTime(r)}
                                />
                                <Stat
                                  label={t("common.hops")}
                                  value={r.path_len != null ? r.path_len : "—"}
                                />
                                <Stat
                                  label={t("common.snr_db")}
                                  value={
                                    r.snr != null
                                      ? Number(r.snr).toFixed(1)
                                      : "—"
                                  }
                                />
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="hidden lg:block overflow-x-auto">
                          <table className="table table-xs table-fixed w-full">
                            <thead>
                              <tr>
                                <th>{t("packets.col_path")}</th>
                                <th className="w-16 text-right">
                                  {t("common.hops")}
                                </th>
                                <th className="w-20 text-right">
                                  {t("common.snr_db")}
                                </th>
                                <th className="w-32 text-right">
                                  {t("common.time")}
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {recs.map((r) => (
                                <tr key={r.packet_id}>
                                  <td className="whitespace-normal align-top">
                                    <PathFlow
                                      reception={r}
                                      sourcePrefix={sourcePrefix}
                                      onBadgeOpen={openPathPopover}
                                    />
                                  </td>
                                  <td className="w-16 text-right text-sm align-top">
                                    {r.path_len != null ? r.path_len : "—"}
                                  </td>
                                  <td className="w-20 text-right text-sm align-top">
                                    {r.snr != null
                                      ? Number(r.snr).toFixed(1)
                                      : "—"}
                                  </td>
                                  <td className="w-32 text-right text-xs opacity-60 align-top whitespace-nowrap">
                                    {receptionTime(r)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {!group.redacted && group.raw_hex && (
                <RawHexBlock hex={group.raw_hex} />
              )}

              {!group.redacted && group.decoded != null && (
                <DecodedJsonBlock value={group.decoded} />
              )}
            </div>
          </div>
        </>
      )}

      {popover &&
        createPortal(
          <div
            ref={popoverRef}
            className="absolute z-[1000] w-64 max-w-[90vw] max-h-[60vh] overflow-y-auto bg-base-100 rounded-box shadow-lg border border-base-300"
            style={{
              left: popoverPos?.left ?? -9999,
              top: popoverPos?.top ?? -9999,
            }}
          >
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-base-200 sticky top-0 bg-base-100 rounded-t-box">
              <span className="text-xs font-semibold uppercase opacity-70">
                {t("packets.path_nodes_title", { hash: popover.hash })}
              </span>
              <button
                className="btn btn-xs btn-ghost btn-circle"
                aria-label={t("common.close")}
                onClick={() => setPopover(null)}
              >
                ✕
              </button>
            </div>
            <div>
              {popoverError ? (
                <div className="p-3">
                  <WarningBadge message={popoverError} />
                </div>
              ) : popoverNodes === null ? (
                <div className="p-3">
                  <Loading />
                </div>
              ) : popoverNodes.length === 0 ? (
                <div className="px-3 py-4 text-sm opacity-60 text-center">
                  {t("packets.path_no_nodes")}
                </div>
              ) : (
                <ul className="menu menu-sm w-full">
                  {popoverNodes.map((n) => (
                    <li key={n.public_key}>
                      <Link
                        to={`/nodes/${n.public_key}`}
                        onClick={() => setPopover(null)}
                        className="flex flex-col items-start gap-0"
                      >
                        <span className="text-sm">{resolveNodeName(n)}</span>
                        <span className="font-mono text-xs opacity-50">
                          {truncateKey(n.public_key, 16)}
                        </span>
                      </Link>
                    </li>
                  ))}
                  {moreCount > 0 && (
                    <li>
                      <Link
                        to={`/nodes?pubkey_prefix=${popover.hash}`}
                        onClick={() => setPopover(null)}
                        className="text-xs opacity-70"
                      >
                        {t("packets.path_nodes_more", {
                          count: formatNumber(moreCount),
                        })}
                      </Link>
                    </li>
                  )}
                </ul>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
