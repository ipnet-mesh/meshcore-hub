import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useAppConfig } from "@/context/AppConfigContext";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { formatNumber, useFormatDateTime } from "@/utils/format";
import { Pagination } from "@/components/Pagination";
import { FilterForm, FilterField } from "@/components/FilterForm";
import {
  MobileSortSelect,
  SortableTableHeader,
} from "@/components/SortableTable";
import { Loading } from "@/components/Alerts";
import { ListToolbar } from "@/components/ListToolbar";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, EmptyRow } from "@/components/EmptyState";
import { IconPath, IconRuler, IconSatelliteDish } from "@/components/icons";

const EVENT_TYPES = [
  "advertisement",
  "channel_msg_recv",
  "contact_msg_recv",
  "trace_data",
  "telemetry_response",
  "path_updated",
  "status_response",
  "req",
  "response",
  "ack",
  "encrypted_direct",
  "encrypted_channel",
  "grp_data",
  "anon_req",
  "multipart",
  "control",
  "raw_custom",
  "advert",
  "path",
  "trace",
  "letsmesh_packet",
];

interface PacketGroupItem {
  packet_hash: string | null;
  event_type: string | null;
  channel_idx: number | null;
  path_hash_bytes: number | null;
  reception_count: number | null;
  observer_count: number | null;
  first_seen: string | null;
  redacted?: boolean;
  receptions?: { packet_id: string }[];
}

interface PacketGroupsResponse {
  items: PacketGroupItem[];
  total: number;
}

interface ChannelItem {
  name: string;
  channel_hash: string;
}

interface ChannelsResponse {
  items: ChannelItem[];
}

interface ChannelEntry {
  idx: number;
  name: string;
}

function buildChannelList(items: ChannelItem[]): ChannelEntry[] {
  return items
    .map((c) => ({ name: c.name, idx: parseInt(c.channel_hash, 16) }))
    .filter((c) => !Number.isNaN(c.idx));
}

function packetUrl(p: PacketGroupItem): string {
  if (p.packet_hash) return `/packets/hash/${p.packet_hash}`;
  if (p.receptions && p.receptions.length > 0)
    return `/packets/${p.receptions[0].packet_id}`;
  return "/packets";
}

function ChannelLabel({
  packet,
  channelNames,
}: {
  packet: PacketGroupItem;
  channelNames: Map<number, string>;
}) {
  const { t } = useTranslation();
  if (packet.channel_idx == null) return <span className="opacity-50">—</span>;
  const name = channelNames.get(packet.channel_idx);
  const text = name ? `${name} (${packet.channel_idx})` : `${packet.channel_idx}`;
  return (
    <>
      {text}
      {packet.redacted && (
        <>
          {" "}
          <span className="opacity-60" title={t("packets.redacted_title")}>
            {"\u{1F512}"}
          </span>
        </>
      )}
    </>
  );
}

function ReceptionBadge({ packet }: { packet: PacketGroupItem }) {
  const { t } = useTranslation();
  const rc = packet.reception_count ?? 1;
  const oc = packet.observer_count ?? 1;
  const pb = packet.path_hash_bytes;
  const knownWidth = pb != null && pb > 0;
  const widthLabel = knownWidth
    ? t("packets.path_width_bytes", { count: pb })
    : t("packets.path_width_unknown");
  return (
    <span className="inline-flex items-center gap-1">
      <IconSatelliteDish className="h-4 w-4 opacity-70" />
      <span
        className="badge badge-sm badge-primary"
        title={t("common.observers")}
      >
        {formatNumber(oc)}
      </span>
      <span className="opacity-40" aria-hidden="true">
        ×
      </span>
      <IconPath className="h-4 w-4 opacity-70" />
      <span
        className="badge badge-sm badge-primary"
        title={t("packets.reception_plural")}
      >
        {formatNumber(rc)}
      </span>
      <span className="opacity-40" aria-hidden="true">
        @
      </span>
      <IconRuler className="h-4 w-4 opacity-70" />
      <span
        className={`badge badge-sm badge-primary ${knownWidth ? "" : "opacity-60"}`}
        title={t("packets.path_width_title")}
      >
        {widthLabel}
      </span>
    </span>
  );
}

export function Packets() {
  const { t } = useTranslation();
  usePageTitle("entities.packets");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const config = useAppConfig();
  const { formatDateTime, formatDateTimeShort } = useFormatDateTime();

  const search = searchParams.get("search") ?? "";
  const eventType = searchParams.get("event_type") ?? "";
  const channelIdx = searchParams.get("channel_idx") ?? "";
  const pathHashBytes = searchParams.get("path_hash_bytes") ?? "";
  const page = parseInt(searchParams.get("page") ?? "", 10) || 1;
  const limit = parseInt(searchParams.get("limit") ?? "", 10) || 20;
  const sort = searchParams.get("sort") ?? "time";
  const order = searchParams.get("order") ?? "desc";
  const offset = (page - 1) * limit;

  const hasActiveFilters =
    search !== "" ||
    eventType !== "" ||
    channelIdx !== "" ||
    pathHashBytes !== "";
  const [filterOpen, setFilterOpen] = useState(hasActiveFilters);

  const autoRefresh = useAutoRefresh();

  const { data, error: queryError } = useQuery({
    queryKey: qk.packets.groups({
      search,
      eventType,
      channelIdx,
      pathHashBytes,
      limit,
      offset,
      sort,
      order,
    }),
    refetchInterval: autoRefresh.refetchInterval,
    queryFn: async ({ signal }) => {
      const apiParams: Record<string, unknown> = {
        limit,
        offset,
        search,
        sort,
        order,
      };
      if (eventType) apiParams.event_type = eventType;
      if (channelIdx !== "") apiParams.channel_idx = channelIdx;
      if (pathHashBytes !== "") apiParams.path_hash_bytes = pathHashBytes;

      const [groupsData, channelsData] = await Promise.all([
        apiGet<PacketGroupsResponse>("/api/v1/packet-groups", apiParams, {
          signal,
        }),
        apiGet<ChannelsResponse>("/api/v1/channels", { limit: 200 }, {
          signal,
        }).catch(() => ({ items: [] as ChannelItem[] })),
      ]);

      return {
        packets: groupsData.items || [],
        total: groupsData.total || 0,
        channels: buildChannelList(channelsData.items || []),
      };
    },
  });
  const error = queryError ? queryError.message : null;

  const packets = data?.packets ?? null;
  const total = data?.total ?? 0;
  const channels = data?.channels ?? [];

  const channelNames = useMemo(
    () => new Map(channels.map((c) => [c.idx, c.name])),
    [channels],
  );

  const applyFilters = (overrides: Record<string, string>) => {
    const next = {
      search,
      event_type: eventType,
      channel_idx: channelIdx,
      path_hash_bytes: pathHashBytes,
      ...overrides,
    };
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) {
      if (v) params.set(k, v);
    }
    const qs = params.toString();
    navigate(qs ? `/packets?${qs}` : "/packets");
  };

  const totalPages = Math.ceil(total / limit);
  const filterParams: Record<string, string> = {
    search,
    event_type: eventType,
    channel_idx: channelIdx,
    path_hash_bytes: pathHashBytes,
    limit: String(limit),
  };
  const noneFound = t("common.no_entity_found", {
    entity: t("entities.packets").toLowerCase(),
  });

  return (
    <div>
      <PageHeader title={t("entities.packets")} />

      <ListToolbar
        total={packets !== null ? total : null}
        error={error}
        autoRefresh={{
          paused: autoRefresh.paused,
          onToggle: autoRefresh.toggle,
          intervalSeconds: autoRefresh.intervalSeconds,
        }}
        filterToggle={{ open: filterOpen, onChange: () => setFilterOpen((o) => !o) }}
      />

      {filterOpen && (
        <div className="mb-4">
          <FilterForm basePath="/packets">
            <FilterField label={t("common.search")}>
              <input
                type="text"
                name="search"
                defaultValue={search}
                placeholder={t("common.search_placeholder")}
                className="input input-sm w-80"
              />
            </FilterField>
            <FilterField
              label={t("packets.filter_event_type")}
              className="max-w-48"
            >
              <select
                name="event_type"
                className="select select-sm"
                value={eventType}
                onChange={(e) => applyFilters({ event_type: e.target.value })}
              >
                <option value="">{t("common.all_types")}</option>
                {EVENT_TYPES.map((et) => (
                  <option key={et} value={et}>
                    {et}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label={t("entities.channel")} className="max-w-48">
              <select
                name="channel_idx"
                className="select select-sm"
                value={channelIdx}
                onChange={(e) => applyFilters({ channel_idx: e.target.value })}
              >
                <option value="">{t("common.all_channels")}</option>
                {channels.map((c) => (
                  <option key={c.idx} value={c.idx}>
                    {c.name} ({c.idx})
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField
              label={t("packets.filter_path_width")}
              className="max-w-48"
            >
              <select
                name="path_hash_bytes"
                className="select select-sm"
                value={pathHashBytes}
                onChange={(e) =>
                  applyFilters({ path_hash_bytes: e.target.value })
                }
              >
                <option value="">{t("common.all")}</option>
                {[1, 2, 3].map((w) => (
                  <option key={w} value={w}>
                    {t("packets.path_width_bytes", { count: w })}
                  </option>
                ))}
              </select>
            </FilterField>
          </FilterForm>
        </div>
      )}

      {packets === null ? (
        <Loading />
      ) : (
        <>
          <MobileSortSelect
            currentSort={sort}
            currentOrder={order}
            basePath="/packets"
            params={filterParams}
            options={[
              { value: "time:desc", label: t("packets.sort.newest") },
              { value: "time:asc", label: t("packets.sort.oldest") },
              { value: "event_type:asc", label: t("packets.sort.event_az") },
              {
                value: "reception_count:desc",
                label: t("packets.sort.receptions_high"),
              },
            ]}
          />

          <div className="lg:hidden space-y-3">
            {packets.length === 0 ? (
              <EmptyState>{noneFound}</EmptyState>
            ) : (
              packets.map((p, i) => (
                <Link
                  key={p.packet_hash ?? p.receptions?.[0]?.packet_id ?? i}
                  to={packetUrl(p)}
                  className="card bg-base-100 shadow-sm block"
                >
                  <div className="card-body p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-mono text-sm truncate">
                          {p.event_type || "—"}
                        </div>
                        <div className="text-xs opacity-60">
                          <ChannelLabel packet={p} channelNames={channelNames} />
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="text-xs opacity-60">
                          {formatDateTimeShort(p.first_seen)}
                        </div>
                        <div className="text-xs opacity-60">
                          <ReceptionBadge packet={p} />
                        </div>
                      </div>
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>

          <div className="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow-sm">
            <table className="table table-zebra">
              <thead>
                <tr>
                  <SortableTableHeader
                    label={t("common.time")}
                    sortKey="time"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/packets"
                    params={filterParams}
                  />
                  <th>{t("packets.packet_hash")}</th>
                  <th title={t("packets.receptions_title")}>
                    {t("packets.col_receptions")}
                  </th>
                  <SortableTableHeader
                    label={t("packets.col_event_type")}
                    sortKey="event_type"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/packets"
                    params={filterParams}
                  />
                  <th>{t("entities.channel")}</th>
                </tr>
              </thead>
              <tbody>
                {packets.length === 0 ? (
                  <EmptyRow colSpan={5}>{noneFound}</EmptyRow>
                ) : (
                  packets.map((p, i) => (
                    <tr
                      key={p.packet_hash ?? p.receptions?.[0]?.packet_id ?? i}
                      data-testid="list-row"
                      className="hover cursor-pointer"
                      onClick={() => navigate(packetUrl(p))}
                    >
                      <td className="text-sm whitespace-nowrap">
                        {formatDateTime(p.first_seen)}
                      </td>
                      <td>
                        {p.packet_hash ? (
                          <code className="font-mono text-xs">
                            {p.packet_hash}
                          </code>
                        ) : (
                          <span className="opacity-50">—</span>
                        )}
                      </td>
                      <td className="text-sm">
                        <ReceptionBadge packet={p} />
                      </td>
                      <td className="font-mono text-xs">
                        {p.event_type || "—"}
                      </td>
                      <td className="text-sm">
                        <ChannelLabel packet={p} channelNames={channelNames} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            basePath="/packets"
            params={{ ...filterParams, sort, order }}
          />
        </>
      )}
    </div>
  );
}
