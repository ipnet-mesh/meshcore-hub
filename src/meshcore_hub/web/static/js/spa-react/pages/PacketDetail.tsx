import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { useFormatDateTime } from "@/utils/format";
import { Loading, WarningBadge } from "@/components/Alerts";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { NotFoundState } from "@/components/NotFoundState";
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

interface PacketDetailData {
  packet_hash: string | null;
  event_type: string | null;
  channel_idx: number | null;
  observed_by: string | null;
  observer_name: string | null;
  observer_tag_name: string | null;
  source_pubkey_prefix: string | null;
  packet_type: number | null;
  payload_type: number | null;
  route_type: string | null;
  snr: number | null;
  path_len: number | null;
  received_at: string | null;
  redacted: boolean;
  raw_hex: string | null;
  decoded: unknown;
}

interface ChannelsResponse {
  items: ChannelItem[];
}

export function PacketDetail() {
  const { t } = useTranslation();
  usePageTitle("packets.detail_title");
  const { id } = useParams();
  const { formatDateTime } = useFormatDateTime();

  const packetQuery = useQuery({
    queryKey: qk.packets.detail(id ?? ""),
    queryFn: ({ signal }) =>
      apiGet<PacketDetailData>(`/api/v1/packets/${id}`, {}, { signal }),
    enabled: !!id,
  });
  const channelsQuery = useQuery({
    queryKey: qk.channels.list({ limit: 200 }),
    queryFn: ({ signal }) =>
      apiGet<ChannelsResponse>("/api/v1/channels", { limit: 200 }, {
        signal,
      }).catch(() => ({ items: [] as ChannelItem[] })),
  });

  const packet = packetQuery.data ?? null;
  const channelNames = buildChannelNames(channelsQuery.data?.items || []);
  const notFound = packetQuery.error
    ? isNotFoundError(packetQuery.error)
    : false;
  const error =
    packetQuery.error && !isNotFoundError(packetQuery.error)
      ? packetQuery.error instanceof Error
        ? packetQuery.error.message
        : String(packetQuery.error)
      : null;

  const leaf = packet?.packet_hash || packet?.event_type || "";
  const channelDisplay = channelNameDisplay(channelNames, packet?.channel_idx ?? null);

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
        <NotFoundState
          message={t("common.entity_not_found_details", {
            entity: t("entities.packet").toLowerCase(),
          })}
        />
      )}
      {error && <WarningBadge message={error} />}
      {!packet && !notFound && !error && <Loading />}

      {packet && (
        <>
          {packet.redacted && <RedactedNotice />}
          <div className="card bg-base-100 shadow-sm">
            <div className="card-body">
              <DefinitionGrid>
                <Field label={t("common.time")}>
                  {formatDateTime(packet.received_at)}
                </Field>
                <Field label={t("common.observers")}>
                  {packet.observed_by ? (
                    <Link
                      to={`/nodes/${packet.observed_by}`}
                      className="link link-hover"
                    >
                      {packet.observer_tag_name ||
                        packet.observer_name ||
                        packet.observed_by}
                    </Link>
                  ) : (
                    <span className="opacity-50">—</span>
                  )}
                </Field>
                <Field label={t("packets.col_event_type")}>
                  {packet.event_type || "—"}
                </Field>
                <Field label={t("entities.channel")}>{channelDisplay}</Field>
                <Field label={t("packets.col_source")}>
                  {packet.source_pubkey_prefix ? (
                    <code className="font-mono text-xs">
                      {packet.source_pubkey_prefix}
                    </code>
                  ) : (
                    <span className="opacity-50">—</span>
                  )}
                </Field>
                <Field label={t("packets.packet_hash")}>
                  {packet.packet_hash ? (
                    <code className="font-mono text-xs">
                      {packet.packet_hash}
                    </code>
                  ) : (
                    <span className="opacity-50">—</span>
                  )}
                </Field>
                <Field label={t("packets.packet_type")}>
                  {packet.packet_type != null ? packet.packet_type : "—"}
                </Field>
                <Field label={t("packets.payload_type")}>
                  {packet.payload_type != null ? packet.payload_type : "—"}
                </Field>
                <Field label={t("packets.col_route_type")}>
                  {packet.route_type || "—"}
                </Field>
                <Field label={t("common.snr_db")}>
                  {packet.snr != null ? Number(packet.snr).toFixed(1) : "—"}
                </Field>
                <Field label={t("common.hops")}>
                  {packet.path_len != null ? packet.path_len : "—"}
                </Field>
              </DefinitionGrid>

              {!packet.redacted && <RawHexBlock hex={packet.raw_hex} />}

              {!packet.redacted && packet.decoded != null && (
                <DecodedJsonBlock value={packet.decoded} />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
