import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import {
  getChannelLabelsMap,
  resolveChannelLabel,
  useAppConfig,
} from "@/context/AppConfigContext";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { useFormatDateTime } from "@/utils/format";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { Pagination } from "@/components/Pagination";
import {
  FilterForm,
  FilterField,
  FilterSelect,
  autoSubmit,
} from "@/components/FilterForm";
import { MobileSortSelect, SortableTableHeader } from "@/components/SortableTable";
import {
  ObserverFilterBadges,
  ObserverIcons,
  getDisabledObserverAreas,
  toggleObserverArea,
} from "@/components/ObserverBadges";
import { Loading } from "@/components/Alerts";
import { ListToolbar } from "@/components/ListToolbar";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, EmptyRow } from "@/components/EmptyState";

interface ObserverInfo {
  node_id?: string;
  public_key: string;
  name?: string;
  tag_name?: string;
  snr?: number | null;
  observed_at?: string;
}

interface Message {
  message_type: string;
  text: string;
  channel_idx?: number | null;
  channel_name?: string | null;
  signature?: string | null;
  pubkey_prefix?: string | null;
  sender_name?: string | null;
  sender_tag_name?: string | null;
  observed_by?: string | null;
  observer_name?: string | null;
  observer_tag_name?: string | null;
  received_at: string;
  packet_hash?: string | null;
  spam_score?: number | null;
  observers?: ObserverInfo[];
}

interface NodeItem {
  public_key: string;
  tags?: { key: string; value: string | null }[];
}

interface ChannelItem {
  channel_hash: string;
  name: string;
}

interface ListResponse<T> {
  items?: T[];
  total?: number;
}

function parseSenderFromText(text: string | null): {
  sender: string | null;
  text: string;
} {
  if (!text || typeof text !== "string") {
    return { sender: null, text: text || "-" };
  }
  const patterns = [
    /^\s*ack\s+@\[(.+?)\]\s*:\s*([\s\S]+)$/i,
    /^\s*@\[(.+?)\]\s*:\s*([\s\S]+)$/i,
    /^\s*ack\s+([^:|\n]{1,80})\s*:\s*([\s\S]+)$/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) continue;
    const sender = (match[1] || "").trim();
    const remaining = (match[2] || "").trim();
    if (!sender) continue;
    return { sender, text: remaining || text };
  }
  return { sender: null, text };
}

function collapseNewlines(text: string | null): string | null {
  if (!text || typeof text !== "string") return text;
  return text.replace(/\s*\n\s*/g, " ");
}

function channelInfo(
  msg: Message,
  channelLabels: Map<number, string>,
  fallbackLabel: string,
): { label: string | null; text: string } {
  if (msg.message_type !== "channel") {
    return { label: null, text: msg.text || "-" };
  }
  const rawText = msg.text || "";
  const match = rawText.match(/^\[([^\]]+)\]\s+([\s\S]*)$/);
  if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
    const knownLabel = resolveChannelLabel(msg.channel_idx, channelLabels);
    if (knownLabel) {
      return {
        label: knownLabel,
        text: match ? match[2] || "-" : rawText || "-",
      };
    }
  }
  if (msg.channel_name) {
    return { label: msg.channel_name, text: msg.text || "-" };
  }
  if (match) {
    return { label: match[1], text: match[2] || "-" };
  }
  if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
    const knownLabel = resolveChannelLabel(msg.channel_idx, channelLabels);
    return { label: knownLabel || `Ch ${msg.channel_idx}`, text: rawText || "-" };
  }
  return { label: fallbackLabel, text: rawText || "-" };
}

function messageTextWithSender(msg: Message, text: string): string {
  const parsed = parseSenderFromText(text || "-");
  const explicitSender =
    msg.sender_tag_name ||
    msg.sender_name ||
    (msg.pubkey_prefix || "").slice(0, 12) ||
    null;
  const sender = explicitSender || parsed.sender;
  const body = collapseNewlines((parsed.text || text || "-").trim()) || "-";
  if (!sender) return body;
  if (body.toLowerCase().startsWith(`${sender.toLowerCase()}:`)) return body;
  return `${sender}: ${body}`;
}

function dedupeBySignature(items: Message[]): Message[] {
  const deduped: Message[] = [];
  const bySignature = new Map<string, Message>();

  for (const msg of items) {
    const signature =
      typeof msg.signature === "string"
        ? msg.signature.trim().toUpperCase()
        : "";
    const canDedupe = msg.message_type === "channel" && signature.length >= 8;
    if (!canDedupe) {
      deduped.push(msg);
      continue;
    }

    const existing = bySignature.get(signature);
    if (!existing) {
      const clone: Message = {
        ...msg,
        observers: [...(msg.observers ?? [])],
      };
      bySignature.set(signature, clone);
      deduped.push(clone);
      continue;
    }

    const combined = [...(existing.observers ?? []), ...(msg.observers ?? [])];
    const seenReceivers = new Set<string>();
    existing.observers = combined.filter((recv) => {
      const key =
        recv?.public_key ||
        recv?.node_id ||
        `${recv?.observed_at ?? ""}:${recv?.snr ?? ""}`;
      if (seenReceivers.has(key)) return false;
      seenReceivers.add(key);
      return true;
    });

    if (!existing.observed_by && msg.observed_by)
      existing.observed_by = msg.observed_by;
    if (!existing.observer_name && msg.observer_name)
      existing.observer_name = msg.observer_name;
    if (!existing.observer_tag_name && msg.observer_tag_name)
      existing.observer_tag_name = msg.observer_tag_name;
    if (!existing.pubkey_prefix && msg.pubkey_prefix)
      existing.pubkey_prefix = msg.pubkey_prefix;
    if (!existing.sender_name && msg.sender_name)
      existing.sender_name = msg.sender_name;
    if (!existing.sender_tag_name && msg.sender_tag_name)
      existing.sender_tag_name = msg.sender_tag_name;
    if (!existing.channel_name && msg.channel_name)
      existing.channel_name = msg.channel_name;
    if (
      existing.channel_name === "Public" &&
      msg.channel_name &&
      msg.channel_name !== "Public"
    ) {
      existing.channel_name = msg.channel_name;
    }
    if (existing.channel_idx === null || existing.channel_idx === undefined) {
      if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
        existing.channel_idx = msg.channel_idx;
      }
    } else if (
      existing.channel_idx === 17 &&
      msg.channel_idx !== null &&
      msg.channel_idx !== undefined &&
      msg.channel_idx !== 17
    ) {
      existing.channel_idx = msg.channel_idx;
    }
  }

  return deduped;
}

export function Messages() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const config = useAppConfig();
  const { formatDateTime, formatDateTimeShort } = useFormatDateTime();
  usePageTitle("entities.messages");

  const messageType = searchParams.get("message_type") ?? "";
  const channelIdx = searchParams.get("channel_idx") ?? "";
  const includeSpamParam = searchParams.get("include_spam") === "true";
  const page = parseInt(searchParams.get("page") ?? "", 10) || 1;
  const limit = parseInt(searchParams.get("limit") ?? "", 10) || 50;
  const sort = searchParams.get("sort") ?? "time";
  const order = searchParams.get("order") ?? "desc";
  const offset = (page - 1) * limit;

  const features = config.features ?? {};
  const packetsEnabled = features.packets !== false;
  const spamEnabled = features.spam === true;
  const includeSpam = spamEnabled && includeSpamParam;
  const spamThreshold =
    typeof config.spam_score_threshold === "number"
      ? config.spam_score_threshold
      : 0.65;

  const [disabledAreas, setDisabledAreas] = useState<Set<string>>(() =>
    getDisabledObserverAreas(),
  );
  const [filterOpen, setFilterOpen] = useState(
    messageType !== "" || channelIdx !== "" || includeSpam,
  );

  const { paused, toggle, intervalSeconds, refetchInterval } =
    useAutoRefresh();

  const { data, error: queryError } = useQuery({
    queryKey: qk.messages.list({
      limit,
      offset,
      messageType,
      channelIdx,
      includeSpam,
      sort,
      order,
      channelLabels: config.channel_labels,
      disabledAreas: [...disabledAreas].sort(),
    }),
    refetchInterval,
    queryFn: async ({ signal }) => {
      const [nodesData, channelsData] = await Promise.all([
        apiGet<ListResponse<NodeItem>>(
          "/api/v1/nodes",
          { limit: 500, observer: true },
          { signal },
        ),
        apiGet<ListResponse<ChannelItem>>("/api/v1/channels", {}, { signal }),
      ]);

      const builtin = getChannelLabelsMap(config);
      const custom = new Map(
        (channelsData.items ?? [])
          .map((ch): [number, string] => [
            parseInt(ch.channel_hash, 16),
            ch.name,
          ])
          .filter(([idx]) => Number.isInteger(idx)),
      );
      const channelLabels = new Map([...builtin, ...custom]);

      const areaMap = new Map<string, string[]>();
      for (const n of nodesData.items ?? []) {
        const area = n.tags?.find((tg) => tg.key === "area")?.value;
        if (!area || !area.trim()) continue;
        const key = area.trim();
        if (!areaMap.has(key)) areaMap.set(key, []);
        areaMap.get(key)!.push(n.public_key);
      }
      const sortedAreas = [...areaMap.keys()].sort((a, b) =>
        a.toLowerCase().localeCompare(b.toLowerCase()),
      );

      const observerFilterActive = sortedAreas.some((a) =>
        disabledAreas.has(a),
      );
      const apiParams: Record<string, unknown> = {
        limit,
        offset,
        message_type: messageType,
        channel_idx: channelIdx,
        sort,
        order,
      };
      if (observerFilterActive) {
        apiParams.observed_by = sortedAreas
          .filter((a) => !disabledAreas.has(a))
          .flatMap((a) => areaMap.get(a) ?? []);
      }
      if (includeSpam) apiParams.include_spam = true;

      const messagesData = await apiGet<ListResponse<Message>>(
        "/api/v1/messages",
        apiParams,
        { signal },
      );
      return {
        items: dedupeBySignature(messagesData.items ?? []),
        total: messagesData.total ?? 0,
        sortedAreas,
        builtinLabels: builtin,
        customLabels: custom,
        channelLabels,
      };
    },
  });
  const error = queryError ? queryError.message : null;

  const items = data?.items ?? null;
  const total = data?.total ?? null;
  const sortedAreas = data?.sortedAreas ?? [];
  const builtinLabels = data?.builtinLabels ?? new Map<number, string>();
  const customLabels = data?.customLabels ?? new Map<number, string>();
  const channelLabels = data?.channelLabels ?? new Map<number, string>();

  const handleObserverToggle = (area: string) => {
    const updated = toggleObserverArea(area, sortedAreas.length);
    setDisabledAreas(new Set(updated));
    if (page > 1) {
      const sp = new URLSearchParams(searchParams);
      sp.delete("page");
      const qs = sp.toString();
      navigate(qs ? `/messages?${qs}` : "/messages");
    }
  };

  const senderBlock = (msg: Message, emphasize = false): ReactNode => {
    const senderName = msg.sender_tag_name || msg.sender_name;
    if (senderName) {
      return emphasize ? (
        <span className="font-medium">{senderName}</span>
      ) : (
        <>{senderName}</>
      );
    }
    const prefix = (msg.pubkey_prefix || "").slice(0, 12);
    if (prefix) return <span className="font-mono text-xs">{prefix}</span>;
    return <span className="opacity-50">-</span>;
  };

  const spamBadge = (msg: Message): ReactNode => {
    if (
      !spamEnabled ||
      msg.spam_score == null ||
      msg.spam_score < spamThreshold
    ) {
      return null;
    }
    return (
      <span
        className="badge badge-warning badge-sm"
        title={`${t("messages.spam.badge")} ${msg.spam_score.toFixed(2)}`}
      >
        {t("messages.spam.badge")}
      </span>
    );
  };

  const renderReceivers = (msg: Message, variant: "mobile" | "desktop") => {
    if (msg.observers && msg.observers.length >= 1) {
      return <ObserverIcons observers={msg.observers} />;
    }
    if (msg.observed_by) {
      return (
        <span className={`opacity-50 ${variant === "mobile" ? "text-xs" : ""}`}>
          {"\u{1F4E1}"}
        </span>
      );
    }
    return variant === "desktop" ? <span className="opacity-50">-</span> : null;
  };

  const totalPages = total !== null ? Math.ceil(total / limit) : 0;
  const headerParams: Record<string, string> = {
    message_type: messageType,
    channel_idx: channelIdx,
    limit: String(limit),
  };
  if (includeSpam) headerParams.include_spam = "true";
  const paginationParams: Record<string, string> = {
    ...headerParams,
    sort,
    order,
  };
  const emptyMessage = t("common.no_entity_found", {
    entity: t("entities.messages").toLowerCase(),
  });

  return (
    <>
      <PageHeader title={t("entities.messages")} />

      <ListToolbar
        total={total}
        error={error}
        autoRefresh={{ paused, onToggle: toggle, intervalSeconds }}
        filterToggle={{ open: filterOpen, onChange: () => setFilterOpen((o) => !o) }}
      />

      {filterOpen && (
        <div className="mb-4">
          <FilterForm basePath="/messages">
            <FilterField label={t("common.type")}>
              <FilterSelect
                name="message_type"
                key={`message_type-${messageType}`}
                defaultValue={messageType}
                onChange={autoSubmit}
                options={[
                  { value: "", label: t("common.all_types") },
                  { value: "contact", label: t("messages.type_direct") },
                  { value: "channel", label: t("messages.type_channel") },
                ]}
              />
            </FilterField>
            <FilterField label={t("entities.channel")}>
              <select
                name="channel_idx"
                key={`channel_idx-${channelIdx}`}
                defaultValue={channelIdx}
                className="select select-sm"
                onChange={autoSubmit}
              >
                <option value="">{t("common.all_channels")}</option>
                {builtinLabels.size > 0 && (
                  <optgroup label={t("channels.optgroup_standard")}>
                    {[...builtinLabels.entries()].map(([idx, label]) => (
                      <option key={idx} value={idx}>
                        {label}
                      </option>
                    ))}
                  </optgroup>
                )}
                {customLabels.size > 0 && (
                  <optgroup label={t("channels.optgroup_custom")}>
                    {[...customLabels.entries()].map(([idx, label]) => (
                      <option key={idx} value={idx}>
                        {label}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </FilterField>
            {spamEnabled && (
              <FilterField label={t("messages.spam.filter_label")}>
                <label className="label cursor-pointer justify-start gap-2 py-1">
                  <input
                    type="checkbox"
                    name="include_spam"
                    value="true"
                    className="checkbox checkbox-sm"
                    defaultChecked={includeSpam}
                    onChange={autoSubmit}
                  />
                  <span className="text-sm">{t("messages.spam.show")}</span>
                </label>
              </FilterField>
            )}
          </FilterForm>
        </div>
      )}

      {items === null ? (
        <Loading />
      ) : (
        <>
          <ObserverFilterBadges
            areas={sortedAreas}
            disabled={disabledAreas}
            onToggle={handleObserverToggle}
            extraClass="hidden lg:flex mb-4"
          />

          <MobileSortSelect
            currentSort={sort}
            currentOrder={order}
            basePath="/messages"
            params={headerParams}
            options={[
              { value: "time:desc", label: t("messages.sort.newest") },
              { value: "time:asc", label: t("messages.sort.oldest") },
              { value: "type:asc", label: t("messages.sort.type_az") },
              { value: "type:desc", label: t("messages.sort.type_za") },
              { value: "from:asc", label: t("messages.sort.from_az") },
              { value: "from:desc", label: t("messages.sort.from_za") },
              { value: "message:asc", label: t("messages.sort.message_az") },
              {
                value: "message:desc",
                label: t("messages.sort.message_za"),
              },
            ]}
          />

          <ObserverFilterBadges
            areas={sortedAreas}
            disabled={disabledAreas}
            onToggle={handleObserverToggle}
            extraClass="flex lg:hidden mb-4"
          />

          <div className="lg:hidden space-y-3">
            {items.length === 0 ? (
              <EmptyState>{emptyMessage}</EmptyState>
            ) : (
              items.map((msg, idx) => {
                const isChannel = msg.message_type === "channel";
                const typeIcon = isChannel ? "\u{1F4FB}" : "\u{1F464}";
                const typeTitle = isChannel
                  ? t("messages.type_channel")
                  : t("messages.type_contact");
                const chInfo = channelInfo(
                  msg,
                  channelLabels,
                  t("messages.type_channel"),
                );
                const displayMessage = messageTextWithSender(
                  msg,
                  chInfo.text,
                );
                const fromPrimary = isChannel ? (
                  <span className="font-medium">
                    {chInfo.label || t("messages.type_channel")}
                  </span>
                ) : (
                  senderBlock(msg)
                );
                const detailUrl =
                  packetsEnabled && msg.packet_hash
                    ? `/packets/hash/${msg.packet_hash}`
                    : null;
                return (
                  <div
                    key={`${msg.signature ?? ""}-${msg.received_at}-${idx}`}
                    className={`card bg-base-100 shadow-sm ${detailUrl ? "cursor-pointer" : ""}`}
                    onClick={
                      detailUrl ? () => navigate(detailUrl) : undefined
                    }
                  >
                    <div className="card-body p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className="text-lg flex-shrink-0"
                            title={typeTitle}
                          >
                            {typeIcon}
                          </span>
                          <div className="min-w-0">
                            <div className="font-medium text-sm truncate">
                              {fromPrimary}
                            </div>
                            <div className="text-xs opacity-60 flex items-center gap-1">
                              {formatDateTimeShort(msg.received_at)}
                              {spamBadge(msg)}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {renderReceivers(msg, "mobile")}
                        </div>
                      </div>
                      <p className="text-sm mt-2 break-words whitespace-pre-wrap">
                        {displayMessage}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow-sm">
            <table className="table table-zebra">
              <thead>
                <tr>
                  <SortableTableHeader
                    label={t("common.type")}
                    sortKey="type"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/messages"
                    params={headerParams}
                  />
                  <SortableTableHeader
                    label={t("common.time")}
                    sortKey="time"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/messages"
                    params={headerParams}
                  />
                  <SortableTableHeader
                    label={t("common.from")}
                    sortKey="from"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/messages"
                    params={headerParams}
                  />
                  <SortableTableHeader
                    label={t("entities.message")}
                    sortKey="message"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/messages"
                    params={headerParams}
                  />
                  <th>{t("common.observers")}</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <EmptyRow colSpan={5}>{emptyMessage}</EmptyRow>
                ) : (
                  items.map((msg, idx) => {
                    const isChannel = msg.message_type === "channel";
                    const typeIcon = isChannel ? "\u{1F4FB}" : "\u{1F464}";
                    const typeTitle = isChannel
                      ? t("messages.type_channel")
                      : t("messages.type_contact");
                    const chInfo = channelInfo(
                      msg,
                      channelLabels,
                      t("messages.type_channel"),
                    );
                    const displayMessage = messageTextWithSender(
                      msg,
                      chInfo.text,
                    );
                    const fromPrimary = isChannel ? (
                      <span className="font-medium">
                        {chInfo.label || t("messages.type_channel")}
                      </span>
                    ) : (
                      senderBlock(msg, true)
                    );
                    const detailUrl =
                      packetsEnabled && msg.packet_hash
                        ? `/packets/hash/${msg.packet_hash}`
                        : null;
                    return (
                      <tr
                        key={`${msg.signature ?? ""}-${msg.received_at}-${idx}`}
                        className={detailUrl ? "hover cursor-pointer" : ""}
                        onClick={
                          detailUrl ? () => navigate(detailUrl) : undefined
                        }
                      >
                        <td className="text-lg" title={typeTitle}>
                          {typeIcon}
                        </td>
                        <td className="text-sm whitespace-nowrap">
                          {formatDateTime(msg.received_at)}
                        </td>
                        <td className="text-sm whitespace-nowrap">
                          <div>{fromPrimary}</div>
                        </td>
                        <td className="break-words max-w-md">
                          <div className="flex items-start gap-2">
                            <span style={{ whiteSpace: "pre-wrap" }}>
                              {displayMessage}
                            </span>
                            {spamBadge(msg)}
                          </div>
                        </td>
                        <td>{renderReceivers(msg, "desktop")}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            basePath="/messages"
            params={paginationParams}
          />
        </>
      )}
    </>
  );
}
