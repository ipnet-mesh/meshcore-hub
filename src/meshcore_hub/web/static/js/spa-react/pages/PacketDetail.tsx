import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { useAppConfig } from "@/context/AppConfigContext";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiGet, isAbortError } from "@/utils/api";
import { useFormatDateTime } from "@/utils/format";
import { copyToClipboard } from "@/utils/clipboard";
import { Loading, WarningBadge } from "@/components/Alerts";
import { JsonTree } from "@/components/JsonTree";

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

interface ChannelItem {
  name: string;
  channel_hash: string;
}

interface ChannelsResponse {
  items: ChannelItem[];
}

function buildChannelNames(items: ChannelItem[]): Map<number, string> {
  const names = new Map<number, string>();
  for (const c of items) {
    const idx = parseInt(c.channel_hash, 16);
    if (!Number.isNaN(idx)) names.set(idx, c.name);
  }
  return names;
}

function isNotFoundError(e: unknown): boolean {
  return e instanceof Error && e.message.includes("404");
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 border-b border-base-200">
      <span className="text-xs uppercase opacity-60">{label}</span>
      <span className="text-sm">{children}</span>
    </div>
  );
}

export function PacketDetail() {
  const { t } = useTranslation();
  usePageTitle("packets.detail_title");
  const { id } = useParams();
  const config = useAppConfig();
  const { formatDateTime } = useFormatDateTime();

  const [packet, setPacket] = useState<PacketDetailData | null>(null);
  const [channelNames, setChannelNames] = useState<Map<number, string>>(
    new Map(),
  );
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setPacket(null);
    setNotFound(false);
    setError(null);
    Promise.all([
      apiGet<PacketDetailData>(`/api/v1/packets/${id}`, {}, {
        signal: controller.signal,
      }),
      apiGet<ChannelsResponse>("/api/v1/channels", { limit: 200 }, {
        signal: controller.signal,
      }).catch(() => ({ items: [] as ChannelItem[] })),
    ])
      .then(([p, channelsData]) => {
        setPacket(p);
        setChannelNames(buildChannelNames(channelsData.items || []));
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        if (isNotFoundError(e)) {
          setNotFound(true);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => controller.abort();
  }, [id]);

  const tz = config.timezone || "";
  const leaf = packet?.packet_hash || packet?.event_type || "";

  let channelDisplay: ReactNode = <span className="opacity-50">—</span>;
  if (packet && packet.channel_idx != null) {
    const name = channelNames.get(packet.channel_idx);
    channelDisplay = name
      ? `${name} (${packet.channel_idx})`
      : `${packet.channel_idx}`;
  }

  return (
    <div>
      <div className="breadcrumbs text-sm mb-4">
        <ul>
          <li>
            <Link to="/">{t("entities.home")}</Link>
          </li>
          <li>
            <Link to="/packets">{t("entities.packets")}</Link>
          </li>
          <li>{leaf || t("packets.detail_title")}</li>
        </ul>
      </div>

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">{t("packets.detail_title")}</h1>
        {tz && tz !== "UTC" && <span className="text-sm opacity-60">{tz}</span>}
      </div>

      {notFound && (
        <div role="alert" className="alert alert-error">
          {t("common.entity_not_found_details", {
            entity: t("entities.packet").toLowerCase(),
          })}
        </div>
      )}
      {error && <WarningBadge message={error} />}
      {!packet && !notFound && !error && <Loading />}

      {packet && (
        <>
          {packet.redacted && (
            <div className="alert alert-warning mb-4">
              {"\u{1F512}"} {t("packets.redacted_notice")}
            </div>
          )}
          <div className="card bg-base-100 shadow-sm">
            <div className="card-body">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
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
              </div>

              {!packet.redacted && (
                <div className="mt-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs uppercase opacity-60">
                      {t("packets.col_raw")}
                    </span>
                    {packet.raw_hex && (
                      <button
                        className="btn btn-xs btn-ghost"
                        onClick={(e) => copyToClipboard(e, packet.raw_hex!)}
                      >
                        {t("packets.copy_raw")}
                      </button>
                    )}
                  </div>
                  <pre className="bg-base-200 rounded p-3 text-xs overflow-x-auto whitespace-pre-wrap break-all">
                    {packet.raw_hex || "—"}
                  </pre>
                </div>
              )}

              {!packet.redacted && packet.decoded != null && (
                <div className="mt-4">
                  <span className="text-xs uppercase opacity-60">
                    {t("packets.decoded")}
                  </span>
                  <div className="bg-base-200 rounded p-3">
                    <JsonTree value={packet.decoded} openDepth={1} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
