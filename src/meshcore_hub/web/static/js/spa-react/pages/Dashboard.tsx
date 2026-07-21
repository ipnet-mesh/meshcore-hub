import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";

import { ErrorAlert, Loading } from "@/components/Alerts";
import {
  RoutesTrendChart,
  StackedBarChart,
  TrendLineChart,
} from "@/components/charts/Charts";
import { ObserverIcons } from "@/components/ObserverBadges";
import { RouteTypeBadge } from "@/components/RouteTypeBadge";
import {
  IconAdvertisements,
  IconChannel,
  IconMessages,
  IconNodes,
  IconPackets,
} from "@/components/icons";
import {
  getChannelLabelsMap,
  resolveChannelLabel,
  useAppConfig,
} from "@/context/AppConfigContext";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiGet, isAbortError } from "@/utils/api";
import {
  averageRouteTier,
  ChartColors,
  type ActivitySeries,
  type BreakdownBucket,
} from "@/utils/charts";
import { formatNumber, useFormatDateTime } from "@/utils/format";

interface DashboardStats {
  total_nodes: number;
  advertisements_7d: number;
  messages_7d: number;
  packets_7d: number;
}

interface PacketBreakdown {
  by_event_type: BreakdownBucket[];
  by_path_width: BreakdownBucket[];
}

interface RouteHealthEntry {
  date: string;
  quality: string | null;
  matched_count: number;
}

interface RouteOverviewItem {
  from_label: string;
  to_label: string;
  enabled: boolean;
  quality?: string | null;
  matched_count?: number;
  history?: RouteHealthEntry[];
}

interface RoutesOverview {
  days: number;
  routes: RouteOverviewItem[];
}

interface ObserverInfo {
  public_key: string;
  name?: string;
  tag_name?: string;
}

interface RecentAdvertisement {
  public_key: string;
  name?: string | null;
  tag_name?: string | null;
  route_type?: string | null;
  received_at: string;
  observed_by?: string | null;
  observers?: ObserverInfo[];
}

interface ChannelMessage {
  received_at: string;
  text?: string | null;
}

interface RecentActivity {
  recent_advertisements: RecentAdvertisement[];
  channel_messages: Record<string, ChannelMessage[]>;
}

interface ChannelsResponse {
  items?: { channel_hash: string; name: string }[];
}

interface DashboardData {
  stats: DashboardStats;
  recentActivity: RecentActivity;
  advertActivity: ActivitySeries | null;
  messageActivity: ActivitySeries | null;
  nodeCount: ActivitySeries | null;
  packetActivity: ActivitySeries | null;
  packetBreakdown: PacketBreakdown;
  routesOverview: RoutesOverview | null;
  channelsData: ChannelsResponse;
}

const QUALITY_COLORS: Record<string, string> = {
  clear: "oklch(0.72 0.17 145)",
  marginal: "oklch(0.75 0.18 85)",
  failing: "oklch(0.62 0.24 25)",
  no_coverage: "oklch(0.65 0.15 250)",
  disabled: "oklch(0.55 0 0)",
};

function qualityColor(quality: string | null): string {
  return QUALITY_COLORS[quality ?? ""] ?? QUALITY_COLORS.no_coverage;
}

function gridCols(count: number): string {
  if (count === 2) return "sm:grid-cols-2";
  if (count === 3) return "sm:grid-cols-2 lg:grid-cols-3";
  if (count === 4) return "sm:grid-cols-2 lg:grid-cols-4";
  return "";
}

function panelStyle(colorVar: string): CSSProperties {
  return { "--panel-color": `var(${colorVar})` } as CSSProperties;
}

function ChartCard({
  colorVar,
  icon,
  title,
  subtitle,
  value,
  children,
}: {
  colorVar: string;
  icon?: ReactNode;
  title: string;
  subtitle: string;
  value?: number;
  children?: ReactNode;
}) {
  return (
    <div
      className="card bg-base-100 shadow-xl panel-accent"
      style={panelStyle(colorVar)}
    >
      <div className="card-body">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="card-title text-base">
              {icon}
              {title}
            </h2>
            <p className="text-xs opacity-80">{subtitle}</p>
          </div>
          {value !== undefined && (
            <div
              className="text-3xl font-bold leading-none"
              style={{ color: `var(${colorVar})` }}
            >
              {formatNumber(value)}
            </div>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}

function RoutesHealth({ routes }: { routes: RouteOverviewItem[] }) {
  const { t } = useTranslation();
  if (!routes || routes.length === 0) {
    return <p className="text-sm opacity-70">{t("dashboard.routes_empty")}</p>;
  }

  const labelFor = (quality: string | null) =>
    t("routes.quality_" + (quality || "unknown"));
  const sorted = routes
    .slice()
    .sort((a, b) => (b.matched_count || 0) - (a.matched_count || 0));
  const visible = sorted.slice(0, 6);
  const hidden = sorted.length - visible.length;

  return (
    <div className="space-y-2">
      {visible.map((route, i) => {
        const history = route.history || [];
        const averageTier =
          history.length > 0 ? averageRouteTier(history) : null;
        const current =
          averageTier ||
          (route.enabled ? route.quality || "no_coverage" : "disabled");
        return (
          <div
            key={`${route.from_label}->${route.to_label}-${i}`}
            className="flex items-center gap-2"
          >
            <span
              className="flex-1 min-w-0 truncate text-sm"
              title={`${route.from_label} \u2192 ${route.to_label}`}
            >
              {route.from_label} <span className="opacity-50">→</span>{" "}
              {route.to_label}
            </span>
            <div className="flex gap-0.5 flex-shrink-0">
              {history.map((entry) => (
                <div
                  key={entry.date}
                  className="route-health-cell"
                  style={{ background: qualityColor(entry.quality) }}
                  title={`${entry.date} \u2014 ${labelFor(entry.quality)} (${entry.matched_count})`}
                ></div>
              ))}
            </div>
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: qualityColor(current) }}
              title={labelFor(current)}
            ></span>
          </div>
        );
      })}
      {hidden > 0 && (
        <p className="text-xs opacity-60 pt-1">
          {t("dashboard.routes_more", { count: hidden })}
        </p>
      )}
    </div>
  );
}

export function DashboardPage() {
  const { t } = useTranslation();
  const config = useAppConfig();
  const { formatDateTime } = useFormatDateTime();
  usePageTitle("entities.dashboard");

  const features = config.features ?? {};
  const showNodes = features.nodes !== false;
  const showAdverts = features.advertisements !== false;
  const showMessages = features.messages !== false;
  const showPackets = features.packets !== false;
  const showRoutes = features.routes !== false;

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      try {
        const [
          stats,
          recentActivity,
          advertActivity,
          messageActivity,
          nodeCount,
          packetActivity,
          packetBreakdown,
          routesOverview,
          channelsData,
        ] = await Promise.all([
          apiGet<DashboardStats>("/api/v1/dashboard/stats", {}, { signal }),
          apiGet<RecentActivity>(
            "/api/v1/dashboard/recent-activity",
            {},
            { signal },
          ),
          apiGet<ActivitySeries>(
            "/api/v1/dashboard/activity",
            { days: 7 },
            { signal },
          ),
          apiGet<ActivitySeries>(
            "/api/v1/dashboard/message-activity",
            { days: 7 },
            { signal },
          ),
          apiGet<ActivitySeries>(
            "/api/v1/dashboard/node-count",
            { days: 7 },
            { signal },
          ),
          apiGet<ActivitySeries>(
            "/api/v1/dashboard/packet-activity",
            { days: 7 },
            { signal },
          ),
          apiGet<PacketBreakdown>(
            "/api/v1/dashboard/packet-breakdown",
            { days: 7 },
            { signal },
          ),
          showRoutes
            ? apiGet<RoutesOverview>(
                "/api/v1/dashboard/routes-overview",
                { days: 7 },
                { signal },
              )
            : Promise.resolve(null),
          apiGet<ChannelsResponse>("/api/v1/channels", {}, { signal }),
        ]);
        setData({
          stats,
          recentActivity,
          advertActivity,
          messageActivity,
          nodeCount,
          packetActivity,
          packetBreakdown,
          routesOverview,
          channelsData,
        });
        setError(null);
      } catch (e) {
        if (isAbortError(e)) return;
        setError(
          e instanceof Error && e.message
            ? e.message
            : t("common.failed_to_load_page"),
        );
      } finally {
        setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [showRoutes, t]);

  const channelLabels = useMemo(() => {
    if (!data) return new Map<number, string>();
    return new Map<number, string>([
      ...getChannelLabelsMap(config),
      ...(data.channelsData.items || [])
        .map((ch) => [parseInt(ch.channel_hash, 16), ch.name] as [number, string])
        .filter(([idx]) => Number.isInteger(idx)),
    ]);
  }, [config, data]);

  if (loading) return <Loading />;
  if (error) return <ErrorAlert message={error} />;
  if (!data) return null;

  const { stats, recentActivity, packetBreakdown, routesOverview } = data;

  const formatTimeOnly = (iso: string | null) =>
    formatDateTime(iso, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  const formatTimeShort = (iso: string | null) =>
    formatDateTime(iso, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  const labelForChannel = (channel: string): string => {
    const idx = parseInt(String(channel), 10);
    if (Number.isInteger(idx)) {
      return resolveChannelLabel(idx, channelLabels) || `Ch ${idx}`;
    }
    return String(channel);
  };

  const eventTypeTotal =
    packetBreakdown?.by_event_type?.reduce((sum, b) => sum + b.count, 0) ?? 0;
  const pathWidthTotal =
    packetBreakdown?.by_path_width?.reduce((sum, b) => sum + b.count, 0) ?? 0;
  const hasRoutes = !!(
    routesOverview &&
    routesOverview.routes &&
    routesOverview.routes.length
  );
  const visibleChartCount =
    (showNodes ? 1 : 0) +
    (showAdverts ? 1 : 0) +
    (showMessages ? 1 : 0) +
    (showPackets ? 1 : 0);
  const bottomCount = (showAdverts ? 1 : 0) + (showMessages ? 1 : 0);

  const ads = recentActivity.recent_advertisements ?? [];
  const channelEntries = Object.entries(recentActivity.channel_messages ?? {});

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">{t("entities.dashboard")}</h1>
      </div>

      {visibleChartCount > 0 && (
        <>
          <div
            className={`grid grid-cols-1 ${gridCols(visibleChartCount)} gap-6 mb-8`}
          >
            {showNodes && (
              <ChartCard
                colorVar="--color-nodes"
                icon={<IconNodes className="h-5 w-5" />}
                title={t("entities.nodes")}
                subtitle={t("time.over_time_last_7_days")}
                value={stats.total_nodes}
              >
                <TrendLineChart
                  data={data.nodeCount}
                  label={t("common.total_entity", {
                    entity: t("entities.nodes"),
                  })}
                  borderColor={ChartColors.nodes}
                  backgroundColor={ChartColors.nodesFill}
                />
              </ChartCard>
            )}
            {showAdverts && (
              <ChartCard
                colorVar="--color-adverts"
                icon={<IconAdvertisements className="h-5 w-5" />}
                title={t("entities.advertisements")}
                subtitle={t("time.per_day_last_7_days")}
                value={stats.advertisements_7d}
              >
                <TrendLineChart
                  data={data.advertActivity}
                  label={t("entities.advertisements")}
                  borderColor={ChartColors.adverts}
                  backgroundColor={ChartColors.advertsFill}
                />
              </ChartCard>
            )}
            {showMessages && (
              <ChartCard
                colorVar="--color-messages"
                icon={<IconMessages className="h-5 w-5" />}
                title={t("entities.messages")}
                subtitle={t("time.per_day_last_7_days")}
                value={stats.messages_7d}
              >
                <TrendLineChart
                  data={data.messageActivity}
                  label={t("entities.messages")}
                  borderColor={ChartColors.messages}
                  backgroundColor={ChartColors.messagesFill}
                />
              </ChartCard>
            )}
            {showPackets && (
              <ChartCard
                colorVar="--color-packets"
                icon={<IconPackets className="h-5 w-5" />}
                title={t("entities.packets")}
                subtitle={t("time.per_day_last_7_days")}
                value={stats.packets_7d}
              >
                <TrendLineChart
                  data={data.packetActivity}
                  label={t("entities.packets")}
                  borderColor={ChartColors.packets}
                  backgroundColor={ChartColors.packetsFill}
                />
              </ChartCard>
            )}
          </div>

          {(showPackets || (showRoutes && hasRoutes)) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
              {showPackets && (
                <ChartCard
                  colorVar="--color-packets"
                  icon={<IconPackets className="h-5 w-5" />}
                  title={t("entities.packet_event_types")}
                  subtitle={t("time.last_7_days")}
                  value={eventTypeTotal}
                >
                  <StackedBarChart
                    buckets={packetBreakdown.by_event_type}
                    colors={ChartColors.breakdown}
                  />
                </ChartCard>
              )}
              {showPackets && (
                <ChartCard
                  colorVar="--color-packets"
                  icon={<IconPackets className="h-5 w-5" />}
                  title={t("entities.path_hash_width")}
                  subtitle={t("time.last_7_days")}
                  value={pathWidthTotal}
                >
                  <StackedBarChart
                    buckets={packetBreakdown.by_path_width}
                    colors={ChartColors.breakdown.slice(0, 3)}
                  />
                </ChartCard>
              )}
              {showRoutes && hasRoutes && (
                <ChartCard
                  colorVar="--color-routes"
                  title={t("dashboard.route_health")}
                  subtitle={t("time.last_7_days")}
                >
                  <RoutesHealth routes={routesOverview!.routes} />
                </ChartCard>
              )}
              {showRoutes && hasRoutes && (
                <ChartCard
                  colorVar="--color-routes"
                  title={t("dashboard.routes_trend")}
                  subtitle={t("time.routes_over_last_n_days", {
                    n: routesOverview!.days,
                  })}
                >
                  <RoutesTrendChart routes={routesOverview!.routes} />
                </ChartCard>
              )}
            </div>
          )}
        </>
      )}

      {bottomCount > 0 && (
        <div className={`grid grid-cols-1 ${gridCols(bottomCount)} gap-6`}>
          {showAdverts && (
            <div
              className="card bg-base-100 shadow-xl panel-accent"
              style={panelStyle("--color-adverts")}
            >
              <div className="card-body">
                <h2 className="card-title">
                  <IconAdvertisements className="h-6 w-6" />
                  {t("common.recent_entity", {
                    entity: t("entities.advertisements"),
                  })}
                </h2>
                {ads.length === 0 ? (
                  <p className="text-sm opacity-70">
                    {t("common.no_entity_yet", {
                      entity: t("entities.advertisements").toLowerCase(),
                    })}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="table table-sm w-full">
                      <thead>
                        <tr>
                          <th>{t("entities.node")}</th>
                          <th className="hidden md:table-cell">
                            {t("common.type")}
                          </th>
                          <th className="text-right">{t("common.received")}</th>
                          <th>{t("common.observers")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ads.map((ad, i) => {
                          const friendlyName = ad.tag_name || ad.name;
                          const displayName =
                            friendlyName || ad.public_key.slice(0, 12) + "...";
                          return (
                            <tr key={`${ad.public_key}-${ad.received_at}-${i}`}>
                              <td>
                                <Link
                                  to={`/nodes/${ad.public_key}`}
                                  className="link link-hover"
                                >
                                  <div className="font-medium">
                                    {displayName}
                                  </div>
                                </Link>
                                {friendlyName && (
                                  <div className="text-xs opacity-50 font-mono">
                                    {ad.public_key.slice(0, 12)}...
                                  </div>
                                )}
                              </td>
                              <td className="hidden md:table-cell">
                                <RouteTypeBadge routeType={ad.route_type ?? null} />
                              </td>
                              <td className="text-right text-sm opacity-70">
                                {formatTimeOnly(ad.received_at)}
                              </td>
                              <td>
                                {ad.observers && ad.observers.length >= 1 ? (
                                  <ObserverIcons observers={ad.observers} />
                                ) : ad.observed_by ? (
                                  <span className="opacity-50">{"\u{1F4E1}"}</span>
                                ) : (
                                  <span className="opacity-50">-</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {showMessages && channelEntries.length > 0 && (
            <div
              className="card bg-base-100 shadow-xl panel-accent"
              style={panelStyle("--color-messages")}
            >
              <div className="card-body">
                <h2 className="card-title">
                  <IconChannel className="h-6 w-6" />
                  {t("dashboard.recent_channel_messages")}
                </h2>
                <div className="space-y-4">
                  {channelEntries.map(([channel, messages]) => (
                    <div key={channel}>
                      <h3 className="font-semibold text-sm mb-2 flex items-center gap-2">
                        <span className="badge badge-info badge-sm">
                          {labelForChannel(channel)}
                        </span>
                      </h3>
                      <div className="space-y-1 pl-2 border-l-2 border-base-300">
                        {messages.map((msg, i) => (
                          <div
                            key={`${channel}-${msg.received_at}-${i}`}
                            className="text-sm"
                          >
                            <span className="text-xs opacity-50">
                              {formatTimeShort(msg.received_at)}
                            </span>{" "}
                            <span
                              className="break-words"
                              style={{ whiteSpace: "pre-wrap" }}
                            >
                              {msg.text || ""}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
